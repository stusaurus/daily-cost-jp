import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import step6_seo_audit as a
import step6_seo_content as c
import step6_effects as e
from step6_gsc_sitemaps import collect_sitemaps
from step6_verification import validate_receipt

NOW=dt.datetime(2026,10,11,14,30,tzinfo=dt.timezone.utc)
SHA='a'*40
CONFIG=json.dumps({'version':c.VERSION,'pages':dict.fromkeys(c.REGISTRY,False)},indent=2)+'\n'


def gsc():
    from gsc_readonly_pilot import periods
    m={'impressions':114,'clicks':2,'ctr':round(2/114,6),'position':12.93}
    return {'source':'Search Console Search Analytics API','site_property':a.SITE,'status':'PROVISIONAL',
            'generated_at_utc':NOW.isoformat(),'windows':periods(NOW.date()),
            'pages':[dict(path=f'/categories/{cid}/',last_28=m.copy(),prior_28=m.copy(),last_7=None,prior_7=None) for cid in c.REGISTRY]}


def technical():
    return {'status':'PASS','pages':[{'path':f'/categories/{cid}/','status':'PASS',
             'title':c.REGISTRY[cid][0]+'の価格比較','has_comparison_help':False,
             'comparison_context_verified':True,'existing_faq_present':True,'faq_navigation_complete':False} for cid in c.REGISTRY]}


