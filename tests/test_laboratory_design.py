import json
import sys
import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from redesign_laboratory import main, photo_url, sample_pair, price_markup, category_showroom, demo_markup, recommendation_picks, buying_modes_markup, display_name
from art_direction import art_picture, CATEGORY_ART

class LaboratoryDesignTests(unittest.TestCase):
    def test_art_is_responsive_bounded_and_distinct_from_product_evidence(self):
        for key in ('hero','paper','tissue','wash','care','clean'):
            s=BeautifulSoup(art_picture(key,key=='hero'),'html.parser')
            image=s.img
            self.assertIn('assets/art/',image['src'])
            self.assertIn('.webp?v=',image['src'])
            self.assertIn('srcset',image.attrs)
            self.assertGreater(int(image['width']),0)
            self.assertGreater(int(image['height']),0)
            self.assertEqual(image['loading'],'eager' if key=='hero' else 'lazy')
            if key=='hero':
                self.assertEqual(s.source['media'],'(max-width:600px)')
                self.assertIn('hero-mobile-480.webp',s.source['srcset'])
                self.assertIn('hero-mobile-960.webp',s.source['srcset'])
            for filename in Path('scripts/design/art').glob(key+'-*.webp'):
                self.assertLess(filename.stat().st_size,120000)
        self.assertEqual(CATEGORY_ART['tissue'],'tissue')
    def test_mobile_hero_restores_one_column_after_desktop_refinement(self):
        css = Path('scripts/design/laboratory.css').read_text()
        self.assertIn('.lab-hero-grid{grid-template-columns:1fr;', css)
        self.assertIn('@media(max-width:600px){\n .art-cover{display:flex;flex-direction:column;', css)
        self.assertIn('.art-data{display:block;', css)
        self.assertIn('.art-search form{display:flex;flex-direction:row;', css)
        self.assertIn('.lab-buy-mode-grid{display:grid;grid-template-columns:repeat(3', css)
        self.assertIn('.lab-buy-mode-card.is-featured', css)

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

    def test_buying_modes_use_one_comparable_unit_and_explain_the_tradeoff(self):
        items = self.items + [{
            'name':'箱ティッシュ200組20箱',
            'price':1600,
            'unit_price':80,
            'metric':'box',
            'url':'https://hb.afl.rakuten.co.jp/c',
            'image':'',
            'shop':'C',
        }]
        category={'name':'ティッシュ','items':items}
        label,picks=recommendation_picks('tissue',category)
        self.assertEqual(label,'100組')
        self.assertEqual([pick[1] for pick in picks],['単価最安','普段使い','まとめ買い'])
        self.assertTrue(all(pick[2]['value'] > 0 for pick in picks))
        self.assertEqual(picks[0][2]['item']['name'],'箱ティッシュ200組60箱')
        markup=BeautifulSoup(buying_modes_markup('tissue',category),'html.parser')
        self.assertEqual(len(markup.select('.lab-buy-mode-card')),3)
        self.assertEqual(markup.select_one('[data-buy-mode="everyday"] .lab-buy-mode-kicker').text,'普段使い')
        self.assertIn('家族人数を推測せず',markup.select_one('.lab-buy-mode-note').text)
        self.assertTrue(all(card.select_one('.lab-mode-buy')['data-conversion-source']=='category' for card in markup.select('.lab-buy-mode-card')))
        self.assertTrue(all('100組' in card.select_one('.lab-mode-buy')['data-unit-price-label'] for card in markup.select('.lab-buy-mode-card')))
        long={'name':'A'*100}
        self.assertTrue(display_name(long).endswith('…'))
        self.assertLessEqual(len(display_name(long)),76)

    def test_premium_numbers_photos_and_difference_remain_factual(self):
        price=BeautifulSoup(price_markup(12345.67,'100ml'),'html.parser')
        self.assertEqual(price.select_one('.lab-price-value').text,'¥12,345.7')
        self.assertEqual(price.select_one('.lab-price-unit').text,'／100ml')
        demo=BeautifulSoup(demo_markup(self.categories),'html.parser')
        self.assertIn('5.00円の差',demo.text)
        self.assertEqual(len(demo.select('.lab-choice')),2)
        self.assertEqual(len(demo.select('.image-placeholder')),1)
        showroom=BeautifulSoup(category_showroom(self.categories),'html.parser')
        self.assertEqual(showroom.select_one('a')['href'],'/daily-cost-jp/categories/tissue/')
        self.assertIn('/a.jpg',showroom.select_one('img')['src'])
        self.assertIn('100組で比較',showroom.text)

    def test_rebuild_preserves_metadata_urls_scripts_tools_and_idempotence(self):
        markup='''<!doctype html><html lang="ja"><head><title>既存SEO</title><meta name="description" content="既存の説明"><link rel="canonical" href="https://stusaurus.github.io/daily-cost-jp/"><script type="application/ld+json">{"@type":"WebSite"}</script><style>body{color:red}</style></head><body><header><h1>旧画面</h1><p class="updated">更新日時</p></header><main><section class="purchase-answer" id="buying-answer"><h2>今日の比較</h2><div class="answer-pick"><a href="#tissue-rank-1">商品A</a><p><strong>100組単価</strong></p></div><p class="answer-price">1箱参考</p></section><section id="purchase-tools"><button id="show-saved"></button><button id="show-comparison"></button><p id="purchase-tool-status"></p><div id="purchase-tool-panel" hidden></div></section><section id="product-finder-home"><form><input name="q" placeholder="商品名"></form></section><section id="exact-store-compare"><input id="exact-name"></section><section id="buy-judge"><button id="judge-button"></button></section><section class="category-section" id="tissue"><div class="product-list"><article class="product-card" id="tissue-rank-1"></article><article class="product-card" id="tissue-rank-2"></article></div></section><script>window.feature = 'keep';</script></main></body></html>'''
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp);(site/'today').mkdir();(site/'assets').mkdir()
            (site/'data.json').write_text(json.dumps({'updated_at':'2026-10-03','categories':self.categories}))
            (site/'today/data.json').write_text('{"items":[]}')
            page=site/'index.html';page.write_text(markup);category=site/'categories/tissue/index.html';category.parent.mkdir(parents=True);category.write_text(markup.replace('100組単価','¥44.22／100組'));main(site)
            text=page.read_text();s=BeautifulSoup(text,'html.parser')
            self.assertEqual(s.title.text,'既存SEO')
            self.assertEqual(s.select_one('[rel=canonical]')['href'],'https://stusaurus.github.io/daily-cost-jp/')
            self.assertIn("window.feature = 'keep';",text)
            for id_ in ['show-saved','show-comparison','exact-name','judge-button','tissue-rank-1','tissue-rank-2']:
                self.assertEqual(len(s.select('#'+id_)),1)
            c=BeautifulSoup(category.read_text(),'html.parser')
            self.assertIn('/a.jpg',c.select_one('.lab-answer-photo img')['src'])
            self.assertEqual(c.select_one('.answer-pick .lab-price-value').text,'¥44.22')
            self.assertEqual(c.select_one('.answer-pick .lab-price-unit').text,'／100組')
            self.assertIn('1箱参考',c.select_one('.lab-answer-context').text)
            self.assertEqual(c.select_one('#tissue-rank-1 .buy-button')['href'],self.items[0]['url'])
            self.assertIn('nofollow',c.select_one('#tissue-rank-1 .buy-button')['rel'])
            self.assertIn('100組',c.select_one('#tissue-rank-1 .unit-price').text)
            self.assertEqual(c.select_one('#tissue .product-list .product-card')['id'],'tissue-rank-2')
            self.assertEqual(c.select_one('#tissue-rank-2 .buy-button')['data-rank'],'2')
            self.assertEqual(len(s.select('h1')),1)
            self.assertIn('本当に安い',s.h1.text)
            self.assertEqual(len(s.select('#product-finder-home')),1)
            self.assertIsNotNone(s.select_one('.art-cover #product-finder-home'))
            self.assertIsNotNone(s.select_one('#art-data .lab-sample-photo img[src*="rakuten"]'))
            self.assertFalse(s.select('.product-card img[src*="assets/art"]'))
            self.assertEqual(s.select_one('.art-cover img')['fetchpriority'],'high')
            self.assertTrue((site/'assets/art/hero-800.webp').is_file())
            self.assertEqual(len(s.select('.lab-mobile-nav')),1)
            self.assertNotIn('body{color:red}',text)
            main(site);self.assertEqual(page.read_text(),text)

if __name__=='__main__':unittest.main()
