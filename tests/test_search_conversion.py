import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from improve_purchase_pages import price_answer
from report_daily_clicks import aggregate

class SearchConversionTests(unittest.TestCase):
    def test_mass_and_volume_are_never_aggregated_or_selected_together(self):
        rows = [dict(name='洗濯洗剤1000g', metric='100g', unit_price=20, price=200, url='https://item.rakuten.co.jp/shop/a'),
                dict(name='洗濯洗剤1000ml', metric='100ml', unit_price=5, price=50, url='https://item.rakuten.co.jp/shop/b')]
        with patch('improve_purchase_pages.filter_items', return_value=rows):
            soup = BeautifulSoup(price_answer('laundry', {'items':rows}), 'html.parser')
        groups = soup.select('.search-price-group')
        self.assertEqual(len(groups), 2)
        self.assertIn('¥20／100g', groups[0].get_text())
        self.assertNotIn('100ml', groups[0].get_text())
        self.assertEqual(groups[0].select_one('.buy-button')['href'], rows[0]['url'])
        self.assertEqual(groups[1].select_one('.buy-button')['href'], rows[1]['url'])

    def test_missing_length_never_creates_a_toilet_paper_price_claim(self):
        row = dict(name='トイレットペーパーダブル12ロール', metric='roll', unit_price=20, price=240)
        with patch('improve_purchase_pages.filter_items', return_value=[row]):
            soup = BeautifulSoup(price_answer('toilet-paper', {'items':[row]}), 'html.parser')
        self.assertFalse(soup.select('.buy-button'))
        self.assertIn('比較できる候補がありません', soup.get_text())

    def test_report_separates_sites_local_operator_and_missing_flags(self):
        base = dict(eventName='affiliate_click', eventCount='1')
        rows = [{**base, 'pageLocation':'https://stusaurus.github.io/daily-cost-jp/categories/tissue/', 'operator_test':v} for v in ['0','1','(not set)']]
        rows += [{**base, 'pageLocation':v, 'operator_test':'0'} for v in ['http://localhost:8765/daily-cost-jp/', 'https://stusaurus.github.io/baby-cost-jp/', '']]
        self.assertEqual(aggregate(rows), dict(production_operator=1, production_non_operator=1, production_unknown=1, development=1, other_site=1, unscoped=1))
