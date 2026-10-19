"""Fixed-selection controller and STEP1/2/3 integration, not a second publisher."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from step4_purchase_audit import inspect,load_live
from step4_recommendations import select,VERSION,CATEGORIES,apply
from step4_measurement import read
SOURCE='daily-cost step4 control v1'
REPO='stusaurus/daily-cost-jp'


def reaction_safeguard(current,prior):
    """Conservative stop signal, not statistical causality or sales proof."""
    def valid(r):
        if not isinstance(r,dict) or r.get('source')!='GA4 Data API' or r.get('response_complete') is not True or r.get('operator_dimension_registered') is not True or r.get('pageview_days_observed')!=28:return False
        try:
            start,end=map(dt.date.fromisoformat,r['period'])
            return (end-start).days==27
        except (KeyError,ValueError,TypeError):return False
    if not valid(current) or not valid(prior):return 'INSUFFICIENT_COMPARABLE_DATA'
    if dt.date.fromisoformat(prior['period'][1])+dt.timedelta(days=1)!=dt.date.fromisoformat(current['period'][0]):return 'PERIOD_MISMATCH'
    def totals(r):
        v=c=0
        for path in ('/','/categories/laundry/','/categories/tissue/','/categories/toilet-paper/'):
            events=r.get('events',{}).get(path,{})
            for e in ('page_view','affiliate_click'):
                values=events.get(e)
                if not isinstance(values,dict) or any(type(values.get(k)) is not int or values[k]<0 for k in ('non_operator','operator','unknown')) or values['unknown']>0:return None
            v+=events['page_view']['non_operator'];c+=events['affiliate_click']['non_operator']
        return v,c
    a,b=totals(current),totals(prior)
    if a is None or b is None or min(a[0],b[0])<1000 or b[1]<30:return 'INSUFFICIENT_COMPARABLE_DATA'
    # Event rate safeguard only, never a user conversion or purchase ratio.
    return 'PAUSE_FOR_RATE_DROP_REVIEW' if a[1]/a[0]<.6*b[1]/b[0] else 'NO_RATE_DROP_SIGNAL'


def diagnose(snapshot,enabled=False,paused=False,current_events=None,prior_events=None,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    audit=inspect(snapshot,now=now);selection=select(snapshot,now=now)
    quality_bad=(selection['status']!='TRUSTED_RECENT' or any(audit['categories'].get(c,{}).get('status')=='UNAVAILABLE' for c in CATEGORIES))
    rejected=any(p.get('status')=='REJECTED' for c in CATEGORIES for p in audit['categories'].get(c,{}).get('offers',[]))
    reaction=reaction_safeguard(current_events,prior_events)
    reason=('MANUAL_PAUSE' if paused else 'QUALITY_OR_SOURCE_ANOMALY' if quality_bad or rejected else 'REACTION_SAFEGUARD' if reaction=='PAUSE_FOR_RATE_DROP_REVIEW' else 'FIXED_SELECTION_ALLOWED')
    action='STOP_AND_FALLBACK' if reason!='FIXED_SELECTION_ALLOWED' else 'ALLOW_FIXED_SELECTION'
    decisions=[]
    for cid,result in selection['categories'].items():
        acquisition = snapshot['categories'].get(cid, {}).get('household_acquisition', {})
        acquisition_failed = (acquisition.get('status') == 'ACQUISITION_UNAVAILABLE' or
                              acquisition.get('reasons', {}).get('api_fetch_failure', 0) > 0)
        for purpose,row in result['slots'].items():
            decisions.append({'path':f'/categories/{cid}/','code':'PURCHASE_'+purpose.upper(),
                'classification':'AUTO_CONTENT' if enabled and action=='ALLOW_FIXED_SELECTION' and row else 'INVESTIGATE',
                'reason':'FIXED_VERIFIED_SELECTION' if row else 'ACQUISITION_UNKNOWN' if acquisition_failed else 'NO_VERIFIED_CANDIDATE', 'automatic_code_change':False})
    # STEP4 cannot promote an observed metric or issue text into executable code.
    decisions += [{'path':'/','code':code,'classification':'HUMAN_ONLY','automatic_code_change':False} for code in ('PRODUCT_QUALITY','PRICE_CALCULATION','POSTAGE','RAKUTEN_URL','SEO','CODE_CSS_NEW_FEATURE','SAFETY_RULE')]
    return {'source':SOURCE,'rule_version':VERSION,'generated_at_utc':now.isoformat(),'content_action':action,'reason':reason,'reaction_status':reaction,
       'content_approved':enabled,'decisions':decisions,'publisher':'EXISTING_STEP2_ONLY','maximum_draft_prs':1,
       'automatic_merge':False,'automatic_deploy':False,'rollback':'REMOVE_PURPOSE_LAYER_USE_CURRENT_SAFE_RANKING',
       'sales_status':'NOT_CONNECTED','selection_status':selection['status']}


def read_feedback(token):
    """Download only a recent successful exact-main workflow's control artifact.

    No arbitrary branch output, filenames, commands, source code or report text
    is executed. Missing permission/data prevents new content, not site build.
    """
    if not token:return None
    from autonomous_operations_issue import github_request
    from urllib.request import Request,build_opener,HTTPRedirectHandler
    import io,zipfile
    class StripAuthorization(HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            result=super().redirect_request(req,fp,code,msg,headers,newurl)
            if result:result.remove_header('Authorization')
            return result
    try:
        runs=github_request('/actions/workflows/ga4-three-day-analysis.yml/runs?branch=main&status=success&per_page=5',token)['workflow_runs']
        run=next((r for r in runs if r.get('head_branch')=='main' and r.get('event') in ('schedule','workflow_dispatch','push') and r.get('conclusion')=='success'),None)
        if not run:return None
        instant=dt.datetime.fromisoformat(run['updated_at'].replace('Z','+00:00'))
        if instant.tzinfo is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-instant).total_seconds() <= 4*86400:return None
        artifacts=github_request(f"/actions/runs/{run['id']}/artifacts?per_page=100",token)['artifacts']
        matches=[a for a in artifacts if a.get('name')=='step4-operations-feedback' and not a.get('expired')]
        if len(matches)!=1:return None
        artifact=matches[0]
        if artifact.get('size_in_bytes',0)>300000:return None
        url=f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip"
        req=Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
        with build_opener(StripAuthorization()).open(req,timeout=20) as response:blob=response.read(300001)
        if len(blob)>300000:return None
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            members=[x for x in archive.infolist() if x.filename=='step4-control.json']
            if len(members)!=1 or members[0].file_size>100000:return None
            value=json.loads(archive.read(members[0]))
        value['evidence_run_id']=run['id']
        return value
    except Exception:return None


def feedback_valid(feedback,now=None):
    if not isinstance(feedback,dict) or feedback.get('source')!=SOURCE or feedback.get('rule_version')!=VERSION:return False
    decisions=feedback.get('decisions')
    if not isinstance(decisions,list) or len(decisions)>30:return False
    from autonomous_operations_triage import good_path
    import re
    if any(not isinstance(d,dict) or not good_path(d.get('path')) or not isinstance(d.get('code'),str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{2,70}',d['code']) or d.get('classification') not in ('AUTO_CONTENT','INVESTIGATE','HUMAN_ONLY') for d in decisions):return False
    try:
        stamp=dt.datetime.fromisoformat(feedback['generated_at_utc']);now=now or dt.datetime.now(dt.timezone.utc)
        return stamp.tzinfo is not None and -300<=(now-stamp).total_seconds()<=4*86400 and feedback.get('content_action') in ('ALLOW_FIXED_SELECTION','STOP_AND_FALLBACK')
    except (KeyError,ValueError,TypeError):return False


def build_content(site=Path('site'),env=None,feedback=None):
    env=env or os.environ
    enabled=env.get('STEP4_ENABLE_CONTENT')=='true';paused=env.get('STEP4_PAUSE_CONTENT')=='true'
    try:snapshot=json.loads((site/'data.json').read_text())
    except (OSError,ValueError):snapshot=None
    try:decision=diagnose(snapshot,enabled,paused)
    except (TypeError,ValueError,KeyError,AttributeError):
        snapshot=None
        decision=diagnose(None,enabled,paused)
    if enabled and not paused:
        feedback=feedback if feedback is not None else read_feedback(env.get('STEP4_READ_TOKEN',''))
        if not feedback_valid(feedback):decision.update(content_action='STOP_AND_FALLBACK',reason='FRESH_MAIN_FEEDBACK_UNAVAILABLE')
        elif feedback['content_action']=='STOP_AND_FALLBACK':decision.update(content_action='STOP_AND_FALLBACK',reason='MAIN_FEEDBACK_PAUSE')
        else:decision['feedback_run_id']=feedback.get('evidence_run_id')
    active=enabled and decision['content_action']=='ALLOW_FIXED_SELECTION'
    if snapshot is not None:apply(site,enabled=active)
    # Safe fallback retains today's verified ranking, never restores old prices.
    (site/'step4-content-state.json').write_text(json.dumps({k:v for k,v in decision.items() if k!='decisions'},ensure_ascii=False,indent=2))
    print('STEP4 content:', 'ACTIVE' if active else 'FALLBACK',decision['reason'])
    return decision


def integrate(operations,control):
    """Append bounded machine findings to the existing rolling Issue queue."""
    if not isinstance(operations,dict) or operations.get('source')!='daily-cost autonomous operations triage v1':raise ValueError('Invalid operations report')
    if not feedback_valid(control):return operations
    findings=list(operations.get('findings',[]))
    candidates=[]
    if control['content_action']=='STOP_AND_FALLBACK':candidates.append(('P1','STEP4_CONTENT_PAUSED','/','購買枠は安全停止の対象です。現行の安全なランキングへ戻します。','入力品質・停止状態を確認。品質判定は緩めない'))
    for d in control['decisions']:
        if d['classification']=='INVESTIGATE' and d.get('reason')=='ACQUISITION_UNKNOWN':candidates.append(('P2','PURCHASE_ACQUISITION_UNKNOWN',d['path'],'購入候補の取得に失敗。供給ゼロや候補不足とは断定しません。','API取得・権限・次回更新を確認。商品判定は緩めない'))
        if d['classification']=='INVESTIGATE' and d.get('reason')=='NO_VERIFIED_CANDIDATE':candidates.append(('P2',d['code'],d['path'],'購入目的に合う検証済み候補が不足しています。','不足数量の取得と商品同一性を調査。架空候補は追加しない'))
    ids={f['id'] for f in findings}
    for severity,code,path,message,next_action in candidates:
        identity=hashlib.sha256((code+':'+path).encode()).hexdigest()[:16]
        if identity not in ids:findings.append({'id':identity,'severity':severity,'code':code,'path':path,'message':message,'next_action':next_action,'evidence':'STEP4固定ルール・当日監査。売上未接続。'});ids.add(identity)
    findings=sorted(findings,key=lambda f:(f['severity'],f['path'],f['code']))[:20]
    operations={**operations,'findings':findings,'summary':{p:sum(f['severity']==p for f in findings) for p in ('P0','P1','P2','P3')}}
    operations['fingerprint']=hashlib.sha256('\n'.join(f"{f['severity']}:{f['id']}" for f in findings if f['severity'] in ('P0','P1','P2')).encode()).hexdigest()[:20]
    operations['status']='URGENT_REVIEW' if operations['summary']['P0'] else 'REVIEW_REQUIRED' if any(operations['summary'][p] for p in ('P1','P2')) else 'NO_ACTIONABLE_FINDINGS'
    return operations


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['build','diagnose'],default='diagnose',nargs='?');args=parser.parse_args()
    if args.mode=='build':build_content();return
    root=Path('audit-results');root.mkdir(exist_ok=True)
    try:snapshot=load_live()
    except Exception:snapshot=None
    control=diagnose(snapshot,os.environ.get('STEP4_ENABLE_CONTENT')=='true',os.environ.get('STEP4_PAUSE_CONTENT')=='true',
        read(root/'step4-events-28d.json'),read(root/'step4-events-prior-28d.json'))
    (root/'step4-control.json').write_text(json.dumps(control,ensure_ascii=False,indent=2))
    (root/'step4-control.md').write_text('# STEP4：固定商品選択の安全判定\n\n'+f"- 状態：{control['content_action']} / {control['reason']}\n- 利用反応：{control['reaction_status']}\n"
       +'- AUTO_CONTENTは承認済み固定選択だけ。コード・CSS・品質・価格・URL・SEOはHUMAN_ONLY。\n'
       +'- 発行処理は既存STEP2だけ、分析1回につき最大1 Draft。売上は未接続。\n')
    operations=read(root/'autonomous-operations.json')
    if operations:
        from autonomous_operations_triage import markdown
        merged=integrate(operations,control)
        (root/'autonomous-operations.json').write_text(json.dumps(merged,ensure_ascii=False,indent=2))
        (root/'autonomous-operations.md').write_text(markdown(merged))
    print('STEP4 control:',control['content_action'],control['reason'])
if __name__=='__main__':main()