class Audit(unittest.TestCase):
    def test_actual_windows_and_priority_evidence(self):
        r=a.analyze(technical(),gsc(),CONFIG,SHA,NOW)
        self.assertEqual(r['status'],'GROUNDED_HYPOTHESES')
        self.assertEqual(r['candidates'][0]['path'],'/categories/laundry/')
        p=r['candidates'][0]['proposals'][0]
        self.assertEqual(p['classification'],'HUMAN_ONLY')
        self.assertEqual(p['source_target'],c.TARGET)
        self.assertFalse(p['publication_authorized'])
        self.assertEqual(r['sales_status'],'NOT_CONNECTED')
        self.assertEqual(a.candidate(r,CONFIG,SHA,NOW)['recipe'],c.recipe('laundry'))

    def test_missing_stale_future_and_wrong_property_never_zero(self):
        for src in [None,{},dict(gsc(),status='NOT_CONNECTED'),dict(gsc(),site_property='https://evil.invalid/'),
                    dict(gsc(),generated_at_utc='2020-01-01T00:00:00+00:00'),dict(gsc(),generated_at_utc='2099-01-01T00:00:00+00:00')]:
            out=a.analyze(technical(),src,CONFIG,SHA,NOW)
            self.assertEqual(out['candidates'],[])
            self.assertIsNone(out['site_aggregates'])

    def test_low_sample_and_unknown_queries_do_not_authorize_titles(self):
        src=gsc();src['pages'][0]['last_28']={'clicks':0,'impressions':8,'ctr':0,'position':8}
        out=a.analyze(technical(),src,CONFIG,SHA,NOW)
        laundry=next(p for p in out['candidates'] if 'laundry' in p['path'])
        self.assertEqual(laundry['proposals'],[])
        self.assertEqual(laundry['title_meta_h1_proposals'],'DEFERRED_WITHOUT_VERIFIED_QUERY_INTENT')
        self.assertIsNone(laundry['descriptive_change']['7'])

    def test_malformed_infinite_counts_and_unequal_periods_block(self):
        for mutate in [lambda x:x['pages'][0]['last_28'].update(position=float('nan')),
                       lambda x:x['pages'][0]['last_28'].update(clicks=115),
                       lambda x:x['pages'][0]['last_28'].update(ctr=.9),
                       lambda x:x['windows']['last_28'].__setitem__(0,'2026-10-01'),
                       lambda x:x.update(status='TOP_ROW_COVERAGE_UNCERTAIN')]:
            src=gsc();mutate(src)
            self.assertFalse(a.validated_gsc(src,NOW))

    def test_duplicate_pages_block(self):
        src=gsc();src['pages'].append(src['pages'][0].copy())
        self.assertFalse(a.validated_gsc(src,NOW))

    def test_failed_audit_complete_navigation_and_existing_help_block(self):
        for key,val in [('status','REVIEW'),('has_comparison_help',True),('comparison_context_verified',False),
                        ('existing_faq_present',False),('faq_navigation_complete',True)]:
            tech=technical()
            for p in tech['pages']:p[key]=val
            out=a.analyze(tech,gsc(),CONFIG,SHA,NOW)
            self.assertTrue(all(not p['proposals'] for p in out['candidates']))

    def test_forged_recipe_and_remote_strings_are_not_executed(self):
        src=gsc();src['top_queries']=[{'query':'$(touch /tmp/unsafe); secret@example.invalid'}]
        r=a.analyze(technical(),src,CONFIG,SHA,NOW)
        for p in r['candidates']:p['proposals']=[{'recipe':'arbitrary-executable-code'}]
        out=a.candidate(r,CONFIG,SHA,NOW)
        self.assertEqual(out['recipe'],c.recipe('laundry'))
        self.assertNotIn('touch',json.dumps(r))
        self.assertNotIn('secret@',json.dumps(r))
        self.assertIsNone(a.candidate(r,CONFIG,'b'*40,NOW))

    def test_sitemap_scope_xml_duplicates_and_limits(self):
        def xml(loc):return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+v+'</loc></url>' for v in loc)+'</urlset>'
        self.assertEqual(a.sitemap_urls(xml([a.SITE])),[a.SITE])
        for raw in [xml([a.SITE,a.SITE]),xml(['https://evil.invalid/']),xml([a.SITE+'../other/']),
                    '<!DOCTYPE x>'+xml([a.SITE]),'<urlset/>']:
            with self.assertRaises(ValueError):a.sitemap_urls(raw)

    def test_safe_redirects_query_and_paths(self):
        for url in ['http://stusaurus.github.io/daily-cost-jp/',a.SITE+'?key=x',a.SITE+'%2e%2e/',
                    'https://stusaurus.github.io/other/','https://u@stusaurus.github.io/daily-cost-jp/',a.SITE+'x#f']:
            self.assertFalse(a.safe_url(url))

    def test_robots_noindex_canonical_h1_and_viewport(self):
        from urllib.robotparser import RobotFileParser
        robots=RobotFileParser();robots.parse(['User-agent: *','Disallow: /'])
        text='<title>x</title><meta name="description" content="y"><meta name="robots" content="noindex"><h1>x</h1><h1>y</h1>'
        row=a.inspect_page(a.SITE,{'status':'OBSERVED','http_status':200,'text':text},robots)
        self.assertTrue({'ROBOTS_BLOCKED','UNEXPECTED_NOINDEX','CANONICAL_MISMATCH_OR_DUPLICATE','H1_COUNT','MOBILE_VIEWPORT_MISSING'}<=set(row['issues']))

    def test_full_audit_broken_fragment_link_and_duplicate_metadata(self):
        xml='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+a.SITE+'</loc></url><url><loc>'+a.SITE+'categories/</loc></url></urlset>'
        def get(url):
            text=xml if url.endswith('sitemap.xml') else 'User-agent: *\nAllow: /\nSitemap: '+a.SITE+'sitemap.xml' if url.endswith('robots.txt') else '<title>duplicate</title><meta name="description" content="duplicate"><meta name="viewport" content="width=device-width"><link rel="canonical" href="'+url+'"><h1>x</h1><a href="'+a.SITE+'categories/#missing">x</a>'
            return {'status':'OBSERVED','http_status':200,'text':text}
        out=a.audit(get)
        self.assertEqual(out['status'],'REVIEW_OR_UNKNOWN')
        self.assertIn('DUPLICATE_TITLE',out['pages'][0]['issues'])
        self.assertIn('INTERNAL_ANCHOR_MISSING',out['pages'][0]['issues'])
        self.assertEqual(out['page_index_status'],'UNCONFIRMED')

    def test_discovery_api_failure_unknown(self):
        out=a.audit(lambda u:{'status':'UNAVAILABLE','http_status':None})
        self.assertEqual(out['status'],'REVIEW_OR_UNKNOWN')
        self.assertEqual(out['pages'],[])


