#!/usr/bin/env python3
"""Public-safe, readonly calendar-month Google aggregates; NO Rakuten revenue."""
import calendar
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
from ga4_three_day_report import check_response
from report_daily_clicks import aggregate
from gsc_readonly_pilot import SITE, API_ROOT, PROPERTY_SCOPE, aggregate_response

SOURCE='step7-google-monthly-v1'

def bounds(today):
    end=today.replace(day=1)-dt.timedelta(days=1)
    return end.replace(day=1),end

def empty(start,end):
    return {'source':SOURCE,'site':SITE,'month':start.strftime('%Y-%m'),
            'period':[start.isoformat(),end.isoformat()],
            'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'status':'UNKNOWN','gsc':{'status':'NOT_CONNECTED','calendar':'America/Los_Angeles','metrics':None,'observed_days':None},
            'ga4':{'status':'NOT_CONNECTED','calendar':'Asia/Tokyo','pageviews_observed':None,'observed_days':None,
                   'operator_dimension_registered':None,'affiliate_clicks_observed':{k:None for k in ('non_operator','operator','unknown')}},
            'cross_source_user_join':False,'revenue_status':'NOT_CONNECTED'}

def ga4_aggregate(click_rows,view_rows,start,end,registered):
    expected={start+dt.timedelta(days=i) for i in range((end-start).days+1)}
    totals={k:None for k in ('non_operator','operator','unknown')};days=set();views=None
    for date,location,flag,value in click_rows:
        if date not in expected or type(value) is not int or value<0:raise ValueError('Invalid aggregate row')
        buckets=aggregate([{'eventName':'affiliate_click','pageLocation':location,
                            'operator_test':flag if registered else '', 'eventCount':str(value)}])
        for label,key in [('non_operator','production_non_operator'),('operator','production_operator'),('unknown','production_unknown')]:
            if buckets[key]:totals[label]=(totals[label] or 0)+buckets[key]
    seen=set()
    for date,path,value in view_rows:
        if date not in expected or type(value) is not int or value<0 or not path.startswith('/daily-cost-jp/') or (date,path) in seen:
            raise ValueError('Invalid view aggregate row')
        seen.add((date,path));days.add(date);views=(views or 0)+value
    return {'status':'OBSERVED_ROWS' if len(days)==len(expected) else 'PARTIAL_OBSERVATIONS',
            'calendar':'Asia/Tokyo','pageviews_observed':views,'observed_days':len(days),
            'operator_dimension_registered':registered,'affiliate_clicks_observed':totals}

def fetch_ga4(start,end):
    if end>dt.datetime.now(ZoneInfo('Asia/Tokyo')).date()-dt.timedelta(days=2):
        result=empty(start,end)['ga4'];result['status']='WAIT_FOR_FINAL_DATA';return result
    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange,Dimension,Metric,RunReportRequest,Filter,FilterExpression,FilterExpressionList
    prop=os.environ['GA4_PROPERTY_ID']
    if not prop.isdigit():raise ValueError('Invalid property')
    credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    client=BetaAnalyticsDataClient(credentials=credentials);resource='properties/'+prop
    registered=any(d.api_name=='customEvent:operator_test' for d in client.get_metadata(name=resource+'/metadata').dimensions)
    dates=[DateRange(start_date=start.isoformat(),end_date=end.isoformat())]
    def request(dimensions,metric,filters):
        response=client.run_report(RunReportRequest(property=resource,date_ranges=dates,
            dimensions=[Dimension(name=x) for x in dimensions],metrics=[Metric(name=metric)],dimension_filter=filters,limit=100000))
        if getattr(response.metadata,'time_zone','')!='Asia/Tokyo':raise ValueError('Property calendar unknown')
        if getattr(response.metadata,'sampling_metadatas',[]) or getattr(response.metadata,'data_truncation_reasons',[]) or getattr(response.metadata,'empty_reason',''):
            raise ValueError('Incomplete or sampled Google response')
        return check_response(response)
    clicks=[]
    for row in request(['date','pageLocation']+(['customEvent:operator_test'] if registered else []),'eventCount',
        FilterExpression(filter=Filter(field_name='eventName',string_filter=Filter.StringFilter(value='affiliate_click',match_type=Filter.StringFilter.MatchType.EXACT)))):
        values=[d.value for d in row.dimension_values]
        clicks.append((dt.datetime.strptime(values[0],'%Y%m%d').date(),values[1],values[2] if registered else '',int(row.metric_values[0].value)))
    filters=FilterExpression(and_group=FilterExpressionList(expressions=[
        FilterExpression(filter=Filter(field_name='hostName',string_filter=Filter.StringFilter(value='stusaurus.github.io',match_type=Filter.StringFilter.MatchType.EXACT))),
        FilterExpression(filter=Filter(field_name='pagePath',string_filter=Filter.StringFilter(value='/daily-cost-jp/',match_type=Filter.StringFilter.MatchType.BEGINS_WITH)))]))
    views=[]
    for row in request(['date','pagePath'],'screenPageViews',filters):
        values=[d.value for d in row.dimension_values]
        views.append((dt.datetime.strptime(values[0],'%Y%m%d').date(),values[1],int(row.metric_values[0].value)))
    return ga4_aggregate(clicks,views,start,end,registered)

