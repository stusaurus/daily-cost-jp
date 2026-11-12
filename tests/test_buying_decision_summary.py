import sys,unittest
import copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from buying_decision_summary import render
from bs4 import BeautifulSoup
from step4_recommendations import block, select_category
from test_step4_purchase_audit import offer
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

 def category_with_purpose(self,cid='laundry'):
  if cid=='laundry':
   ranked=offer(cid,90,'100g',unit_price=90,suffix='bulk',title='洗濯洗剤 1500g×6袋')
   small=offer(cid,8.5,'100g',unit_price=105.52941176470588,suffix='small',title='洗濯洗剤 850g')
  elif cid=='tissue':
   ranked=offer(qty=60,unit_price=90,suffix='bulk',title='ボックスティッシュ 200組 5箱×12パック')
   small=offer(qty=5,unit_price=120,suffix='small',title='ボックスティッシュ 180組 5箱')
  else:
   ranked=offer(cid,48,'roll',unit_price=110,suffix='bulk',title='トイレットペーパー シングル 170m 48ロール')
   small=offer(cid,12,'roll',unit_price=95,suffix='small',title='トイレットペーパー シングル 50m 12ロール')
  small['shop']='小量のお店';ranked['shop']='まとめ買いのお店'
  return {'items':[ranked],'purpose_candidates':[small]}

 def ranking_markup(self,cid,category):
  from comparison_units import comparison_unit,quantity_label
  p=category['items'][0];unit,value=comparison_unit(cid,p)
  return (f'<article class="product-card" id="{cid}-rank-1">'
          f'<span class="lab-price-value">¥{value:.2f}</span><span class="lab-price-unit">／{unit}</span>'
          f'<p class="purchase-summary">{quantity_label(p)}</p>'
          f'<a class="buy-button" href="{p["url"]}" data-shipping-price="{p["price"]}"></a></article>')

 def test_already_published_small_offer_is_first_checkout_choice(self):
  for cid in ('laundry','tissue','toilet-paper'):
   with self.subTest(cid=cid):
    c=self.category_with_purpose(cid);before=copy.deepcopy(c)
    cards=self.ranking_markup(cid,c)+block(cid,select_category(cid,c),cid)
    d=BeautifulSoup(render(cards,c,cid),'html.parser')
    self.assertEqual([r['data-decision-target']for r in d.select('tbody tr')],
                     [cid+'-purpose-small',cid+'-rank-1'])
    first=d.select_one('tbody tr')
    self.assertIn('小量のお店',first.get_text());self.assertIn('洗濯洗剤 850g' if cid=='laundry' else '12ロール' if cid=='toilet-paper' else '5箱',first.get_text())
    self.assertEqual(first.select_one('a')['href'],'#'+cid+'-purpose-small')
    self.assertEqual(c,before,'comparison must never alter source data or selection')

 def test_pool_never_overrides_disabled_or_paused_purpose_layer(self):
  c=self.category_with_purpose()
  d=BeautifulSoup(render(self.ranking_markup('laundry',c),c,'laundry'),'html.parser')
  self.assertEqual({r['data-decision-target']for r in d.select('tbody tr')},{'laundry-rank-1'})
  self.assertNotIn('purpose-small',str(d));self.assertNotIn('¥897',d.get_text())

 def test_mismatched_rendered_url_spec_or_price_cannot_publish_pool_offer(self):
  c=self.category_with_purpose()
  for attr,value in [('href','https://item.rakuten.co.jp/shop/other/'),('data-id','wrong'),
                     ('data-shipping-price','1'),('data-purchase-purpose','bulk'),('data-category-id','tissue')]:
   with self.subTest(attribute=attr):
    cards=BeautifulSoup(block('laundry',select_category('laundry',c),'洗剤'),'html.parser')
    cards.select_one('[data-purpose="small"] .buy-button')[attr]=value
    d=BeautifulSoup(render(self.ranking_markup('laundry',c)+str(cards),c,'laundry'),'html.parser')
    self.assertNotIn('laundry-purpose-small',str(d))

 def test_unknown_shipping_and_mixed_unit_pool_do_not_enter_summary(self):
  for edit in ({'postage':'送料別'},{'metric':'100ml','name':'洗濯洗剤 850ml'}):
   c=self.category_with_purpose()
   cards=self.ranking_markup('laundry',c)+block('laundry',select_category('laundry',c),'洗剤')
   c['purpose_candidates'][0].update(edit)
   d=BeautifulSoup(render(cards,c,'laundry'),'html.parser')
   self.assertNotIn('laundry-purpose-small',str(d))

 def test_unselected_pool_offer_is_not_promoted_by_summary(self):
  c=self.category_with_purpose()
  cards=self.ranking_markup('laundry',c)+block('laundry',select_category('laundry',c),'洗剤')
  c['purpose_candidates'].append(offer('laundry',8,'100g',unit_price=100,suffix='new',title='洗濯洗剤 800g'))
  d=BeautifulSoup(render(cards,c,'laundry'),'html.parser')
  self.assertNotIn('laundry-purpose-small',str(d));self.assertNotIn('¥800',d.get_text())

 def test_tissue_and_paper_use_normalized_comparison_units(self):
  for cid,unit in [('tissue','100組'),('toilet-paper','シングル10m')]:
   c=self.category_with_purpose(cid)
   cards=self.ranking_markup(cid,c)+block(cid,select_category(cid,c),cid)
   d=BeautifulSoup(render(cards,c,cid),'html.parser')
   self.assertEqual(len(d.select('tbody tr')),2)
   self.assertTrue(all(unit in r.get_text()for r in d.select('tbody tr')))

 def test_purpose_repeated_in_ranking_is_one_offer(self):
  c=self.category_with_purpose();c['purpose_candidates']=[]
  raw=self.ranking_markup('laundry',c)+block('laundry',select_category('laundry',c),'洗剤')
  d=BeautifulSoup(render(raw,c,'laundry'),'html.parser')
  self.assertEqual(len(d.select('tbody tr')),2)
  self.assertEqual({r['data-decision-target']for r in d.select('tbody tr')},{'laundry-rank-1'})