class FixedContent(unittest.TestCase):
    def test_one_page_fixed_policy_and_idempotence(self):
        revised=c.repair(CONFIG,c.recipe('laundry'))
        self.assertEqual(c.policy(revised)['pages'],{'laundry':True,'tissue':False,'toilet-paper':False})
        self.assertIsNone(c.repair(revised,c.recipe('laundry')))
        self.assertIsNone(c.repair(CONFIG,'run-arbitrary-source'))

    def test_invalid_policy_no_additional_urls_or_copy(self):
        for obj in [dict(version=c.VERSION,pages={'laundry':True}),dict(version=c.VERSION,pages=dict.fromkeys(c.REGISTRY,'false')),
                    dict(version='bad',pages=dict.fromkeys(c.REGISTRY,False))]:
            with self.assertRaises(ValueError):c.policy(json.dumps(obj))

    def test_generated_content_source_preserves_all_other_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'categories/laundry/index.html';p.parent.mkdir(parents=True)
            original='<html><head><title>x</title><link rel="canonical" href="'+a.SITE+'categories/laundry/"></head><body><main><h1>x</h1><section id="laundry">same exact ranking/price/URL</section></main></body></html>'
            p.write_text(original)
            cfg=c.policy(c.repair(CONFIG,c.recipe('laundry')))
            self.assertEqual(c.apply(root,cfg),['laundry'])
            self.assertEqual(p.read_text().replace(c.markup('laundry'),''),original)
            self.assertEqual(c.apply(root,cfg),[])

    def test_lastmod_not_guessed_and_repeated_build_stable(self):
        script=Path(__file__).resolve().parents[1]/'scripts/generate_seo_files.py'
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)/'site';site.mkdir();(site/'index.html').write_text('same')
            env=dict(os.environ,SITE_URL=a.SITE)
            subprocess.run([sys.executable,str(script)],cwd=d,env=env,check=True,stdout=subprocess.DEVNULL)
            first=(site/'sitemap.xml').read_bytes()
            subprocess.run([sys.executable,str(script)],cwd=d,env=env,check=True,stdout=subprocess.DEVNULL)
            self.assertEqual(first,(site/'sitemap.xml').read_bytes())
            self.assertNotIn(b'lastmod',first)

    def test_missing_quality_browser_receipt_blocks(self):
        self.assertFalse(validate_receipt(None,{}))
        self.assertFalse(validate_receipt({'status':'PASS'},{'base_sha':SHA,'candidate_hash':'x'}))


class Measurement(unittest.TestCase):
    def test_sitemap_registration_get_only_and_index_unknown(self):
        session=Mock();session.get.return_value.status_code=200
        session.get.return_value.json.return_value={'sitemap':[{'path':a.SITE+'sitemap.xml','errors':'0','lastDownloaded':'2026-10-10T00:00:00Z'}]}
        r=collect_sitemaps(session)
        self.assertEqual(r['status'],'OBSERVED');self.assertEqual(r['page_index_status'],'UNCONFIRMED')
        session.post.assert_not_called();session.put.assert_not_called()
        self.assertTrue(session.get.call_args.args[0].endswith('/sitemaps'))

    def test_sitemap_api_failure_does_not_invent_indexing(self):
        session=Mock();session.get.return_value.status_code=403
        self.assertEqual(collect_sitemaps(session)['status'],'UNAVAILABLE')

    def test_release_windows_same_length_exclude_publication_day(self):
        row={'published_on':'2026-10-11'}
        self.assertIsNone(e.windows(row,dt.date(2026,10,20),7))
        w=e.windows(row,dt.date(2026,11,11),28)
        self.assertEqual(w,{'after':['2026-10-12','2026-11-08'],'before':['2026-09-13','2026-10-10']})

    def test_no_publication_no_api_requests(self):
        session=Mock()
        with patch.object(Path,'read_text',return_value='{"releases":[]}'):
            out=e.collect(session,NOW.date())
        self.assertEqual(out['status'],'NO_CONFIRMED_PUBLICATION');session.post.assert_not_called()

    def test_low_sample_missing_and_failed_data_pending(self):
        ledger=json.dumps({'releases':[{'path':'/categories/laundry/','recipe':c.recipe('laundry'),'published_on':'2026-08-01','commit':SHA}]})
        session=Mock();session.post.return_value.status_code=200
        for response in [{}, {'rows':[{'clicks':1,'impressions':10,'ctr':.1,'position':12}]}]:
            session.post.return_value.json.return_value=response
            with patch.object(Path,'read_text',return_value=ledger):out=e.collect(session,NOW.date())
            self.assertEqual(out['evaluation'],'評価保留')
            self.assertFalse(out['cross_source_user_join'])
            self.assertEqual(out['sales_status'],'NOT_CONNECTED')
            self.assertIn(out['releases'][0]['comparisons']['28']['status'],['MISSING_ROWS_UNKNOWN','LOW_SAMPLE'])

    def test_invalid_release_ledger_rejected(self):
        with self.assertRaises(ValueError):e.releases('{"releases":[{"path":"/evil/"}]}')

    def test_workflow_reuses_single_publisher_and_switch(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/ga4-three-day-analysis.yml').read_text()
        self.assertEqual(text.count('step2.py publish'),1)
        self.assertIn("if: vars.STEP2_ENABLE_PR_WRITES == 'true'",text)
        self.assertIn('cron:',text)
        self.assertNotIn('Indexing API',text)


if __name__=='__main__':unittest.main()
