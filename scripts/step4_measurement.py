"""28-day aggregate evidence; independent sources are never joined as users."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from ga4_page_diagnostics import path_from_location, FOCUS_PAGES
from ga4_three_day_report import check_response
from report_daily_clicks import aggregate
EVENTS=('page_view','realtime_product_search','product_result_click','affiliate_click','purchase_search_diagnostics','purchase_comparison_open','purchase_saved_open','purchase_save_add','purchase_compare_add')


def count(value):return value if type(value) is int and value>=0 else None


def aggregate_events(rows,period,registered,complete=True):
    start,end=[dt.date.fromisoformat(x) for x in period]
    if (end-start).days!=27:raise ValueError('Expected 28 complete calendar days')
    groups={p:{e:{'non_operator':0,'operator':0,'unknown':0} for e in EVENTS} for p in FOCUS_PAGES}
    observed=set()
    for row in rows:
        day,event,location,flag,n=row
        d=dt.date.fromisoformat(day)
        if not start<=d<=end or event not in EVENTS or count(n) is None:raise ValueError('Invalid aggregate event input')
        page=path_from_location(location)
        if page not in groups:continue
        bucket=aggregate([{'eventName':'affiliate_click','pageLocation':location,'operator_test':flag if registered else '', 'eventCount':str(n)}])
        for key,target in [('production_non_operator','non_operator'),('production_operator','operator'),('production_unknown','unknown')]:groups[page][event][target]+=bucket[key]
        if event=='page_view':observed.add(day)
    return {'source':'GA4 Data API','status':'AGGREGATES_ONLY' if complete else 'UNAVAILABLE','period':period,'operator_dimension_registered':registered,
            'pageview_days_observed':len(observed),'expected_days':28,'response_complete':complete,'events':groups if complete else None,
            'missing_days_interpretation':'NO_ROW_IS_NOT_PROVEN_TRACKING_FAILURE','diagnostic_cause_breakdown':'NOT_QUERIED_CUSTOM_DIMENSIONS',
            'purpose_breakdown':'NOT_QUERIED_CUSTOM_DIMENSIONS','sales_status':'NOT_CONNECTED','conversion_rate':None}


def report(page_diagnostics=None,event_report=None,gsc=None):
    r={'source':'daily-cost step4 measurement v1','sales_status':'NOT_CONNECTED','sales_improvement':'UNVERIFIED','funnel_user_join':'NOT_POSSIBLE',
       'ga4_status':'UNAVAILABLE','period':None,'observed_days':None,'expected_days':28,'pages':[], 'event_report_status':'UNAVAILABLE',
       'new_event_counts':None,'recommendation_decision':'INVESTIGATE','evaluation':'Compare equal 28-day windows after activation; exclude operator/unknown; report counts, coverage and samples separately. Clicks per pageview are event ratios, not users or sales.'}
    if isinstance(page_diagnostics,dict) and page_diagnostics.get('source')=='GA4 Data API':
        r['ga4_status']=page_diagnostics.get('status','UNAVAILABLE');r['period']=page_diagnostics.get('period_last_28')
        r['observed_days']=count(page_diagnostics.get('pageview_dates_observed_in_last_28'))
        for p in page_diagnostics.get('pages',[]):
            if not isinstance(p,dict) or p.get('page') not in FOCUS_PAGES:continue
            s=p.get('periods',{}).get('last_28',{});clicks=s.get('clicks',{})
            views=count(s.get('pageviews'));real=count(clicks.get('production_non_operator'));unknown=count(clicks.get('production_unknown'))
            r['pages'].append({'path':p['page'],'pageviews_all_operator_scopes':views,'non_operator_clicks_provisional':real if page_diagnostics.get('operator_dimension_registered') is True else None,
                'operator_clicks':count(clicks.get('production_operator')),'unknown_clicks':unknown,'real_user_pageviews':None,'sample_status':'INSUFFICIENT_FOR_AUTOMATIC_OPTIMIZATION',
                'click_ratio':None})
    if isinstance(event_report,dict) and event_report.get('source')=='GA4 Data API':
        r['event_report_status']=event_report.get('status','UNAVAILABLE')
        # Whitelist paths, event names, counts only. Never publish original API rows.
        if event_report.get('response_complete') is True and isinstance(event_report.get('events'),dict):
            r['new_event_counts']={p:{e:{k:count(v.get(k)) for k in ('non_operator','operator','unknown')} for e,v in es.items() if e in EVENTS and isinstance(v,dict)} for p,es in event_report['events'].items() if p in FOCUS_PAGES and isinstance(es,dict)}
            r['event_period']=event_report.get('period');r['event_observed_days']=count(event_report.get('pageview_days_observed'))
    r['gsc_status']='INDEPENDENT_NOT_JOINED' if isinstance(gsc,dict) else 'UNAVAILABLE'
    r['periods_aligned']=False
    return r


def fetch_events(include_prior=False):
    prop=os.environ['GA4_PROPERTY_ID']
    if not prop.isdigit():raise ValueError('Invalid GA4 property')
    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension,Metric,RunReportRequest,Filter,FilterExpression
    credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    client=BetaAnalyticsDataClient(credentials=credentials);property_='properties/'+prop
    meta=client.get_metadata(name=property_+'/metadata')
    registered=any(d.api_name=='customEvent:operator_test' for d in meta.dimensions)
    end=dt.datetime.now(ZoneInfo('Asia/Tokyo')).date()-dt.timedelta(days=2);start=end-dt.timedelta(days=27)
    period=[start.isoformat(),end.isoformat()]
    fetch_start=start-dt.timedelta(days=28) if include_prior else start
    raw=client.run_report(RunReportRequest(property=property_,date_ranges=[DateRange(start_date=fetch_start.isoformat(),end_date=period[1])],
       dimensions=[Dimension(name='date'),Dimension(name='eventName'),Dimension(name='pageLocation')]+([Dimension(name='customEvent:operator_test')] if registered else []),
       metrics=[Metric(name='eventCount')],dimension_filter=FilterExpression(filter=Filter(field_name='eventName',in_list_filter=Filter.InListFilter(values=list(EVENTS)))),limit=100000))
    rows=[]
    for row in check_response(raw):
        v=[d.value for d in row.dimension_values];day=dt.datetime.strptime(v[0],'%Y%m%d').date().isoformat()
        rows.append((day,v[1],v[2],v[3] if registered else '',int(row.metric_values[0].value)))
    current=aggregate_events([r for r in rows if r[0]>=period[0]],period,registered)
    if include_prior:
        prior=[fetch_start.isoformat(),(start-dt.timedelta(days=1)).isoformat()]
        return current,aggregate_events([r for r in rows if r[0]<period[0]],prior,registered)
    return current


def read(path):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return None


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');args=parser.parse_args()
    root=Path('audit-results');root.mkdir(exist_ok=True)
    events=read(root/'step4-events-28d.json')
    if args.fetch:
        try:
            events,prior=fetch_events(include_prior=True)
            (root/'step4-events-prior-28d.json').write_text(json.dumps(prior,ensure_ascii=False,indent=2))
        except Exception:
            # Never log credentials, API URLs, raw query or arbitrary errors.
            events={'source':'GA4 Data API','status':'UNAVAILABLE','response_complete':False}
        (root/'step4-events-28d.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
    r=report(read(root/'ga4-page-diagnostics.json'),events,read(root/'gsc-search-pilot.json'))
    (root/'step4-measurement.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    (root/'step4-measurement.md').write_text('# STEP 4：28日購買導線の測定\n\n'
       +f"- GA4：{r['ga4_status']}。期間：{r['period']}。観測日：{r['observed_days']}/28。\n"
       +f"- 導線イベント：{r['event_report_status']}。一般利用者・運営者・不明を別集計。\n"
       +'- GA4表示数には運営者が含まれる場合がある。クリック/表示から成約率を推定しない。\n'
       +'- GSCクリックは別データ。同じユーザーの購入導線として結合しない。\n'
       +'- 楽天確定成果：未接続。売上改善は未確認。\n'
       +'- 実施前基準値は同run JSON。公開後は同じ28日窓、観測日、テスト区分、商品更新日時を記録し比較。少数では最適化しない。\n',encoding='utf-8')
    print('STEP4 measurement:',r['ga4_status'],'events:',r['event_report_status'],'sales NOT_CONNECTED')
if __name__=='__main__':main()
