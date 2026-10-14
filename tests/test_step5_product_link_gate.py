"""Production renderer -> full product gate, including hostile supplements."""
import copy
import datetime as dt
import html
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import step4_recommendations as purpose
import validate_product_quality as gate
from build_freshness import provenance
from candidate_acquisition import SUPPLEMENTAL_QUERIES
from sync_trend_search_chips import checked_suggestions
from test_step4_purchase_audit import offer


class ProductLinkIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ranked = {
            'tissue': offer(qty=60, suffix='tbulk', title='ボックスティッシュ 200組 5箱×12パック'),
            'laundry': offer('laundry', 90, '100g', suffix='lbulk', title='洗濯洗剤 1500g×6本'),
            'toilet-paper': offer('toilet-paper', 48, 'roll', suffix='pbulk', title='トイレットペーパー シングル 50m 48ロール'),
        }
        self.extra = {
            'tissue': offer(qty=5, suffix='tsmall'),
            'laundry': offer('laundry', 15, '100g', suffix='ldaily', title='洗濯洗剤 詰め替え 1500g'),
            'toilet-paper': offer('toilet-paper', 12, 'roll', suffix='psmall', title='トイレットペーパー シングル 50m 12ロール'),
        }
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        self.payload = {'source': 'Rakuten Ichiba API', 'ranking_basis': 'shipping_included_unit_price',
                        'updated_at': stamp, 'categories': {cid: {'items': [], 'error': 'API unavailable'} for cid in gate.REQUIRED}}
        self.report = {cid: {'published': 0, 'published_products': []} for cid in gate.REQUIRED}
        for cid in self.ranked:
            row = self.ranked[cid]
            self.payload['categories'][cid] = {'name': cid, 'metric': row['metric'], 'items': [row],
                                               'purpose_candidates': [self.extra[cid]]}
            self.report[cid] = {'published': 1, 'published_products': [row], 'acquisition': {
                'baseline': {'ranked': 1}, 'requests': [{'supplementary': True, 'query': SUPPLEMENTAL_QUERIES[cid][0]}]}}

    def render(self):
        (self.root / 'data.json').write_text(json.dumps(self.payload))
        report_path = self.root / 'quality-report.json'
        report_path.write_text(json.dumps(self.report))
        now = dt.datetime.now(dt.timezone.utc)
        daily = {'items': [], 'text': '', 'generated_at': now.isoformat(), 'date': now.date().isoformat(), **provenance(self.payload)}
        for name in ('today/data.json', 'social/latest.json'):
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(daily))
        chips = ''.join(f'<button class="chip" data-q="{html.escape(q, quote=True)}"></button>' for _, q, _ in checked_suggestions())
        for name in ('index.html', 'categories/tissue/index.html', 'categories/laundry/index.html', 'categories/toilet-paper/index.html', 'today/index.html', 'products/index.html'):
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('<html><head></head><body><main>' + (chips if name == 'products/index.html' else '') + '</main></body></html>')
        before = copy.deepcopy(self.payload)
        purpose.apply(self.root, enabled=True)
        self.assertEqual(json.loads((self.root / 'data.json').read_text()), before)
        return report_path

    def errors(self):
        return gate.validate(self.root, self.root / 'quality-report.json')[0]

    def test_active_home_and_three_categories_pass_full_product_gate_without_ranking_mutation(self):
        self.render()
        # Reproduce the old ranking-only allowlist's exact four-page failure.
        with patch.object(gate, 'verified_purpose_links', return_value=set()):
            failures = [e for e in self.errors() if 'outside verified selection' in e]
            self.assertEqual({e.split(':')[0] for e in failures}, {'index.html', 'categories/tissue/index.html',
                             'categories/laundry/index.html', 'categories/toilet-paper/index.html'})
        self.assertEqual(self.errors(), [])
        _, ranked_allowed = gate.validate_catalog(self.payload)
        for cid in self.extra:
            self.assertNotIn(self.extra[cid]['url'], ranked_allowed[cid])
            self.assertIn(self.extra[cid]['url'], (self.root / f'categories/{cid}/index.html').read_text())
        self.assertEqual(len(gate.verified_purpose_links(self.payload)), 3)

    def test_unverified_or_unselected_links_cannot_be_added_by_attributes_or_flags(self):
        self.render()
        for url in ('https://item.rakuten.co.jp/shop/unverified/', 'https://evil.example/buy'):
            page = self.root / 'index.html'; old = page.read_text()
            page.write_text(old.replace('</main>', f'<a href="{url}" data-category-id="tissue" data-purchase-purpose="small">buy</a></main>'))
            self.assertTrue(any('outside verified selection' in e for e in self.errors()))
            page.write_text(old)
        self.payload['categories']['tissue']['purpose_candidates'].append(offer(qty=5, suffix='unselected', unit_price=200))
        self.render()
        page = self.root / 'index.html'
        page.write_text(page.read_text().replace('</main>', '<a href="https://item.rakuten.co.jp/shop/unselected/" data-category-id="tissue" data-purchase-purpose="small">buy</a></main>'))
        self.assertTrue(any('outside verified selection' in e for e in self.errors()))

    def test_purpose_offer_not_authorized_for_ranking_today_social_other_category_or_wrong_slot(self):
        self.render()
        url = self.extra['tissue']['url']
        for name, cid, slot in [('index.html', None, None), ('today/index.html', 'tissue', 'small'),
                                ('categories/laundry/index.html', 'tissue', 'small'), ('index.html', 'tissue', 'bulk')]:
            page = self.root / name; old = page.read_text()
            attrs = '' if cid is None else f' data-category-id="{cid}" data-purchase-purpose="{slot}"'
            page.write_text(old.replace('</main>', f'<a href="{url}"{attrs}>buy</a></main>'))
            self.assertTrue(any('outside verified selection' in e for e in self.errors()))
            page.write_text(old)
        _, accepted = gate.validate_catalog(self.payload)
        row = self.extra['tissue']
        self.assertTrue(gate.validate_recommendations({'items': [{'id': 'tissue', 'url': url, 'product_name': row['name'],
                         'metric': row['metric'], 'price': row['price'], 'unit_price': row['unit_price']}]}, accepted))

    def test_bad_quantity_shipping_identity_use_units_and_price_fall_back_without_authorization(self):
        base = self.extra['tissue']
        for edit in ({'postage': '送料不明'}, {'item_code': 'shop:wrong'}, {'name': 'ボックスティッシュ 5箱〜60箱'},
                     {'name': 'ボックスティッシュ 容量不明'}, {'name': 'ティッシュケース 5箱'},
                     {'name': 'ボックスティッシュ 200組 5箱 法人限定'}, {'metric': 'pack'}, {'price': 1},
                     {'url': 'https://evil.example/item'}, {'url': 'https://[malformed'}, {'confidence': 0.1}):
            with self.subTest(edit=edit):
                self.payload['categories']['tissue']['purpose_candidates'] = [{**base, **edit, 'quality_version': 'forged'}]
                self.render()
                self.assertEqual(purpose.verified_purpose_candidates('tissue', self.payload['categories']['tissue']), [])
                self.assertEqual(self.errors(), [])
                self.assertIn('確認できる候補なし', (self.root / 'categories/tissue/index.html').read_text())

    def test_group_outlier_is_not_rendered_or_authorized(self):
        rows = [offer(qty=5, suffix=f'price{i}', unit_price=p) for i, p in enumerate((1, 100, 110, 120))]
        self.payload['categories']['tissue']['purpose_candidates'] = rows
        self.render()
        self.assertNotIn(rows[0]['url'], (self.root / 'index.html').read_text())
        self.assertEqual(self.errors(), [])
        self.assertEqual(len(purpose.verified_purpose_candidates('tissue', self.payload['categories']['tissue'])), 3)

    def test_different_mass_volume_or_ply_family_is_not_authorized(self):
        for cid, row in (
            ('laundry', offer('laundry', 15, '100ml', suffix='volume', title='洗濯洗剤 1500ml')),
            ('toilet-paper', offer('toilet-paper', 12, 'roll', suffix='double', title='トイレットペーパー ダブル 50m 12ロール')),
        ):
            self.payload['categories'][cid]['purpose_candidates'] = [row]
            self.render()
            self.assertEqual(purpose.verified_purpose_candidates(cid, self.payload['categories'][cid]), [])
            self.assertNotIn(row['url'], (self.root / 'index.html').read_text())
            self.assertEqual(self.errors(), [])

    def test_malformed_empty_and_unavailable_pool_safe_fallback(self):
        for pool in ([], [None], 'invalid', [self.extra['tissue']] * 31):
            self.payload['categories']['tissue']['purpose_candidates'] = pool
            self.render(); self.assertEqual(self.errors(), [])
        category = self.payload['categories']['tissue']
        category['purpose_candidates'] = [self.extra['tissue']]; category['error'] = 'API unavailable'
        self.render(); self.assertEqual(self.errors(), [])
        self.assertEqual(purpose.verified_purpose_candidates('tissue', category), [])


if __name__ == '__main__':
    unittest.main()
