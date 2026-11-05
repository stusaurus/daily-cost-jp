import datetime as dt
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ga4_five_sites_readonly as g


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status
    def json(self):
        return self.payload


class Session:
    def __init__(self, error=None):
        self.calls, self.error = [], error
    def get(self, url, **kwargs):
        self.calls.append(('get', url, kwargs))
        if self.error:
            return Response({'error': {'details': [{'reason': self.error}]}}, 429 if self.error == 'RATE' else 403)
        if 'accountSummaries' in url:
            return Response({'accountSummaries': [{'displayName': 'PRIVATE ACCOUNT', 'propertySummaries': [{'property': 'properties/123'}]}]})
        if '/dataStreams' in url:
            return Response({'dataStreams': [{'name': 'properties/'+url.split('/properties/')[1].split('/')[0]+'/dataStreams/7',
                'type': 'WEB_DATA_STREAM', 'webStreamData': {'measurementId': 'G-Q1N14V276G', 'defaultUri': 'https://private.example/?secret=do-not-publish'}}]})
        return Response({'dimensions': [{'apiName': 'customEvent:operator_test'}]})
    def post(self, url, json, **kwargs):
        self.calls.append(('post', url, json))
        return Response({'dimensionHeaders': json['dimensions'], 'metricHeaders': json['metrics'],
                         'rowCount': 0, 'metadata': {'timeZone': 'Asia/Tokyo'}})


