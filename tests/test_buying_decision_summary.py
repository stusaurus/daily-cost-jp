import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from buying_decision_summary import render
from bs4 import BeautifulSoup
class SummaryTests(unittest.TestCase):
 def test_tradeoff_preserves_quantity_and_links_and_rejects_unknown_shipping(self):
  def card(i,p,u):return f'<article class="product-card" id="laundry-rank-{i}"><span class="lab-price-value">¥{u}</span><span class="lab-price-unit">／100g</span><p class="purchase-summary">{i}袋</p><a class="buy-button" href="https://example.com/{i}" data-shipping-price="{p}"></a></article>'
  raw=card(1,500,50)+card(2,1000,25)+card(3,1,1)
  offers={'items':[{'url':f'https://example.com/{i}','price':p,'postage':post}for i,p,post in [(1,500,'送料込み'),(2,1000,'送料込み'),(3,1,'不明')]]}
  d=BeautifulSoup(render(raw,offers,'laundry'),'html.parser')
  self.assertEqual([r['data-decision-target']for r in d.select('tbody tr')],['laundry-rank-1','laundry-rank-2'])
  self.assertIn('単価最安と支払総額最安は違います',d.get_text());self.assertIn('¥500高くなります',d.get_text());
  self.assertIn('1袋',d.get_text());self.assertIn('2袋',d.get_text());self.assertIn('¥500',d.get_text());self.assertEqual(d.select_one('tbody a')['href'],'#laundry-rank-1')
  self.assertEqual(render(raw,{'items':[]},'laundry'),'')
