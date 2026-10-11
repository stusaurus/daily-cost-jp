"""Anonymous purpose evidence and comparable windows, never revenue inference."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from step4_purchase_audit import load_live, verify_snapshot
from step4_recommendations import select, select_category, sale_band, destination_matches, CATEGORIES
from product_quality import filter_items, parsed_quantity
from comparison_units import comparison_unit
from ga4_page_diagnostics import path_from_location, FOCUS_PAGES
from step4_measurement import read
from ga4_three_day_report import check_response

DIMENSIONS=('operator_test','purchase_purpose','diagnostic_status','diagnostic_phase','conversion_source')
PURPOSES=('small','everyday','bulk')


def aggregate_purpose(rows, period, registered):
    start,end=map(dt.date.fromisoformat,period)
    if (end-start).days!=27:raise ValueError('Expected 28-day window')
    buckets={p:{purpose:{k:0 for k in ('non_operator','operator','unknown')} for purpose in (*PURPOSES,'unspecified')} for p in FOCUS_PAGES}
    daily={};observed=set()
    for day,path,purpose,flag,count in rows:
        date=dt.date.fromisoformat(day)
        if not start<=date<=end or type(count) is not int or count<0:raise ValueError('Invalid metrics')
        path=path_from_location(path)
        if path not in buckets:continue
        purpose=purpose if purpose in PURPOSES else 'unspecified'
        scope='non_operator' if registered.get('operator_test') and flag=='0' else 'operator' if registered.get('operator_test') and flag=='1' else 'unknown'
        buckets[path][purpose][scope]+=count
        daily.setdefault(day,{k:0 for k in ('non_operator','operator','unknown')})[scope]+=count
        observed.add(day)
    connected=registered.get('purchase_purpose') is True
    seven={}
    for label,lo,hi in [('last_7',end-dt.timedelta(days=6),end),('prior_7',end-dt.timedelta(days=13),end-dt.timedelta(days=7))]:
        seven[label]={'period':[lo.isoformat(),hi.isoformat()],
            'clicks':{k:sum(v[k] for d,v in daily.items() if lo.isoformat()<=d<=hi.isoformat()) for k in ('non_operator','operator','unknown')} if connected else None}
    return {'status':'AGGREGATES_ONLY' if connected else 'NOT_REGISTERED','period':period,
            'counts':buckets if connected else None,'days_with_click_rows':len(observed),
            'daily_clicks':daily if connected else None,'seven_day_windows':seven,'real_users_verified':False,
            'missing_click_rows_are_not_observed_pageview_days':True}


def fetch_details():
    import google.auth
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange,Dimension,Metric,RunReportRequest,Filter,FilterExpression
    prop=os.environ['GA4_PROPERTY_ID']
    if not prop.isdigit():raise ValueError('Invalid property')
    credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    client=BetaAnalyticsDataClient(credentials=credentials);property_='properties/'+prop
    names={d.api_name for d in client.get_metadata(name=property_+'/metadata').dimensions}
    registered={d:'customEvent:'+d in names for d in DIMENSIONS}
    end=dt.datetime.now(ZoneInfo('Asia/Tokyo')).date()-dt.timedelta(days=2);start=end-dt.timedelta(days=27)
    prior_start=start-dt.timedelta(days=28)
    result={'source':'GA4 Data API','custom_dimensions':registered,'status':'NOT_REGISTERED',
            'current':None,'prior':None,'diagnostics':'NOT_QUERIED','sales_status':'NOT_CONNECTED'}
    if not registered['purchase_purpose']:return result
    dims=['date','pageLocation','customEvent:purchase_purpose']+(['customEvent:operator_test'] if registered['operator_test'] else [])
    response=client.run_report(RunReportRequest(property=property_,date_ranges=[DateRange(start_date=prior_start.isoformat(),end_date=end.isoformat())],
        dimensions=[Dimension(name=x) for x in dims],metrics=[Metric(name='eventCount')],limit=100000,
        dimension_filter=FilterExpression(filter=Filter(field_name='eventName',string_filter=Filter.StringFilter(value='affiliate_click',match_type=Filter.StringFilter.MatchType.EXACT)))))
    rows=[]
    for row in check_response(response):
        v=[d.value for d in row.dimension_values];day=dt.datetime.strptime(v[0],'%Y%m%d').date().isoformat()
        rows.append((day,v[1],v[2],v[3] if registered['operator_test'] else '',int(row.metric_values[0].value)))
    result.update(status='AGGREGATES_ONLY',current=aggregate_purpose([r for r in rows if r[0]>=start.isoformat()],[start.isoformat(),end.isoformat()],registered),
                  prior=aggregate_purpose([r for r in rows if r[0]<start.isoformat()],[prior_start.isoformat(),(start-dt.timedelta(days=1)).isoformat()],registered))
    return result


def assortment(snapshot):
    selection=select(snapshot)
    result={'status':selection['status'],'catalog_updated_at':selection['catalog_updated_at'],'categories':{},'empty_slots':None,'ranking_changed':False}
    if selection['status']!='TRUSTED_RECENT':return result
    empty=0
    for cid in CATEGORIES:
        c=snapshot['categories'][cid];s=selection['categories'][cid]
        pool=c.get('purpose_candidates',[])
        if not isinstance(pool,list) or len(pool)>30 or any(not isinstance(r,dict) for r in pool):pool=[]
        rows=filter_items(cid,c.get('items',[]))+filter_items(cid,pool)
        if cid=='tissue' and isinstance(c.get('small_pack_offer'),dict):rows+=filter_items(cid,[c['small_pack_offer']])
        counts={p:0 for p in PURPOSES};seen=set()
        for row in rows:
            qty=parsed_quantity(cid,row['name']);unit=comparison_unit(cid,row)
            if not qty or not unit or not destination_matches(row):continue
            key=row['item_code']
            if key in seen:continue
            seen.add(key);purpose=sale_band(cid,row,qty['quantity'])
            if purpose in counts:counts[purpose]+=1
        slots={p:({'quantity':r['quantity'],'total_yen':r['offer']['price'],'comparison_unit':r['unit'][0]} if r else None) for p,r in s['slots'].items()}
        empty+=sum(r is None for r in slots.values())
        result['categories'][cid]={'eligible_offer_counts':counts,'distinct_sku_count':None,'slots':slots,
            'recommendation_status':s['status'],'recommendation_reasons':s['reasons'],
            'acquisition_status':c.get('household_acquisition',{}).get('status','NOT_CONNECTED'),
            'acquisition_reasons':c.get('household_acquisition',{}).get('reasons',{})}
    result['empty_slots']=empty
    return result


def evaluate(snapshot, current=None, prior=None, details=None, gsc=None):
    result={'source':'daily-cost step5 evaluation v1','assortment':assortment(snapshot),
            'ga4':{'current':None,'prior':None,'purpose_details':None},'gsc':None,
            'sales':{'status':'NOT_CONNECTED','confirmed_reward_yen':None,'orders':None},
            'evaluation':'INSUFFICIENT_COMPARABLE_DATA','cross_source_user_join':False,'automatic_code_change':False}
    for label,data in [('current',current),('prior',prior)]:
        if isinstance(data,dict) and data.get('source')=='GA4 Data API':
            result['ga4'][label]={k:data.get(k) for k in ('period','status','pageview_days_observed','expected_days','response_complete','operator_dimension_registered','events')}
    if isinstance(details,dict) and details.get('source')=='GA4 Data API':
        result['ga4']['purpose_details']={k:details.get(k) for k in ('status','custom_dimensions','current','prior','diagnostics')}
    if isinstance(gsc,dict) and gsc.get('source')=='Search Console Search Analytics API':
        # Site aggregates only, never raw search queries or user joins.
        result['gsc']={'independent_source':True,'windows':gsc.get('windows'),'site_aggregates':gsc.get('site_aggregates')}
    # Reuse the approved conservative sample/period guard; readiness is not success.
    from step4_automation import reaction_safeguard
    guard=reaction_safeguard(current,prior)
    result['comparison_readiness_reason']=guard
    if (guard in ('NO_RATE_DROP_SIGNAL','PAUSE_FOR_RATE_DROP_REVIEW') and isinstance(details,dict)
        and details.get('status')=='AGGREGATES_ONLY' and details.get('current',{}).get('period')==current.get('period')
        and details.get('prior',{}).get('period')==prior.get('period')):
        result['evaluation']='READY_FOR_HUMAN_REVIEW_NOT_CAUSAL_PROOF'
    result['seven_day_policy']='Operational availability and measurement coverage only; not success/failure or sales.'
    result['twenty_eight_day_policy']='Equal complete post-release windows with dates, pageview observation, event samples, operator/unknown separation; no outcome claim when insufficient.'
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');parser.add_argument('--build',action='store_true');args=parser.parse_args()
    root=Path('site' if args.build else 'audit-results');root.mkdir(exist_ok=True)
    details=None
    if args.fetch:
        try:details=fetch_details()
        except Exception:details={'source':'GA4 Data API','status':'UNAVAILABLE','custom_dimensions':None}
        (root/'step5-purpose-metrics.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
    else:details=read(root/'step5-purpose-metrics.json')
    try:snapshot=read(root/'data.json') if args.build else load_live()
    except Exception:snapshot=None
    result=evaluate(snapshot,read(root/'step4-events-28d.json'),read(root/'step4-events-prior-28d.json'),details,read(root/'gsc-search-pilot.json'))
    (root/'step5-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (root/'step5-evaluation.md').write_text('# STEP5：品揃えと収益検証\n\n'
       +f"- 品揃え：{result['assortment']['status']}、空枠：{result['assortment']['empty_slots']}\n"
       +'- 7日は取得/空枠/計測の運用確認。28日は期間・観測日数・イベント件数・テスト/不明を分離して評価。\n'
       +'- 非運営者区分は実利用者の証明ではない。GSCとGA4をユーザー結合しない。\n'
       +'- 楽天確定成果未接続。売上0円ではなく不明。改善成功/失敗は未判定。\n')
    print('STEP5 evaluation',result['assortment']['status'],'sales NOT_CONNECTED')


if __name__=='__main__':main()