class FiveSitesTests(unittest.TestCase):
    def test_completed_windows(self):
        self.assertEqual(g.windows(dt.date(2026,10,23)), {'7':['2026-10-15','2026-10-21'], '28':['2026-09-24','2026-10-21']})

    def test_exact_host_url_and_path_filters_without_page_row_summing(self):
        f=g.filters('food-cost-jp', '7', '1')['andGroup']['expressions']
        values={x['filter']['fieldName']:x['filter']['stringFilter']['value'] for x in f}
        self.assertEqual(values['hostName'], 'stusaurus.github.io')
        self.assertEqual(values['pagePath'], '/food-cost-jp/')
        self.assertEqual(values['pageLocation'], 'https://stusaurus.github.io/food-cost-jp/')
        self.assertEqual(values['streamId'], '7')
        self.assertEqual(values['customEvent:operator_test'], '1')
        with self.assertRaises(ValueError):g.filters('food-cost-jp-evil')
        with self.assertRaises(ValueError):g.filters('food-cost-jp','7/../bad')

    def test_no_write_or_unapproved_google_endpoint(self):
        s=Session()
        for method,url in [('post',g.ADMIN+'properties/552907444'),('get','https://example.org/'),('get',g.ADMIN+'properties/1/accessBindings')]:
            with self.assertRaises(ValueError):g.api(s,method,url)
        self.assertEqual(s.calls,[])

    def test_disabled_service_and_permission_errors_are_distinct(self):
        for reason,expected in [('SERVICE_DISABLED','SERVICE_DISABLED'),('OTHER','PERMISSION_DENIED')]:
            r=g.api(Session(reason),'get',g.DATA+'properties/552907444/metadata')
            self.assertEqual(r['reason'],expected)
            self.assertEqual(r['http_status'],403)
            self.assertNotIn('error',r)

    def payload(self):
        return {'dimensionHeaders':[{'name':'eventName'},{'name':'customEvent:operator_test'}],
                'metricHeaders':[{'name':'eventCount'}], 'rowCount':1, 'metadata':{'timeZone':'Asia/Tokyo'},
                'rows':[{'dimensionValues':[{'value':'affiliate_click'},{'value':'(not set)'}], 'metricValues':[{'value':'3'}]}]}

    def test_unknown_test_flag_is_retained_not_non_operator(self):
        r=g.parse_report(self.payload(),['eventName','customEvent:operator_test'],'eventCount')
        self.assertEqual(r['rows'],[{'dimensions':['affiliate_click','(not set)'],'count':3}])

    def test_thresholding_sampling_truncation_withhold_counts(self):
        for key,value in [('subjectToThresholding',True),('dataLossFromOtherRow',True),('samplingMetadatas',[{'samplesReadCount':'5'}])]:
            p=self.payload();p['metadata'][key]=value
            r=g.parse_report(p,['eventName','customEvent:operator_test'],'eventCount')
            self.assertEqual(r['status'],'WITHHELD_DATA_QUALITY');self.assertNotIn('rows',r)
        p=self.payload();p['rowCount']=2
        self.assertEqual(g.parse_report(p,['eventName','customEvent:operator_test'],'eventCount')['status'],'WITHHELD_DATA_QUALITY')

    def test_calendar_mismatch_is_not_zero(self):
        p=self.payload();p['metadata']['timeZone']='America/Los_Angeles'
        r=g.parse_report(p,['eventName','customEvent:operator_test'],'eventCount')
        self.assertEqual(r['status'],'WITHHELD_PROPERTY_TIMEZONE');self.assertNotIn('rows',r)

    def test_observed_empty_and_invalid_headers_are_distinct(self):
        p=self.payload();p.update(rowCount=0,rows=[])
        self.assertEqual(g.parse_report(p,['eventName','customEvent:operator_test'],'eventCount')['status'],'NO_REPORTED_ROWS')
        self.assertEqual(g.parse_report(p,['sessionSource'],'eventCount')['status'],'INVALID_HEADERS')

    def test_config_mapping_is_not_fabricated_stream_verification(self):
        m=g.mappings(['G-GFVSZ8YDQ5'],{})[0]
        self.assertIsNone(m['stream_id']);self.assertIn('UNVERIFIED',m['basis'])
        self.assertEqual(g.mappings(['G-6STQ5HXRDH'],{})[0]['property_id'],'558239521')
        self.assertEqual(g.mappings(['G-UNKNOWN999'],{}),[])

    def test_discovery_redacts_unrelated_names_and_uris(self):
        a,streams=g.discover(Session(),{'G-Q1N14V276G'})
        out=json.dumps([a,streams]);self.assertNotIn('PRIVATE ACCOUNT',out);self.assertNotIn('private.example',out)
        self.assertEqual(g.mappings(['G-Q1N14V276G'],{'123':streams['123']})[0]['property_id'],'123')

    def test_complete_collect_and_operator_scope_queries(self):
        s=Session()
        def public(site):
            return {'status':'OBSERVED','measurement_ids':['G-GFVSZ8YDQ5' if site in g.SITES[:3] else 'G-6STQ5HXRDH']}
        r=g.collect(s,dt.date(2026,10,23),public)
        self.assertEqual([x['status'] for x in r['sites']],['QUERIED']*5)
        self.assertEqual(len([c for c in s.calls if c[0]=='post']),40)
        for _,url,p in (c for c in s.calls if c[0]=='post'):
            self.assertTrue(url.endswith(':runReport'))
            if p['metrics']==[{'name':'sessions'}]:self.assertEqual(p['dimensions'],[{'name':'sessionDefaultChannelGroup'}])
        self.assertEqual(r['sites'][0]['periods']['28']['events']['status'],'NO_REPORTED_ROWS')

    def test_stop_on_rate_limit_before_other_reads(self):
        s=Session('RATE')
        r=g.collect(s,dt.date(2026,10,23),lambda _: {'measurement_ids':['G-GFVSZ8YDQ5']})
        self.assertEqual(r['status'],'RATE_LIMITED_STOP');self.assertEqual(len(s.calls),1)

    def test_known_property_permission_failure_keeps_counts_unavailable(self):
        class Denied(Session):
            def get(self,url,**kwargs):
                if url.endswith('properties/558239521/metadata'):
                    self.calls.append(('get',url,kwargs))
                    return Response({'error':{}},403)
                return super().get(url,**kwargs)
        r=g.collect(Denied(),dt.date(2026,10,23),lambda _: {'measurement_ids':['G-6STQ5HXRDH']})
        for site in r['sites']:
            self.assertEqual(site['status'],'DATA_API_UNAVAILABLE')
            self.assertEqual(site['data_api_metadata']['reason'],'PERMISSION_DENIED')
            self.assertEqual(site['periods'],{})

    def test_food_guide_is_an_exact_saved_inspection_target(self):
        import scripts.gsc_six_sites_diagnostics as existing
        self.assertIn('/guides/pack-rice-24-servings-cost/',existing.TARGET_PATHS['食品'])



