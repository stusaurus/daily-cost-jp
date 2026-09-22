"""Fail a Pages deployment on broken internal destinations or tagging metadata."""
from __future__ import annotations
from collections import defaultdict
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
import xml.etree.ElementTree as ET

BASE = 'https://stusaurus.github.io/daily-cost-jp/'


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.canonical, self.schema = [], [], []
        self.ids, self.meta = set(), {}
        self.h1, self.title = 0, ''
        self.in_title = self.in_schema = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'): self.ids.add(a['id'])
        if tag == 'a': self.links.append(a)
        if tag == 'link' and a.get('rel') == 'canonical': self.canonical.append(a.get('href'))
        if tag == 'meta': self.meta[a.get('name', a.get('property', ''))] = a.get('content', '')
        if tag == 'h1': self.h1 += 1
        if tag == 'title': self.in_title = True
        if tag == 'script' and a.get('type') == 'application/ld+json': self.in_schema = True

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag == 'script': self.in_schema = False

    def handle_data(self, data):
        if self.in_title: self.title += data
        if self.in_schema: self.schema.append(data)


def validate(root=Path('site')):
    pages, errors = {}, []
    titles, descriptions = defaultdict(list), defaultdict(list)
    for path in root.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        rel = path.relative_to(root).as_posix()
        page = Page(); page.feed(text); pages[rel] = page
        expected = BASE + rel.removesuffix('index.html')
        if page.canonical != [expected]: errors.append(f'{rel}: canonical mismatch {page.canonical}')
        if page.h1 != 1: errors.append(f'{rel}: expected one H1')
        if not page.title or not page.meta.get('description'): errors.append(f'{rel}: missing title/description')
        if 'noindex' in page.meta.get('robots', '').lower(): errors.append(f'{rel}: unexpectedly noindex')
        titles[page.title].append(rel); descriptions[page.meta.get('description')].append(rel)
        for schema in page.schema:
            try: json.loads(schema)
            except ValueError: errors.append(f'{rel}: invalid JSON-LD')
        if text.count("gtag('config', 'G-GFVSZ8YDQ5')") != 1: errors.append(f'{rel}: missing/duplicate GA4 config')
        if 'data.operator_test = operator ?' not in text: errors.append(f'{rel}: missing explicit operator flag')
    rakuten = 0
    for rel, page in pages.items():
        for link in page.links:
            href = link.get('href', '')
            url = urlsplit(urljoin(BASE + rel, href))
            if url.hostname == 'stusaurus.github.io' and url.path.startswith('/daily-cost-jp/'):
                target = unquote(url.path.removeprefix('/daily-cost-jp/'))
                if not target or target.endswith('/'): target += 'index.html'
                if target not in pages: errors.append(f'{rel}: missing page {target}')
                elif url.fragment and unquote(url.fragment) not in pages[target].ids:
                    errors.append(f'{rel}: missing anchor {target}#{url.fragment}')
            elif url.hostname and (url.hostname == 'rakuten.co.jp' or url.hostname.endswith('.rakuten.co.jp')):
                rakuten += 1
                if '&amp;' in href: errors.append(f'{rel}: double-escaped Rakuten parameters')
                if url.scheme != 'https': errors.append(f'{rel}: insecure Rakuten link')
                if link.get('target') == '_blank' and 'noopener' not in link.get('rel', ''):
                    errors.append(f'{rel}: unsafe new tab')
    for kind, mapping in [('title', titles), ('description', descriptions)]:
        for group in mapping.values():
            if len(group) > 1: errors.append(f'duplicate {kind}: {group}')
    sitemap = ET.parse(root / 'sitemap.xml')
    actual = {n.text for n in sitemap.iter() if n.tag.endswith('}loc')}
    expected = {p.canonical[0] for p in pages.values() if len(p.canonical) == 1}
    if actual != expected: errors.append('sitemap does not cover exactly the canonical pages')
    return errors, {'pages': len(pages), 'rakuten_links': rakuten, 'sitemap_urls': len(actual)}


if __name__ == '__main__':
    errors, stats = validate()
    print(json.dumps(stats))
    if errors: raise SystemExit('\n'.join(errors))
    print('Generated site checks passed.')
