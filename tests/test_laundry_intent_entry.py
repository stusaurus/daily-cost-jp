import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from improve_purchase_pages import price_answer
class Entry(unittest.TestCase):
 def test_empty_supply_still_exposes_existing_comparison_routes(self):
  s=price_answer('laundry',{'items':[],'metric':'100g'})
  self.assertLess(s.index('aria-label="洗剤の比較方法を選ぶ"'),s.index('store-comparison-method'))
  for url in ['#laundry','../../products/','../../tools/laundry-cost-per-wash/']:
   self.assertIn('href="'+url+'"',s)
  self.assertIn('店舗別の最安順位は表示できません',s)
  self.assertIn('同じ条件で比較できる候補がありません',s)
 def test_other_categories_keep_existing_unit_guide(self):
  s=price_answer('tissue',{'items':[],'metric':'box'})
  self.assertNotIn('洗剤の比較方法を選ぶ',s)
  self.assertIn('同じ単位で計算する',s)
 def test_paper_category_search_visitors_can_compare_real_store_price(self):
  for category, metric in [('tissue','box'),('toilet-paper','roll')]:
   with self.subTest(category=category):
    s=price_answer(category,{'items':[],'metric':metric})
    self.assertIn('href="../../#exact-store-compare"',s)
    self.assertIn('店頭で見た税込価格を入力',s)
    self.assertIn('同一商品と確認できない場合は比較結果を出しません',s)
    self.assertIn('店舗別の最安順位を示す機能ではありません',s)
    self.assertLess(s.index('href="../../#exact-store-compare"'),s.index('同じ条件で比較できる候補がありません'))
    self.assertIn('href="#'+category+'"',s)
    self.assertIn('href="../../products/"',s)
    self.assertIn('同じ単位で計算する',s)
    self.assertNotIn('洗剤の比較方法を選ぶ',s)
    self.assertEqual(s.count('href="../../#exact-store-compare"'),1)
 def test_store_compare_is_real_existing_homepage_tool_not_a_fabricated_shop_ranking(self):
  from pathlib import Path
  tool=Path('scripts/add_exact_store_compare.py').read_text(encoding='utf-8')
  self.assertIn('id="exact-store-compare"',tool)
  self.assertIn('同じ商品',tool)
  self.assertIn('店頭価格',tool)
  laundry=price_answer('laundry',{'items':[],'metric':'100g'})
  self.assertNotIn('href="../../#exact-store-compare"',laundry)
if __name__=='__main__':unittest.main()
