import os
os.environ.setdefault("RAKUTEN_APPLICATION_ID", "offline-test")
os.environ.setdefault("RAKUTEN_ACCESS_KEY", "offline-test")
import json
import sys
import unittest
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from product_quality import category_rejection
from comparison_units import comparison_unit, quantity_label
from price_observations import update, stats, identity, prepare
from unittest.mock import patch
import urllib.error
import tempfile
from monitor_quality import monitor
from diversify_daily_deals import select_diverse
from build_site import choose_ranked_items

class CompletionTests(unittest.TestCase):
    def test_generated_purchase_script_is_versioned_to_refresh_revisitors(self):
        import hashlib
        import complete_purchase_flow
        with tempfile.TemporaryDirectory() as tmp, patch('complete_purchase_flow.SITE', Path(tmp)):
            root = Path(tmp)
            (root/'today').mkdir()
            (root/'data.json').write_text(json.dumps({'updated_at':'2026-10-03T06:00:00+09:00','categories':{}}))
            (root/'price-observations.json').write_text(json.dumps({'products':{}}))
            for page in (root/'index.html',root/'today/index.html'):
                page.write_text('<html><head></head><body><main></main></body></html>')
            complete_purchase_flow.main()
            source = Path('scripts/purchase_tools.js').read_text()
            version = hashlib.sha256(source.encode()).hexdigest()[:12]
            self.assertIn(f'purchase-tools.js?v={version}',(root/'index.html').read_text())
            self.assertIn(f'purchase-tools.js?v={version}',(root/'today/index.html').read_text())
            self.assertEqual((root/'assets/purchase-tools.js').read_text(),source)

    def test_conditional_and_used_prices_are_rejected_without_removing_generic_coupon_ads(self):
        for condition in ['中古','定期便','初回限定','クーポン利用で']:
            self.assertEqual(category_rejection('tissue',f'箱ティッシュ150組60箱 {condition}'),'conditional_or_used_price')
        self.assertIsNone(category_rejection('tissue','箱ティッシュ150組60箱 500円OFFクーポン配布中'))

    def test_failed_history_read_cannot_reset_observations(self):
        with patch('price_observations.fetch_public', side_effect=OSError('timeout')):
            with self.assertRaisesRegex(RuntimeError, 'preserve history'):
                prepare()

    def test_first_history_404_is_allowed_but_other_prior_data_is_required(self):
        from price_observations import CACHE
        def first(path):
            if path == 'price-observations.json': raise urllib.error.HTTPError(path,404,'not found',{},None)
            return {'categories':{}} if path == 'data.json' else {'items':[]}
        with tempfile.TemporaryDirectory() as tmp, patch('price_observations.CACHE',Path(tmp)/'cache.json'), patch('price_observations.fetch_public',side_effect=first):
            prepare()
            self.assertNotIn('history',json.loads((Path(tmp)/'cache.json').read_text()))

    def test_box_rank_can_reverse_at_equal_groups(self):
        a={'name':'箱ティッシュ150組','metric':'box','unit_price':60,'price':3600}
        b={'name':'箱ティッシュ200組','metric':'box','unit_price':70,'price':4200}
        self.assertLess(a['unit_price'],b['unit_price'])
        self.assertGreater(comparison_unit('tissue',a)[1],comparison_unit('tissue',b)[1])
        self.assertEqual(quantity_label(a),'60箱')

    def test_ply_and_length_are_required_not_inferred(self):
        for name in ['トイレットペーパー170m48ロール','トイレットペーパーシングル100m120m48ロール','シングル ダブル120m48ロール']:
            self.assertIsNone(comparison_unit('toilet-paper',{'name':name,'metric':'roll','unit_price':100}))
        self.assertEqual(comparison_unit('toilet-paper',{'name':'シングル120m48ロール','metric':'roll','unit_price':120}),('シングル10m',10))

    def test_same_day_refresh_is_not_history_and_changed_spec_is_new_series(self):
        now=datetime(2026,10,3,20,tzinfo=ZoneInfo('Asia/Tokyo'))
        item={'name':'箱ティッシュ150組60箱','url':'https://item.rakuten.co.jp/shop/item/','metric':'box','evidence':'60箱','price':3600}
        p={'updated_at':'2026-10-03T06:00:00+09:00','categories':{'tissue':{'items':[item]}}}
        h=update(p,{},now);p['updated_at']='2026-10-03T19:00:00+09:00';h=update(p,{'history':h},now)
        self.assertIsNone(stats('tissue',item,h))
        p['updated_at']='2026-10-04T06:00:00+09:00';item['price']=3000
        h=update(p,{'history':h},datetime(2026,10,4,7,tzinfo=now.tzinfo))
        self.assertAlmostEqual(stats('tissue',item,h)['drop_percent'],100/6)
        self.assertIsNone(stats('tissue',{**item,'name':'箱ティッシュ200組60箱'},h))
        self.assertEqual(identity('tissue',item),identity('tissue',{**item,'price':1}))

    def test_invalid_history_never_invents_a_low_price(self):
        h={'products':{'abc':[{'at':'2026-10-03T00:00:00+09:00','price':-1},{'at':'2027-01-01T00:00:00+09:00','price':1}]}}
        result=update({'updated_at':'2026-10-03T06:00:00+09:00','categories':{}},{'history':h},datetime(2026,10,3,7,tzinfo=ZoneInfo('Asia/Tokyo')))
        self.assertEqual(result['products'],{})

    def test_recent_exposure_reduces_repeat_but_real_drop_can_override(self):
        rows=[{'id':str(i),'product_key':str(i),'discount':20-i,'unit_price':10,'observed_drop':0} for i in range(8)]
        history={'selections':[{'keys':['0','1','2','3','4']}] * 6}
        now=datetime(2026,10,3,6,tzinfo=ZoneInfo('Asia/Tokyo'))
        first=select_diverse(rows,rows,now,history)
        self.assertIn('5',[r['id'] for r in first])
        rows[0]['observed_drop']=20
        self.assertIn('0',[r['id'] for r in select_diverse(rows,rows,now,history)])

    def test_more_than_five_comparable_products_can_be_published(self):
        rows=[{'name':f'product{i}','unit_price':i+1,'confidence':.99,'metric':'box','review_count':1,'review_average':5,'postage':'送料込み'} for i in range(8)]
        self.assertEqual(len(choose_ranked_items(rows)[1]),8)

if __name__=='__main__':unittest.main()
