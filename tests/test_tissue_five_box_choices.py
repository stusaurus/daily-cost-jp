import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from tissue_five_box_choices import MARKER, select_offers, render, apply


def offer(n, qty=5, price=1050, pairs=180, shop=None):
    shopid = f'testshop{n}'
    return {
        'item_code': f'{shopid}:item{n}',
        'name': f'ボックスティッシュ {pairs}組 {qty}箱 まとめ買い 商品{n}',
        'shop': shop if shop is not None else f'検証店{n}',
        'price': price,
        'unit_price': price / qty,
        'metric': 'box',
        'confidence': .99,
        'postage': '送料込み',
        'quality_version': 1,
        'url': f'https://item.rakuten.co.jp/{shopid}/item{n}/',
    }


def catalog():
    return {'categories': {'tissue': {
        'items': [offer(90, 60, 5400, 200)],
        'purpose_candidates': [
            offer(1), offer(2, price=1111), offer(3, price=1958, pairs=220),
            offer(4, qty=60, price=5000),
        ],
        'error': None,
    }}}


class TissueFiveBoxShopTests(unittest.TestCase):
    def test_strict_five_box_choices_exclude_bulk(self):
        items = select_offers(catalog()['categories']['tissue'])
        self.assertEqual(len(items), 3)
        self.assertEqual([int(x[0]) for x in items], [1050, 1111, 1958])
        self.assertEqual([x[2] for x in items], [180, 180, 220])

    def test_invalid_shipping_and_wrong_identity_are_excluded(self):
        data = catalog()
        data['categories']['tissue']['purpose_candidates'][1]['postage'] = '送料別'
        self.assertEqual(len(select_offers(data['categories']['tissue'])), 2)
        data['categories']['tissue']['purpose_candidates'][0]['item_code'] = 'other:code'
        self.assertEqual(select_offers(data['categories']['tissue']), [])

    def test_one_shop_does_not_claim_multiple_shops(self):
        data = catalog()
        for row in data['categories']['tissue']['purpose_candidates']:
            row['shop'] = '同じ店'
        self.assertEqual(select_offers(data['categories']['tissue']), [])

    def test_explanations_and_links_use_checked_offers(self):
        offers = select_offers(catalog()['categories']['tissue'])
        result = render(offers)
        soup = BeautifulSoup(result, 'html.parser')
        self.assertEqual(len(soup.select('.tissue-five-box-item')), 3)
        self.assertEqual(len(soup.select('a.buy-button')), 3)
        self.assertIn('異なる商品を同一商品の店別最安値とは扱いません', result)
        self.assertIn('220組×5箱', result)
        for link in soup.select('a.buy-button'):
            self.assertEqual(link.get('rel'), ['nofollow', 'sponsored', 'noopener'])
            self.assertEqual(link.get('data-conversion-source'), 'category')
            self.assertEqual(link.get('data-purchase-purpose'), 'small')
            self.assertEqual(link.get('data-category-id'), 'tissue')
            self.assertTrue(link['href'].startswith('https://item.rakuten.co.jp/'))

    def test_injects_once_and_preserves_existing_buy_button(self):
        data = catalog()
        sample = ('<html><head></head><body><main>'
                  '<section class="tissue-size-guide" id="tissue-buy-size"></section>'
                  '<section class="purchase-answer lab-answer" id="buying-answer">'
                  '<a class="buy-button" href="https://item.rakuten.co.jp/original/x/">既存の購入先</a>'
                  '</section></main></body></html>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / 'categories/tissue/index.html'
            page.parent.mkdir(parents=True)
            page.write_text(sample)
            (root / 'data.json').write_text(json.dumps(data, ensure_ascii=False))
            self.assertEqual(apply(root), 'rendered:3offers')
            result = page.read_text()
            self.assertEqual(apply(root), 'already_exists')
            self.assertEqual(page.read_text(), result)
            self.assertEqual(result.count(MARKER), 1)
            soup = BeautifulSoup(result, 'html.parser')
            self.assertEqual(soup.select_one('#tissue-five-box-details').name, 'details')
            self.assertEqual(soup.select_one('#buying-answer .buy-button')['href'],
                             'https://item.rakuten.co.jp/original/x/')
            self.assertEqual(len(soup.select('.tissue-five-box-item')), 3)

    def test_missing_verified_offers_does_not_modify_page(self):
        data = catalog()
        data['categories']['tissue']['purpose_candidates'] = []
        sample = ('<html><head></head><body>'
                  '<section id="tissue-buy-size"></section>'
                  '<section class="purchase-answer lab-answer" id="buying-answer"></section>'
                  '</body></html>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / 'categories/tissue/index.html'
            page.parent.mkdir(parents=True)
            page.write_text(sample)
            (root / 'data.json').write_text(json.dumps(data, ensure_ascii=False))
            self.assertEqual(apply(root), 'no_verified_five_box_choice')
            self.assertEqual(page.read_text(), sample)


if __name__ == '__main__':
    unittest.main()
