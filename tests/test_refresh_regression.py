"""Run the production catalog and recommendation generators repeatedly.

Only the Rakuten network boundary and clock are faked; acquisition, normalization,
quality, ranking, category/home/today rendering and X copy are the real code.
"""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
os.environ.setdefault('RAKUTEN_APPLICATION_ID', 'offline-test')
os.environ.setdefault('RAKUTEN_ACCESS_KEY', 'offline-test')
import build_realtime_products as builder
import build_site_entry as entry
import build_site_growth as growth
import build_daily_deals as deals
import diversify_daily_deals as diversify
import build_pipeline as pipeline
import post_buffer as morning
import post_buffer_evening as evening
import validate_product_quality as gate
from build_freshness import freshness_errors, provenance
from product_display import clean_display_name
from product_quality import REQUIRED
from sync_trend_search_chips import replace_product_chips
from test_product_quality import CASES

JST = ZoneInfo('Asia/Tokyo')
PREFIX = '【9/25 24時間限定★P5倍＋最大1,500円OFFクーポン】'


def raw_offer(cid, title, slot, index, **extra):
    return dict(itemName=PREFIX + title + f' 出品{chr(65+slot)}{chr(65+index)}',
                itemCode=f'shop:{cid}-{slot}-{index}', itemPrice=1000+index*150,
                postageFlag=0, shopName='fixture shop', reviewCount=10,
                reviewAverage=4.5, pointRate=1,
                affiliateUrl=f'https://hb.afl.rakuten.co.jp/hgc/fixture/?pc={cid}-{slot}-{index}',
                **extra)


