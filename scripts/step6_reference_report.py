"""Read existing exact-main authenticated GSC artifact for unpublished PR QA.

This does not authenticate to Google from a PR or add any Google permission.
The report retains its original timestamp; stale evidence cannot make a Draft.
"""
import io
import json
import os
import zipfile
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from autonomous_operations_issue import github_request, REPO


class StripAuthorization(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target=super().redirect_request(req,fp,code,msg,headers,newurl)
        if target:target.remove_header('Authorization')
        return target


def main():
    out=Path('audit-results/gsc-search-pilot.json');out.parent.mkdir(exist_ok=True)
    token=os.environ.get('GITHUB_TOKEN','')
    try:
        sha=github_request('/git/ref/heads/main',token)['object']['sha']
        runs=github_request('/actions/workflows/ga4-three-day-analysis.yml/runs?branch=main&status=success&per_page=10',token)['workflow_runs']
        run=next((r for r in runs if r.get('head_sha')==sha and r.get('event') in ('schedule','push','workflow_dispatch') and r.get('conclusion')=='success'),None)
        if not run:raise ValueError('Exact-main authenticated source unavailable')
        artifacts=github_request(f"/actions/runs/{run['id']}/artifacts?per_page=100",token)['artifacts']
        matches=[a for a in artifacts if a['name']=='ga4-three-day-report' and not a['expired'] and a['size_in_bytes']<2_000_000]
        if len(matches)!=1:raise ValueError('Unique bounded GSC artifact unavailable')
        req=Request(f"https://api.github.com/repos/{REPO}/actions/artifacts/{matches[0]['id']}/zip",headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
        with build_opener(StripAuthorization()).open(req,timeout=30) as response:raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Oversized artifact')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            member=archive.getinfo('gsc-search-pilot.json')
            if member.file_size>1_000_000:raise ValueError('Oversized report')
            report=json.loads(archive.read(member))
        # Do not republish raw queries; original aggregate source remains distinct.
        report.pop('top_queries',None)
        report['reference_run_id']=run['id'];report['reference_main_sha']=sha
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print('STEP6 reference: existing authenticated run',run['id'])
    except Exception:
        out.write_text(json.dumps({'source':'Search Console Search Analytics API','status':'NOT_CONNECTED',
                                   'site_property':'https://stusaurus.github.io/daily-cost-jp/'}))
        print('STEP6 reference: unavailable, not zero traffic')


if __name__=='__main__':main()
