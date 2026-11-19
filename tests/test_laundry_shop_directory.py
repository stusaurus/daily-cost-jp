import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from laundry_shop_directory import MARKER, verified_groups, render, apply


def example():
    products = []
    blocks = []
    for n, (shop, price) in enumerate([('店A&B', 850), ('店C', 1000), ('店A& B', 1200)], 1):
        url = f'https://hb.afl.rakuten.co.jp/hgc/offer-{n}/'
        products.append({'name': f'洗濯洗剤 詰め替え850g まとめ{n}',
                         'shop': shop, 'postage': '送料込み', 'quality_version': 1,
                         'metric': '100g', 'price': price, 'unit_price': price / 8.5, 'url': url})
        blocks.append(f'<article class="product-card" id="laundry-rank-{n}">'
                      f'<p class="shop">{shop.replace("&", "&amp;")}</p>'
                      f'<a class="buy-button" data-rank="{n}" data-category-id="laundry" '
                      f'data-shipping-price="{price}" href="{url}">楽天へ</a></article>')
    markup = ('<html><head></head><body><main class="container">'
              '<section id="buying-decisions" class="buying-decisions"><h2>比較</h2></section>'
              '<section id="laundry"><div class="product-list">'
              + ''.join(blocks) + '</div></section></main></body></html>')
    return markup, {'categories': {'laundry': {'items': products}}}


class LaundryShopDirectoryTests(unittest.TestCase):
    def test_groups_only_published_verified_offers(self):
        markup, data = example()
        groups = verified_groups(markup, data)
        self.assertEqual(len(groups), 3)
        self.assertEqual(sum(map(len, groups.values())), 3)
        output = render(groups)
        parsed = BeautifulSoup(output, 'html.parser')
        self.assertEqual(len(parsed.select('.laundry-shop-item')), 3)
        self.assertEqual(len(parsed.select('a[href^="#laundry-rank-"]')), 3)
        self.assertFalse(any(link.get('href', '').startswith('https://') for link in parsed.select('a')))
        self.assertIn('異なる商品を比べた「安い店ランキング」ではありません', output)
        self.assertIn('店A&amp;B', output)

    def test_fail_closed_when_offer_and_rendered_price_disagree(self):
        markup, data = example()
        self.assertFalse(verified_groups(markup.replace('data-shipping-price="850"',
                                                       'data-shipping-price="800"'), data))
        changed = copy.deepcopy(data)
        changed['categories']['laundry']['items'][1]['postage'] = '送料別'
        self.assertFalse(verified_groups(markup, changed))
        changed = copy.deepcopy(data)
        changed['categories']['laundry']['items'][0]['quality_version'] = 0
        self.assertFalse(verified_groups(markup, changed))

    def test_duplicate_offer_or_missing_product_card_fails_closed(self):
        markup, data = example()
        changed = copy.deepcopy(data)
        changed['categories']['laundry']['items'][2]['url'] = changed['categories']['laundry']['items'][0]['url']
        self.assertFalse(verified_groups(markup, changed))
        self.assertFalse(verified_groups(markup.replace('laundry-rank-3', 'missing-rank-3'), data))

    def test_one_shop_does_not_pretend_to_compare_stores(self):
        markup, data = example()
        changed = copy.deepcopy(data)
        for row in changed['categories']['laundry']['items']:
            row['shop'] = '同じ店'
        same_markup = (markup.replace('店A&amp;B', '同じ店')
                       .replace('店A&amp; B', '同じ店').replace('店C', '同じ店'))
        self.assertFalse(verified_groups(same_markup, changed))

    def test_inserts_once_without_modifying_original_affiliate_links(self):
        markup, data = example()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'categories/laundry').mkdir(parents=True)
            page = folder / 'categories/laundry/index.html'
            page.write_text(markup, encoding='utf-8')
            (folder / 'data.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(apply(folder), 'rendered:3shops/3offers')
            result = page.read_text(encoding='utf-8')
            self.assertEqual(apply(folder), 'already_exists')
            self.assertEqual(page.read_text(encoding='utf-8'), result)
            self.assertEqual(result.count(MARKER), 1)
            doc = BeautifulSoup(result, 'html.parser')
            self.assertEqual([x.get('id') for x in doc.select('main > section')][:3],
                             ['buying-decisions', 'laundry-shop-directory', 'laundry'])
            self.assertEqual([x['href'] for x in doc.select('article.product-card a.buy-button')],
                             [x['url'] for x in data['categories']['laundry']['items']])
            self.assertEqual(len(doc.select('.laundry-shop-directory a')), 3)


if __name__ == '__main__':
    unittest.main()
