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
if __name__=='__main__':unittest.main()