class RefreshRegressionTests(unittest.TestCase):
    def test_morning_evening_next_day_and_shortage_rebuilds(self):
        previous_urls = set()
        old_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            os.chdir(tmp)
            stack.callback(os.chdir, old_cwd)
            stack.enter_context(patch.object(growth.core, 'OUTPUT_DIR', Path('site')))
            stack.enter_context(patch.object(entry.time, 'sleep'))
            stack.enter_context(patch.dict(os.environ, GITHUB_SHA='test-commit', GITHUB_RUN_ID='test-run'))
            for slot, (day, hour) in enumerate([(26,6),(26,19),(27,6),(28,6)]):
                now = datetime(2026,9,day,hour,tzinfo=JST)
                class Clock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return now
                requests = []
                def fetch(category, page):
                    cid = category['id']
                    requests.append((cid, page, category.get('_supplementary')))
                    good, bad = CASES[cid]
                    safe = [raw_offer(cid,good,slot,i) for i in range(5)]
                    wrong = raw_offer(cid,bad,slot,9)
                    if cid == 'tissue':
                        # Two base results on every refresh, plus duplicates,
                        # wrong-category and uncertain-shipping candidates.
                        if page == 2:
                            return [safe[0],safe[1],wrong]
                        if category.get('_supplementary'):
                            uncertain = dict(safe[2], itemCode='uncertain', postageFlag=1)
                            return [wrong,uncertain] + (safe[2:] if slot < 3 else [])
                        return [safe[0],wrong]
                    return [*safe,wrong]

                with ExitStack() as run, redirect_stdout(io.StringIO()):
                    for module in (entry,growth,builder,deals,diversify):
                        run.enter_context(patch.object(module,'datetime',Clock))
                    run.enter_context(patch.object(entry,'fetch_page',side_effect=fetch))
                    builder.main()
                    deals.main()
                    diversify.main()
                catalog=json.loads(Path('site/data.json').read_text())
                report=json.loads(Path('quality-report.json').read_text())
                today=json.loads(Path('site/today/data.json').read_text())
                social=json.loads(Path('site/social/latest.json').read_text())
                self.assertEqual(len(catalog['categories']),21)
                self.assertEqual(len(catalog['categories']['tissue']['items']),5 if slot < 3 else 2)
                self.assertTrue(any(cid=='tissue' and supplementary for cid,_,supplementary in requests))
                self.assertEqual(report['tissue']['acquisition']['baseline']['ranked'],2)
                self.assertGreater(sum(report['tissue']['reasons'].get(k,0) for k in ('accessory','wrong_use_or_type')),0)
                self.assertGreater(report['tissue']['reasons'].get('unconfirmed_shipping',0),0)
                self.assertEqual(today,social)
                self.assertFalse(freshness_errors(social,catalog,not_before=now))
                self.assertEqual(len(today['items']),5)
                self.assertTrue(all(PREFIX in p['product_name'] for p in today['items']))
                if slot == 3:
                    self.assertNotIn('tissue',[p['id'] for p in today['items']])
                urls={p['url'] for c in catalog['categories'].values() for p in c['items']}
                self.assertTrue(urls.isdisjoint(previous_urls))
                for path in Path('site').rglob('*.html'):
                    markup=path.read_text()
                    names=gate.Links();names.feed(markup)
                    self.assertTrue(all(clean_display_name(n)==n for n in names.display_names),str(path))
                    self.assertNotIn('IQOS',markup)
                    self.assertFalse(any(url in markup for url in previous_urls),str(path))
                original=deepcopy(social)
                self.assertNotIn('9/25',evening.build_evening_text(social))
                self.assertLessEqual(len(evening.build_evening_text(social)),280)
                self.assertIn('utm_source=x',morning.final_post_text(social))
                self.assertEqual(social,original)
                # The final product gate also checks static search examples.
                path=Path('site/products/index.html')
                path.write_text(replace_product_chips(path.read_text()))
                errors,stats=gate.validate()
                self.assertFalse(errors,errors)
                self.assertEqual(stats['products'],105 if slot < 3 else 102)
                previous_urls=urls

    def test_stale_or_unverified_recommendations_fail_closed(self):
        catalog={'updated_at':'2026-09-27T06:00:00+09:00','categories':{}}
        payload={**provenance(catalog),'generated_at':'2026-09-27T06:05:00+09:00','date':'2026-09-27'}
        self.assertFalse(freshness_errors(payload,catalog))
        self.assertTrue(freshness_errors(payload,catalog,not_before=datetime(2026,9,27,19,tzinfo=JST)))
        changed=deepcopy(catalog);changed['updated_at']='2026-09-27T19:00:00+09:00'
        self.assertTrue(freshness_errors(payload,changed))
        self.assertTrue(freshness_errors(payload,catalog,expected_run_id='other-run'))
        self.assertTrue(freshness_errors(payload,catalog,expected_sha='other-commit'))

    def test_quality_gate_detects_skipped_supplemental_fetch(self):
        catalog={'categories':{'tissue':{'items':[]}}}
        report={'tissue':{'published':0,'published_products':[], 'acquisition':{
            'baseline':{'ranked':0},'requests':[{'query':'ティッシュ','page':1}]}}}
        self.assertTrue(any('supplemental' in e for e in gate.validate_acquisition(catalog,report)))

    def test_pipeline_stops_before_manifest_when_quality_gate_fails(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'site').mkdir();(root/'site/stale.html').write_text('old recommendation')
            def run(args, **kwargs):
                self.assertFalse((root/'site/stale.html').exists())
                if args[-1].endswith('validate_product_quality.py'):
                    raise subprocess.CalledProcessError(1,args)
            with patch.object(pipeline,'ROOT',root), patch.object(pipeline.subprocess,'run',side_effect=run), patch.object(pipeline,'write_build_info') as manifest, redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.CalledProcessError):
                    pipeline.main()
                manifest.assert_not_called()

    def test_evening_product_name_is_cleaned_before_truncation(self):
        raw=PREFIX+'アタックZERO ドラム式専用 詰替2100g×6袋'
        payload={'date':'2026-09-27','items':[dict(id='laundry',name='洗濯洗剤',product_name=raw,discount=20,unit_price=50,metric_label='100g')]}
        text=evening.build_evening_text(payload)
        self.assertNotIn('9/25',text)
        # The optional line may be removed to meet X's existing length limit.
        if 'アタックZERO' in text:
            self.assertIn('ドラム式専用 詰替2100g×6袋',text)
        self.assertEqual(payload['items'][0]['product_name'],raw)

    def test_evening_refresh_boundary_handles_overnight_github_delay(self):
        delayed = datetime(2026,10,2,2,5,tzinfo=JST)
        on_time = datetime(2026,10,2,19,30,tzinfo=JST)
        self.assertEqual(
            evening.required_evening_refresh_time(delayed),
            datetime(2026,10,1,19,tzinfo=JST),
        )
        self.assertEqual(
            evening.required_evening_refresh_time(on_time),
            datetime(2026,10,2,19,tzinfo=JST),
        )

    def test_pr_and_production_share_the_full_pipeline_and_schedules(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('deploy-pages.yml','validate-pr.yml'):
            text=(root/'.github/workflows'/name).read_text()
            self.assertIn('uses: ./.github/actions/build-site',text)
            self.assertNotIn('run: python scripts/audit_product_candidates.py',text)
        self.assertIn('python scripts/build_pipeline.py',(root/'.github/actions/build-site/action.yml').read_text())
        self.assertEqual(pipeline.STEPS[0],'build_realtime_products')
        self.assertEqual(pipeline.STEPS[-2:],('validate_generated_site','validate_product_quality'))
        self.assertEqual(len(pipeline.STEPS),len(set(pipeline.STEPS)))
        self.assertTrue(all((root/'scripts'/f'{name}.py').is_file() for name in pipeline.STEPS))
        self.assertFalse(any(name.startswith('post_buffer') for name in pipeline.STEPS))
        for name,cron in [('deploy-pages.yml','0 21 * * *'),('refresh-before-evening-x.yml','0 10 * * *'),('evening-x.yml','30 10 * * *')]:
            self.assertIn(f'cron: "{cron}"',(root/'.github/workflows'/name).read_text())
        self.assertIn('deploy-pages.yml -f post_to_x=false',(root/'.github/workflows/refresh-before-evening-x.yml').read_text())

    def test_x_waits_for_evening_catalog_instead_of_reusing_morning(self):
        from test_product_quality import item
        catalog={'updated_at':'2026-09-27T06:00:00+09:00','categories':{
            cid:{'items':[],'metric':None} for cid in REQUIRED}}
        offers=[dict(item(price=price),url=f'https://hb.afl.rakuten.co.jp/hgc/test/{i}')
                for i,price in enumerate([800,1000,1100,1200,1300])]
        catalog['categories']['cotton-swab']={'name':'綿棒','metric':'piece','items':offers}
        morning_time=datetime(2026,9,27,6,5,tzinfo=JST)
        payload=deals.build_social(deals.build_rows(catalog),morning_time,catalog)
        fresh_catalog=deepcopy(catalog);fresh_catalog['updated_at']='2026-09-27T19:00:00+09:00'
        fresh_payload=deals.build_social(deals.build_rows(fresh_catalog),datetime(2026,9,27,19,5,tzinfo=JST),fresh_catalog)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                return datetime(2026,9,27,19,30,tzinfo=JST)
        responses=[payload,catalog,fresh_payload,fresh_catalog]
        def response(*args,**kwargs):
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        with patch.object(morning,'datetime',Clock), patch.object(morning.urllib.request,'urlopen',side_effect=response) as network, patch.object(morning.time,'sleep') as pause, patch.dict(os.environ,EXPECTED_BUILD_SHA='',EXPECTED_BUILD_RUN_ID=''), redirect_stdout(io.StringIO()):
            result=morning.fetch_today_social(not_before=datetime(2026,9,27,19,tzinfo=JST))
        self.assertEqual(result,fresh_payload)
        self.assertEqual(network.call_count,4)
        pause.assert_called_once()


if __name__ == '__main__':
    unittest.main()
