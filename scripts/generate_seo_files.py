from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

SITE_DIR = Path("site")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/") + "/"

if not SITE_URL.strip("/"):
    raise SystemExit("SITE_URL is required")
if not SITE_DIR.exists():
    raise SystemExit("site directory does not exist")

urls = []
for html in sorted(SITE_DIR.rglob("*.html")):
    rel = html.relative_to(SITE_DIR).as_posix()
    if rel == "404.html" or (rel.startswith("google") and "/" not in rel):
        continue
    if rel == "index.html":
        path = ""
    elif rel.endswith("/index.html"):
        path = rel[:-10]
    else:
        path = rel
    url = SITE_URL + quote(path, safe="/-._~")
    urls.append(url)

today = date.today().isoformat()
xml = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
for url in urls:
    xml.append(f"  <url><loc>{url}</loc><lastmod>{today}</lastmod></url>")
xml.append("</urlset>")
(SITE_DIR / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")
robots = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n"
(SITE_DIR / "robots.txt").write_text(robots, encoding="utf-8")

# Fail the deployment if the discovery files Google receives are malformed.
root = ET.parse(SITE_DIR / "sitemap.xml").getroot()
ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
parsed_urls = [node.text for node in root.findall(f"{ns}url/{ns}loc")]
if parsed_urls != urls:
    raise SystemExit("sitemap.xml validation failed: generated URL list differs from parsed XML")
if not urls or len(set(urls)) != len(urls):
    raise SystemExit("sitemap.xml validation failed: empty or duplicate URLs")
expected_sitemap_line = f"Sitemap: {SITE_URL}sitemap.xml"
if expected_sitemap_line not in robots.splitlines():
    raise SystemExit("robots.txt validation failed: sitemap declaration missing")
print(f"Generated and validated sitemap.xml with {len(urls)} URLs and robots.txt")