class WeeklyFunnelEvidenceTests(unittest.TestCase):
    def test_operator_flags_stay_distinct_from_real_people(self):
        rows={'status':'OBSERVED_ROWS','rows':[
            {'dimensions':['affiliate_click','0'],'count':3},
            {'dimensions':['affiliate_click','1'],'count':2},
            {'dimensions':['affiliate_click','(not set)'],'count':4},
            {'dimensions':['page_view','0'],'count':90}]}
        e=g.event_evidence(rows,'affiliate_click',True)
        self.assertEqual((e['count'],e['marked_operator'],
                          e['marked_non_operator_unverified'],e['unclassified']),
                         (9,2,3,4))
        self.assertNotIn('conversion_rate',e)
        self.assertNotIn('users',e)

    def test_unregistered_operator_is_unknown(self):
        e=g.event_evidence({'status':'OBSERVED_ROWS','rows':[
            {'dimensions':['affiliate_click'],'count':12}]},
            'affiliate_click',False)
        self.assertEqual(e['unclassified'],12)
        self.assertEqual(e['marked_non_operator_unverified'],0)

    def test_no_rows_and_withheld_are_not_zeros(self):
        for status in ('NO_REPORTED_ROWS','WITHHELD_DATA_QUALITY',
                       'UNAVAILABLE','WITHHELD_PROPERTY_TIMEZONE'):
            e=g.event_evidence({'status':status},'affiliate_click',True)
            self.assertEqual(e['status'],status)
            self.assertNotIn('count',e)
        e=g.event_evidence({'status':'OBSERVED_ROWS','rows':[
            {'dimensions':['page_view','0'],'count':5}]},'affiliate_click',True)
        self.assertEqual(e['status'],'EVENT_NOT_REPORTED')
        self.assertNotIn('count',e)

    def test_duplicate_negative_and_bad_dimensions_rejected(self):
        cases=[
            [{'dimensions':['affiliate_click','0'],'count':2},
             {'dimensions':['affiliate_click','0'],'count':2}],
            [{'dimensions':['affiliate_click','0'],'count':-2}],
            [{'dimensions':['affiliate_click'],'count':2}]]
        for rows in cases:
            e=g.event_evidence({'status':'OBSERVED_ROWS','rows':rows},
                               'affiliate_click',True)
            self.assertNotEqual(e['status'],'OBSERVED_EVENT_ROWS')
        self.assertEqual(g.event_evidence(
            {'status':'OBSERVED_ROWS','rows':cases[1]},
            'affiliate_click',None)['status'],'OPERATOR_METADATA_UNAVAILABLE')

    def test_all_five_sites_and_periods_preserve_observed_semantics(self):
        data={'periods':g.windows(dt.date(2026,11,5)),'sites':[
            {'site':site,'status':'QUERIED',
             'data_api_metadata':{'operator_registered':True},
             'periods':{p:{'events':{'status':'OBSERVED_ROWS','rows':[
                 {'dimensions':['affiliate_click','0'],'count':1}]}}
                        for p in ('7','28')}} for site in g.SITES]}
        data['funnel_event_coverage']=g.funnel_event_coverage(data)
        self.assertEqual(set(data['funnel_event_coverage']),set(g.SITES))
        self.assertEqual(data['funnel_event_coverage']['sotojitaku']['7']
                         ['affiliate_click']['count'],1)
        self.assertEqual(data['funnel_event_coverage']['baby-cost-jp']['28']
                         ['page_view']['status'],'EVENT_NOT_REPORTED')
        md=g.markdown(data)
        self.assertIn('## 5サイトの商品導線イベント',md)
        self.assertIn('非運営者表示1',md)
        self.assertIn('楽天確定成果は未接続',md)

    def test_existing_monday_read_only_runner_is_sole_automation(self):
        src=(Path(__file__).resolve().parents[1]
             /'.github/workflows/gsc-six-sites-diagnostics.yml').read_text()
        self.assertIn("github.event_name == 'schedule' || (github.event_name == 'workflow_dispatch'",src)
        self.assertIn('inputs.include_five_site_ga4',src)
        self.assertIn('steps.ga4_evidence.outcome',src)
        self.assertIn('continue-on-error: true',src)
        self.assertEqual(src.count("cron: '45 0 * * 1'"),1)
        self.assertNotIn('analytics.write',src)


if __name__=='__main__':unittest.main()
