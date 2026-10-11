"""Equal completed pre/post search windows after confirmed publication.

The reviewed ledger records the actual public date, not merge/build time.
No entries => no deployed SEO experiment; never claim an improvement.
"""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import quote
from gsc_readonly_pilot import SITE, API_ROOT, aggregate_response
from step6_seo_content import REGISTRY, recipe


def releases(text):
    obj=json.loads(text)
    rows=obj.get('releases') if isinstance(obj,dict) else None
    if not isinstance(rows,list) or len(rows)>30:raise ValueError('Invalid release ledger')
    seen=set()
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'path','recipe','published_on','commit'} or
                row['path'] not in {f'/categories/{c}/' for c in REGISTRY} or
                row['recipe']!=recipe(row['path'].split('/')[2]) or
                not re.fullmatch('[a-f0-9]{40}',row['commit']) or row['recipe'] in seen):
            raise ValueError('Invalid confirmed SEO release')
        dt.date.fromisoformat(row['published_on']);seen.add(row['recipe'])
    return rows


def windows(release, today, length):
    published=dt.date.fromisoformat(release['published_on'])
    # Publication day excluded; final reporting latency preserved.
    current=[published+dt.timedelta(days=1),published+dt.timedelta(days=length)]
    prior=[published-dt.timedelta(days=length),published-dt.timedelta(days=1)]
    if current[1]>today-dt.timedelta(days=3):return None
    return {k:[d.isoformat() for d in v] for k,v in [('after',current),('before',prior)]}


def collect(session, today):
    try:ledger=releases(Path('docs/step6-release-ledger.json').read_text())
    except (OSError,ValueError,TypeError):return {'status':'LEDGER_UNKNOWN','evaluation':'評価保留'}
    result={'status':'NO_CONFIRMED_PUBLICATION' if not ledger else 'OBSERVING',
            'evaluation':'評価保留','sales_status':'NOT_CONNECTED','cross_source_user_join':False,'releases':[]}
    # One latest approved experiment per cycle; at most four readonly queries.
    for entry in sorted(ledger,key=lambda r:r['published_on'],reverse=True)[:1]:
        row={**entry,'comparisons':{}}
        for length in (7,28):
            bounds=windows(entry,today,length)
            comparison={'windows':bounds,'status':'WAIT_FOR_COMPLETE_WINDOW','before':None,'after':None,
                        'evaluation':'評価保留','causal_effect_verified':False}
            if bounds:
                try:
                    for label,(start,end) in bounds.items():
                        r=session.post(API_ROOT+'/sites/'+quote(SITE,safe='')+'/searchAnalytics/query',json={
                            'startDate':start,'endDate':end,'type':'web','dataState':'final',
                            'dimensionFilterGroups':[{'filters':[{'dimension':'page','operator':'equals',
                                                                 'expression':SITE+entry['path'][1:]}]}]},timeout=45)
                        if r.status_code!=200:raise ValueError('API unavailable')
                        comparison[label]=aggregate_response(r.json())['metrics']
                    if comparison['before'] is None or comparison['after'] is None:
                        comparison['status']='MISSING_ROWS_UNKNOWN'
                    elif min(comparison[k]['impressions'] for k in ('before','after'))<200 or min(comparison[k]['clicks'] for k in ('before','after'))<20:
                        comparison['status']='LOW_SAMPLE'
                    else:
                        comparison['status']='READY_FOR_HUMAN_REVIEW_NOT_CAUSAL_PROOF'
                except Exception:
                    comparison['status']='API_UNAVAILABLE'
            row['comparisons'][str(length)]=comparison
        result['releases'].append(row)
    return result
