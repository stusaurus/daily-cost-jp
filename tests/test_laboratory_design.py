import json
import sys
import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from redesign_laboratory import main, photo_url, sample_pair

class LaboratoryDesignTests(unittest.TestCase):
    def setUp(self):
        self.items=[{'name':'箱ティッシュ150組60箱','price':3600,'unit_price':60,'metric':'box','url':'https://hb.afl.rakuten.co.jp/a','image':'https://thumbnail.image.rakuten.co.jp/a.jpg?_ex=128x128','shop':'A'}, {'name':'箱ティッシュ200組60箱','price':4200,'unit_price':70,'metric':'box','url':'https://hb.afl.rakuten.co.jp/b','image':'','shop':'B'}]
        self.categories={'tissue':{'name':'ティッシュ','items':self.items}}

    def test_demo_uses_real_equal_unit_inversion_and_image_parameters(self):
        cid,rows,inversion=sample_pair(self.categories)
        self.assertEqual(cid,'tissue');self.assertTrue(inversion)
        self.assertLess(rows[0][0]['price'],rows[1][0]['price'])
        self.assertGreater(rows[0][1][1],rows[1][1][1])
        self.assertEqual(rows[0][1][0],rows[1][1][0])
        self.assertIn('_ex=420x420',photo_url(self.items[0]['image']))
        self.assertEqual(photo_url('https://example.com/image?a=1'),'https://example.com/image?a=1')

    def test_rebuild_preserves_metadata_urls_scripts_tools_and_idempotence(self):
        markup='''<!doctype html><html lang="ja"><head><title>既存SEO</title><meta name="description" content="既存の説明"><link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/"><script type="application/ld+json">{"@type":"WebSite"}</script><style>body{color:red}</style></head><body><header><h1>旧画面</h1><p class="updated">更新日時</p></header><main><section id="purchase-tools"><button id="show-saved"></button><button id="show-comparison"></button><p id="purchase-tool-status"></p><div id="purchase-tool-panel" hidden></div></section><section id="product-finder-home"><form><input name="q" placeholder="商品名"></form></section><section id="exact-store-compare"><input id="exact-name"></section><section id="buy-judge"><button id="judge-button"></button></section><section class="category-section" id="tissue"><div class="product-list"><article class="product-card" id="tissue-rank-1"></article><article class="product-card" id="tissue-rank-2"></article></div></section><script>window.feature = 'keep';</script></main></body></html>'''
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/'today').mkdir();(site/'assets').mkdir()
            (site/'data.json').write_text(json.dumps({'updated_at':'2026-10-03','categories':self.categories}))
            (site/'today/data.json').write_text('{"items":[]}')
            page=site/'index.html';page.write_text(markup);category=site/'categories/tissue/index.html';category.parent.mkdir(parents=True);category.write_text(markup);main(site)
            text=page.read_text();s=BeautifulSoup(text,'html.parser')
            self.assertEqual(s.title.text,'既存SEO')
            self.assertEqual(s.select_one('[rel=canonical]')['href'],'https://stusaurus.github.io/daily-cost-jp/')
            self.assertIn("window.feature = 'keep';",text)
            for id_ in ['show-saved','show-comparison','exact-name','judge-button','tissue-rank-1','tissue-rank-2']:
                self.assertEqual(len(s.select('#'+id_)),1)
            c=BeautifulSoup(category.read_text(),'html.parser')
            self.assertEqual(c.select_one('#tissue-rank-1 .buy-button')['href'],self.items[0]['url'])
            self.assertIn('nofollow',c.select_one('#tissue-rank-1 .buy-button')['rel'])
            self.assertIn('100組',c.select_one('#tissue-rank-1 .unit-price').text)
            self.assertEqual(c.select_one('#tissue .product-list .product-card')['id'],'tissue-rank-2')
            self.assertEqual(c.select_one('#tissue-rank-2 .buy-button')['data-rank'],'2')
            self.assertEqual(len(s.select('h1')),1)
            self.assertEqual(len(s.select('.lab-mobile-nav')),1)
            self.assertNotIn('body{color:red}',text)
            main(site);self.assertEqual(page.read_text(),text)

if __name__=='__main__':unittest.main()
