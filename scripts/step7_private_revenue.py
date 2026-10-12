#!/usr/bin/env python3
"""Offline private monthly accounting. Never imported by the site build/publisher.

CSV header names are explicitly mapped from an operator's official download;
no undocumented Rakuten login/API or inferred site attribution is implemented.
"""
import argparse
import calendar
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from zoneinfo import ZoneInfo

KINDS = {'confirmed_reward', 'order_status', 'rakuten_clicks'}
STATUS = {'確定': 'confirmed', '未確定': 'pending', '破棄': 'discarded'}
FORMATS = {'month_iso': '%Y-%m', 'month_slash': '%Y/%m', 'month_jp': '%Y年%m月',
           'date_iso': '%Y-%m-%d', 'date_slash': '%Y/%m/%d'}
SOURCE = 'step7-private-revenue-v1'
MAX_BYTES = 10 * 1024 * 1024

class PrivateError(ValueError):
    pass

def reject(code):
    raise PrivateError(code)

def month(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d{2}-(?:0[1-9]|1[0-2])', value):
        reject('INVALID_MONTH')
    return value

def number(value):
    if not isinstance(value, str): reject('INVALID_NUMBER')
    value = value.strip().removeprefix('¥').removeprefix('￥').removesuffix('円').strip()
    if not re.fullmatch(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)', value): reject('INVALID_NUMBER')
    n = int(value.replace(',', ''))
    if n > 10**12: reject('NUMBER_OUT_OF_RANGE')
    return n

def schema(obj):
    required = {'kind', 'columns', 'period_format', 'encoding', 'row_format'}
    if not isinstance(obj, dict) or set(obj) != required: reject('INVALID_SCHEMA')
    if obj['kind'] not in KINDS or obj['period_format'] not in FORMATS or obj['encoding'] not in {'utf-8-sig','cp932'}:
        reject('INVALID_SCHEMA')
    cols = obj['columns']
    need = {'period', 'amount' if obj['kind'] != 'rakuten_clicks' else 'clicks'}
    if obj['kind'] == 'order_status':
        need.add('status')
        if obj['row_format'] == 'detail': need.add('row_id')
        elif obj['row_format'] != 'status_totals' or not obj['period_format'].startswith('month_'): reject('INVALID_SCHEMA')
    elif obj['row_format'] != 'summary': reject('INVALID_SCHEMA')
    if obj['kind'] == 'confirmed_reward' and not obj['period_format'].startswith('month_'):
        reject('REWARD_REQUIRES_REPORT_MONTH')
    if (not isinstance(cols, dict) or set(cols) != need or len(set(cols.values())) != len(cols) or
        any(not isinstance(v,str) or not v.strip() or len(v)>100 for v in cols.values())):
        reject('INVALID_SCHEMA')
    return obj

def aggregate(raw, mapping, expected_month):
    mapping = schema(mapping); month(expected_month)
    if not isinstance(raw, bytes) or len(raw)>MAX_BYTES: reject('CSV_TOO_LARGE')
    try: text = raw.decode(mapping['encoding'])
    except UnicodeError: reject('INVALID_ENCODING')
    reader = csv.DictReader(io.StringIO(text, newline=''))
    headers = reader.fieldnames
    if (not headers or len(headers)!=len(set(headers)) or
        not set(mapping['columns'].values()).issubset(headers)):
        reject('CSV_HEADERS_DO_NOT_MATCH')
    totals = {'confirmed_reward_yen': None, 'order_status_yen': {s:None for s in STATUS.values()},
              'rakuten_clicks_observed': None, 'observed_dates': [], 'rows_used': 0}
    seen = {}; periods = set(); rows = 0; cols = mapping['columns']; kind = mapping['kind']
    try:
        for row in reader:
            rows += 1
            if rows > 100000 or None in row or any(row.get(v) is None for v in cols.values()): reject('INVALID_CSV_ROW')
            try: date = dt.datetime.strptime(row[cols['period']].strip(), FORMATS[mapping['period_format']]).date()
            except (ValueError, TypeError): reject('INVALID_PERIOD')
            if date.strftime('%Y-%m') != expected_month: reject('MIXED_OR_WRONG_MONTH')
            key = date.isoformat(); periods.add(key)
            amount = number(row[cols['clicks' if kind=='rakuten_clicks' else 'amount']])
            state = None
            if kind=='order_status':
                state = STATUS.get(row[cols['status']].strip())
                if state is None: reject('UNKNOWN_STATUS')
                if mapping['row_format']=='detail':
                    identity = row[cols['row_id']].strip()
                    if not identity or len(identity)>256: reject('MISSING_DETAIL_ID')
                    signature = (key,state,amount)
                    if identity in seen:
                        if seen[identity] != signature: reject('CONFLICTING_DETAIL_ID')
                        continue
                    seen[identity] = signature  # Memory only; no order IDs persisted.
                else:
                    if state in seen: reject('OVERLAPPING_STATUS_TOTALS')
                    seen[state] = True
                old = totals['order_status_yen'][state]
                totals['order_status_yen'][state] = (old or 0)+amount
            else:
                if key in seen: reject('OVERLAPPING_SUMMARY_ROWS')
                seen[key] = True
                field = 'confirmed_reward_yen' if kind=='confirmed_reward' else 'rakuten_clicks_observed'
                totals[field] = (totals[field] or 0)+amount
            totals['rows_used'] += 1
    except csv.Error: reject('INVALID_CSV')
    if rows==0: reject('EMPTY_CSV_IS_UNKNOWN')
    if mapping['period_format'].startswith('month_') and kind!='order_status' and rows!=1:
        reject('MONTHLY_SUMMARY_MUST_BE_SINGLE_ROW')
    totals['observed_dates'] = sorted(periods) if mapping['period_format'].startswith('date_') else []
    totals['daily_coverage_complete'] = (len(periods)==calendar.monthrange(*map(int,expected_month.split('-')))[1]
                                       if mapping['period_format'].startswith('date_') else None)
    return totals

def protected_path(value):
    p=Path(value)
    if not p.is_absolute(): reject('PRIVATE_PATH_MUST_BE_ABSOLUTE')
    for parent in [p,*p.parents]:
        if parent.is_symlink(): reject('SYMLINK_NOT_ALLOWED')
        if (parent/'.git').exists(): reject('PRIVATE_DATA_INSIDE_GIT_FORBIDDEN')
    return p.resolve()

def private_root(value, create=False):
    p=protected_path(value)
    if create:
        if not p.exists(): p.mkdir(mode=0o700,parents=False)
    if not p.is_dir() or stat.S_IMODE(p.stat().st_mode)&0o077: reject('PRIVATE_DIRECTORY_REQUIRES_0700')
    return p

def private_file(root, value):
    p=protected_path(value)
    if not p.is_relative_to(root) or not p.is_file(): reject('INPUT_MUST_BE_PRIVATE')
    if stat.S_IMODE(p.stat().st_mode)&0o077: reject('PRIVATE_FILE_REQUIRES_0600')
    if p.stat().st_size>MAX_BYTES: reject('PRIVATE_FILE_TOO_LARGE')
    return p

def timestamp(value):
    try: stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,AttributeError): reject('INVALID_EXPORT_TIME')
    if stamp.tzinfo is None or stamp.utcoffset()!=dt.timedelta(0): reject('EXPORT_TIME_REQUIRES_UTC')
    if stamp > dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5): reject('FUTURE_EXPORT_TIME')
    return stamp.isoformat()