def fetch_gsc(start,end):
    if end>dt.datetime.now(ZoneInfo('America/Los_Angeles')).date()-dt.timedelta(days=3):
        return {'status':'WAIT_FOR_FINAL_DATA','calendar':'America/Los_Angeles','metrics':None,'observed_days':None}
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials,_=google.auth.default(scopes=[PROPERTY_SCOPE]);session=AuthorizedSession(credentials)
    def query(extra):
        response=session.post(API_ROOT+'/sites/'+quote(SITE,safe='')+'/searchAnalytics/query',
            json={'startDate':start.isoformat(),'endDate':end.isoformat(),'type':'web','dataState':'final',**extra},timeout=45)
        if response.status_code!=200:raise ValueError('API unavailable')
        return response.json()
    data=aggregate_response(query({}));dates=set()
    for row in query({'dimensions':['date'],'rowLimit':100}).get('rows',[]):
        date=dt.date.fromisoformat(row['keys'][0])
        if not start<=date<=end or date in dates:raise ValueError('Invalid day row')
        dates.add(date)
    return {'status':data['status'],'calendar':'America/Los_Angeles','metrics':data['metrics'],'observed_days':len(dates)}

def validate(obj):
    """Whitelist before copying a public aggregate into a private comparison."""
    keys={'source','site','month','period','generated_at_utc','status','gsc','ga4','cross_source_user_join','revenue_status'}
    if not isinstance(obj,dict) or set(obj)!=keys or obj['source']!=SOURCE or obj['site']!=SITE or obj['cross_source_user_join'] is not False or obj['revenue_status']!='NOT_CONNECTED':raise ValueError('Unknown monthly aggregate')
    start=dt.date.fromisoformat(obj['month']+'-01');end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
    if obj['period']!=[start.isoformat(),end.isoformat()] or end>=dt.datetime.now(ZoneInfo('Asia/Tokyo')).date().replace(day=1):raise ValueError('Incomplete month')
    stamp=dt.datetime.fromisoformat(obj['generated_at_utc'])
    if (stamp.tzinfo is None or stamp.utcoffset()!=dt.timedelta(0) or
        stamp>dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5) or
        stamp.astimezone(ZoneInfo('Asia/Tokyo')).date()<=end):raise ValueError('Unknown export time')
    gsc=obj['gsc'];ga=obj['ga4']
    if set(gsc)!={'status','calendar','metrics','observed_days'} or set(ga)!={'status','calendar','pageviews_observed','observed_days','operator_dimension_registered','affiliate_clicks_observed'}:raise ValueError('Unknown metric fields')
    if gsc['calendar']!='America/Los_Angeles' or ga['calendar']!='Asia/Tokyo':raise ValueError('Calendar mismatch')
    if set(ga['affiliate_clicks_observed'])!={'non_operator','operator','unknown'}:raise ValueError('Unknown click scope')
    for n in [ga['pageviews_observed'],*ga['affiliate_clicks_observed'].values()]:
        if n is not None and (type(n) is not int or n<0):raise ValueError('Invalid observed count')
    for n in [ga['observed_days'],gsc['observed_days']]:
        if n is not None and (type(n) is not int or not 0<=n<=end.day):raise ValueError('Invalid observation coverage')
    if ga['operator_dimension_registered'] is not None and type(ga['operator_dimension_registered']) is not bool:raise ValueError('Invalid dimension status')
    if gsc['metrics'] is not None:
        m=gsc['metrics']
        if set(m)!={'clicks','impressions','ctr','position'} or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in m.values()):raise ValueError('Invalid search metrics')
        if (m['clicks']>m['impressions'] or m['ctr']>1 or m['position']<1 or
            not float(m['clicks']).is_integer() or not float(m['impressions']).is_integer() or
            (m['impressions'] and abs(m['ctr']-m['clicks']/m['impressions'])>0.000001)):
            raise ValueError('Invalid search ratio')
    if (obj['status'] not in {'UNKNOWN','INDEPENDENT_MONTHLY_OBSERVATIONS','PARTIAL_OR_UNKNOWN'} or
        gsc['status'] not in {'NOT_CONNECTED','WAIT_FOR_FINAL_DATA','UNAVAILABLE','OBSERVED','NO_ROWS'} or
        ga['status'] not in {'NOT_CONNECTED','UNAVAILABLE','WAIT_FOR_FINAL_DATA','OBSERVED_ROWS','PARTIAL_OBSERVATIONS'}):raise ValueError('Invalid status')
    return obj

def main():
    start,end=bounds(dt.datetime.now(ZoneInfo('Asia/Tokyo')).date());report=empty(start,end)
    for field,collector in [('ga4',fetch_ga4),('gsc',fetch_gsc)]:
        try:report[field]=collector(start,end)
        except Exception:report[field]['status']='UNAVAILABLE'
    report['status']='INDEPENDENT_MONTHLY_OBSERVATIONS' if report['gsc']['metrics'] is not None and report['ga4']['pageviews_observed'] is not None else 'PARTIAL_OR_UNKNOWN'
    validate(report)
    root=Path('audit-results');root.mkdir(exist_ok=True)
    (root/'step7-google-monthly.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Monthly Google aggregates saved; Rakuten revenue not collected.')

if __name__=='__main__':main()