def database(root):
    root=private_root(str(root))
    p=root/'monthly.sqlite3'
    if p.exists(): private_file(root,str(p))
    else:
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    conn=sqlite3.connect(p,timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS snapshots (account TEXT, kind TEXT, month TEXT, exported_at TEXT, digest TEXT, payload TEXT, PRIMARY KEY(account,kind,month))')
    conn.execute('CREATE TABLE IF NOT EXISTS imports (account TEXT,kind TEXT,month TEXT,digest TEXT, PRIMARY KEY(account,kind,month,digest))')
    return conn

def ingest(conn, raw, mapping, account, period, exported_at, replace=False):
    if not re.fullmatch('[a-z0-9-]{1,40}',account): reject('INVALID_ACCOUNT_ALIAS')
    result=aggregate(raw,mapping,period);stamp=timestamp(exported_at);kind=mapping['kind']
    digest=hashlib.sha256((json.dumps(result,sort_keys=True)+stamp).encode()).hexdigest()
    with conn:
        # Serialize check+replacement, including two simultaneous imports.
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM imports WHERE account=? AND kind=? AND month=? AND digest=?',(account,kind,period,digest)).fetchone():
            return 'DUPLICATE_NOT_ADDED'
        old=conn.execute('SELECT exported_at FROM snapshots WHERE account=? AND kind=? AND month=?',(account,kind,period)).fetchone()
        if old:
            if not replace: reject('SNAPSHOT_EXISTS_USE_REPLACE')
            if stamp<=old[0]: reject('STALE_SNAPSHOT')
        conn.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?)',(account,kind,period,stamp,digest,json.dumps(result,sort_keys=True)))
        conn.execute('INSERT INTO imports VALUES (?,?,?,?)',(account,kind,period,digest))
    return 'PRIVATE_SNAPSHOT_IMPORTED'

def monthly_report(conn, account, period, google=None):
    month(period)
    if not re.fullmatch('[a-z0-9-]{1,40}',account):reject('INVALID_ACCOUNT_ALIAS')
    values={k:None for k in KINDS}
    for kind,stamp,payload in conn.execute('SELECT kind,exported_at,payload FROM snapshots WHERE account=? AND month=?',(account,period)):
        values[kind]={'exported_at_utc':stamp,**json.loads(payload)}
    g=None
    if google is not None:
        from step7_google_monthly import validate
        g=validate(google)
        if g['month']!=period:reject('MONTHLY_SOURCE_PERIOD_MISMATCH')
    history=[{'month':m,'confirmed_reward_yen':json.loads(p)['confirmed_reward_yen'],'exported_at_utc':t}
             for m,t,p in conn.execute('SELECT month,exported_at,payload FROM snapshots WHERE account=? AND kind=? AND month<=? ORDER BY month DESC LIMIT 12',(account,'confirmed_reward',period))]
    priorities=[{'priority':1,'code':'VERIFY_SITE_ATTRIBUTION','classification':'INVESTIGATE'}]
    if values['confirmed_reward'] is None:priorities.insert(0,{'priority':1,'code':'LOAD_CONFIRMED_REWARD_REPORT','classification':'INVESTIGATE'})
    if g is None or g.get('status')!='INDEPENDENT_MONTHLY_OBSERVATIONS':priorities.append({'priority':2,'code':'VERIFY_MONTHLY_GOOGLE_COVERAGE','classification':'INVESTIGATE'})
    return {'source':SOURCE,'month':period,'rakuten_scope':'ACCOUNT_UNATTRIBUTED',
            'daily_cost_confirmed_reward_yen':None,'site_attribution':'UNVERIFIED',
            'rakuten':values,'confirmed_account_history':history,'priorities':priorities,'google':g,'google_status':'NOT_CONNECTED' if g is None else g.get('status','UNKNOWN'),
            'evaluation':'評価保留','cross_source_user_join':False,
            'note':'Reward-report month, order occurrence month and click month are separate bases. No revenue/visitor ratio or daily-site attribution.'}

def save(root,name,value):
    root=private_root(str(root))
    p=protected_path(str(root/name))
    if not p.is_relative_to(root):reject('OUTPUT_MUST_BE_PRIVATE')
    if p.exists() and p.is_symlink(): reject('SYMLINK_NOT_ALLOWED')
    fd,temp=tempfile.mkstemp(prefix='.private-',dir=root)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(value)
        os.replace(temp,p)
    finally:
        if Path(temp).exists(): Path(temp).unlink()

def markdown(r):
    lines=['# 非公開：月次実績比較', '', '月：'+r['month'],
           '楽天はアカウント全体・サイト帰属未確認。Googleは日用品サイトのみ。',
           '同じ月でも集計時間帯・報酬対象月が異なる。クリックは購入ではない。', '',
           '| 区分 | 取得値 |', '|---|---:|']
    reward=r['rakuten']['confirmed_reward'];orders=r['rakuten']['order_status'];clicks=r['rakuten']['rakuten_clicks']
    show=lambda v:'未確認' if v is None else str(v)
    lines.append('| 確定報酬（公式成果報酬レポート月） | '+show(reward['confirmed_reward_yen'] if reward else None)+' |')
    for k,label in [('confirmed','確定注文詳細の報酬'),('pending','未確定成果'),('discarded','破棄成果')]:
        lines.append('| '+label+'（成果発生月） | '+show(orders['order_status_yen'][k] if orders else None)+' |')
    lines.append('| 楽天クリック取得行 | '+show(clicks['rakuten_clicks_observed'] if clicks else None)+' |')
    if r['google']:
        for source in ('gsc','ga4'):
            lines+=['',source.upper()+'（独立した月次集計）：',json.dumps(r['google'].get(source),ensure_ascii=False)]
    lines+=['','## アカウント全体の確定報酬履歴（最大12か月・未取得月は省略）','', '| 報酬レポート月 | 確定円 |','|---|---:|']
    for item in r['confirmed_account_history']:lines.append('| '+item['month']+' | '+str(item['confirmed_reward_yen'])+' |')
    lines+=['','次の調査（自動修正なし）：'+', '.join(p['code'] for p in r['priorities'])]
    lines+=['','日用品由来の確定報酬：未確認。評価保留。','注文詳細の確定値と成果報酬レポートは加算しない。']
    return '\n'.join(lines)+'\n'

def main():
    if os.environ.get('GITHUB_ACTIONS')=='true' or os.environ.get('CI')=='true': reject('PRIVATE_FINANCIAL_CLI_FORBIDDEN_IN_CI')
    parser=argparse.ArgumentParser(description='Offline private monthly CSV importer; never upload financial files to GitHub.')
    parser.add_argument('--private-dir',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    imp=sub.add_parser('import-csv');imp.add_argument('--csv',required=True);imp.add_argument('--schema',required=True)
    imp.add_argument('--account',default='main');imp.add_argument('--month',required=True);imp.add_argument('--exported-at',required=True)
    imp.add_argument('--complete-official-month',action='store_true',required=True);imp.add_argument('--replace',action='store_true')
    rep=sub.add_parser('report');rep.add_argument('--account',default='main');rep.add_argument('--month',required=True);rep.add_argument('--google')
    args=parser.parse_args();root=private_root(args.private_dir,create=args.command=='init')
    conn=database(root)
    try:
        if args.command=='import-csv':
            if month(args.month)>=dt.datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m'):reject('MONTH_NOT_COMPLETE')
            raw=private_file(root,args.csv).read_bytes();mapping=json.loads(private_file(root,args.schema).read_text())
            print(ingest(conn,raw,mapping,args.account,args.month,args.exported_at,args.replace))
        elif args.command=='report':
            google=json.loads(private_file(root,args.google).read_text()) if args.google else None
            r=monthly_report(conn,args.account,args.month,google)
            save(root,'monthly-report.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n');save(root,'monthly-report.md',markdown(r))
            print('PRIVATE_REPORT_SAVED')
        else: print('PRIVATE_STORE_READY')
    finally: conn.close()

if __name__=='__main__':
    try:main()
    except PrivateError as error:print(str(error));raise SystemExit(1)
    except Exception:print('PRIVATE_OPERATION_FAILED_NO_DATA_LOGGED');raise SystemExit(1)
