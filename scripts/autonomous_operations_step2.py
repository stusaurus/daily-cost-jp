#!/usr/bin/env python3
"""Deterministic fixed recipes. Never execute report/issue text."""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from autonomous_operations_issue import REPO, github_request
from autonomous_operations_triage import SITE, good_path, read_optional

SOURCE = 'daily-cost autonomous operations triage v1'
TARGET = 'docs/autonomous-operations-step1.md'
ANCHOR = '## 既存機能と安全性\n'
GUARD = '- 自動マージ・自動公開は禁止。修正PRはDraftで作成し、人間の承認を待つ。\n'
# Existing equivalent policy must never be rewritten just to manufacture a PR.
LEGACY = '- **この段階では改善PRの自動作成・自動マージ・自動公開は有効化しない。**'
RECIPE = 'restore-operations-safety-documentation-v1'
VERIFY_RECIPE = 'verify-workflow-token-v1'
VERIFY_TARGET = 'docs/step2-token-verification.md'
VERIFY_CONTENT = '# STEP 2 workflow token verification\n\nDO NOT MERGE. This Draft PR is a manual, documentation-only permission test.\nNo site, product, affiliate, analytics, deployment or merge changes are authorized.\n'
VERIFY_WORKFLOW = 'STEP 2 Token Verification (manual, never merge)'
PROTECTED = {'PRODUCT_QUALITY_WARNINGS', 'PRODUCT_QUALITY_FAILURE', 'SEO_SNIPPET_RESEARCH',
             'PRODUCT_PRICE', 'POSTAGE', 'QUANTITY', 'RAKUTEN_LINK', 'SEO_TITLE', 'SAFETY_RULE'}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def repair(text):
    if text.count(ANCHOR) != 1 or len(text) > 100000 or GUARD in text or LEGACY in text:
        return None
    return text.replace(ANCHOR, ANCHOR + '\n' + GUARD, 1)


def classify(report, text, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(report, dict) or report.get('source') != SOURCE or report.get('site') != SITE:
        raise ValueError('Missing or untrusted STEP 1 report')
    try:
        stamp = dt.datetime.fromisoformat(report['generated_at_utc'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Missing timezone')
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError('Invalid report timestamp') from exc
    age = (now - stamp).total_seconds()
    if stamp.tzinfo is None or age < -300 or age > 6 * 3600:
        raise ValueError('Stale or future STEP 1 report')
    findings = report.get('findings')
    if not isinstance(findings, list) or len(findings) > 20:
        raise ValueError('Invalid findings')
    decisions = []
    for f in findings:
        if not isinstance(f, dict) or not good_path(f.get('path')) or not isinstance(f.get('code'), str):
            raise ValueError('Invalid finding')
        # No report flag, supplied recipe, text, path or proposed command can authorize writes.
        decisions.append({'code': f['code'] if re.fullmatch(r'[A-Z][A-Z0-9_]{2,70}', f['code']) else 'UNKNOWN',
                          'path': f['path'],
                          'decision': 'HUMAN_ONLY' if f['code'] in PROTECTED else 'INVESTIGATE'})
    candidate = repair(text)
    if candidate is not None:
        decisions.append({'code': 'OPS_SAFETY_DOCUMENTATION_MISSING', 'path': '/',
                          'decision': 'AUTO_FIX', 'recipe': RECIPE})
    return {'decisions': decisions, 'candidate': candidate,
            'recipe': RECIPE if candidate else None,
            'fingerprint': digest(RECIPE + ':' + TARGET)[:24] if candidate else None}


def prepare():
    report = read_optional('audit-results/autonomous-operations.json')
    target = Path(TARGET)
    if target.is_symlink():
        raise ValueError('Symlink target forbidden')
    original = target.read_text()
    result = classify(report, original)
    result['base_sha'] = git('rev-parse', 'HEAD')
    result['original_hash'] = digest(original)
    candidate = result.pop('candidate')
    if candidate is None:
        from autonomous_operations_step3 import ui_decisions, TARGET as ui_target
        css_path = Path(ui_target)
        if css_path.is_symlink():
            raise ValueError('Symlink UI target forbidden')
        css = css_path.read_text(encoding='utf-8')
        ui = ui_decisions(read_optional('audit-results/step3-ui/report.json'), css, result['base_sha'])
        result['decisions'].extend(ui['decisions'])
        if ui['recipe']:
            original, candidate = css, ui['candidate']
            target = css_path
            result.update(recipe=ui['recipe'], fingerprint=digest(ui['recipe'] + ':' + ui_target)[:24],
                          original_hash=digest(css), ui_evidence_hash=ui['evidence_hash'])
    result['candidate_hash'] = digest(candidate) if candidate is not None else None
    if result['recipe']:
        target.write_text(candidate, encoding='utf-8')
    root = Path('audit-results')
    root.mkdir(exist_ok=True)
    (root / 'step2-plan.json').write_text(json.dumps(result, indent=2))
    (root / 'step2-plan.md').write_text('# STEP 2 safety decisions\n\n' + '\n'.join(
        '- ' + d['decision'] + ': ' + d['code'] + ' ' + d['path'] for d in result['decisions']) +
        '\n\nOnly fixed recipes can produce one tested Draft PR. Human approval required; no automatic publish.\n')
    print('STEP 2: ' + ('candidate prepared' if result['recipe'] else 'no safe fix; no PR'))



def candidate_target(plan):
    if plan.get('recipe') == RECIPE:
        return TARGET
    if plan.get('recipe') == VERIFY_RECIPE:
        return VERIFY_TARGET
    from autonomous_operations_step3 import RECIPE as ui_recipe, TARGET as ui_target
    if plan.get('recipe') == ui_recipe:
        return ui_target
    raise ValueError('Unapproved recipe')


def verification_authorized(env):
    return (env.get('GITHUB_REPOSITORY') == REPO and
            env.get('GITHUB_REF') == 'refs/heads/main' and
            env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
            env.get('GITHUB_WORKFLOW') == VERIFY_WORKFLOW and
            env.get('STEP2_VERIFY_TOKEN') == 'true')


def prepare_verification(env=None):
    env = os.environ if env is None else env
    if not verification_authorized(env):
        raise ValueError('Verification requires explicit manual main workflow')
    target = Path(VERIFY_TARGET)
    if target.exists() or target.is_symlink():
        raise ValueError('Verification file already exists; never overwrite it')
    if subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + VERIFY_TARGET],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError('Verification path already tracked')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(VERIFY_CONTENT, encoding='utf-8')
    plan = {'recipe': VERIFY_RECIPE, 'fingerprint': digest(VERIFY_RECIPE + ':' + VERIFY_TARGET)[:24],
            'base_sha': git('rev-parse', 'HEAD'), 'original_hash': digest(''),
            'candidate_hash': digest(VERIFY_CONTENT),
            'decisions': [{'code': 'MANUAL_TOKEN_VERIFICATION', 'decision': 'HUMAN_ONLY', 'path': '/'}]}
    root = Path('audit-results')
    root.mkdir(exist_ok=True)
    (root / 'step2-plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    print('Manual verification prepared: fixed documentation fixture; DO NOT MERGE')


def all_prs(token, request):
    for page in range(1, 101):
        items = request(f'/pulls?state=all&per_page=100&page={page}', token)
        if not isinstance(items, list):
            raise ValueError('Invalid PR listing')
        yield from items
        if len(items) < 100:
            return
    raise ValueError('PR history exceeds safe pagination bound')


def publish(plan, receipt, token, env, request=github_request):
    if env.get('GITHUB_REPOSITORY') != REPO or env.get('GITHUB_REF') != 'refs/heads/main' or env.get('GITHUB_EVENT_NAME') not in ('push', 'schedule', 'workflow_dispatch'):
        raise ValueError('Write operation restricted to trusted main workflow')
    if not isinstance(plan, dict):
        raise ValueError('Missing preparation plan')
    if not plan.get('recipe'):
        return {'status': 'NO_SAFE_FIX'}
    target = candidate_target(plan)
    verification = plan['recipe'] == VERIFY_RECIPE
    from autonomous_operations_step3 import RECIPE as ui_recipe, repair as ui_repair, ui_decisions
    ui = plan['recipe'] == ui_recipe
    if verification and not verification_authorized(env):
        raise ValueError('Verification cannot run from scheduled repair workflow')
    if plan['fingerprint'] != digest(plan['recipe'] + ':' + target)[:24]:
        raise ValueError('Unapproved recipe')
    sha = plan['base_sha']
    if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha) or git('rev-parse', 'HEAD') != sha:
        raise ValueError('Invalid or changed base commit')
    expected_receipt = {'base_sha': sha, 'candidate_hash': plan['candidate_hash'], 'tests': 'PASS'}
    if ui:
        proof_path = Path('audit-results/step3-ui/verification.json')
        report_path = Path('audit-results/step3-ui/report.json')
        difference_path = Path('audit-results/step3-ui/differences.json')
        proof = read_optional(proof_path)
        if (not proof or proof.get('status') != 'PASS' or proof.get('mode') != 'live' or
                proof.get('screens') != 18 or proof.get('base_sha') != sha or
                proof.get('candidate_hash') != plan['candidate_hash'] or
                proof.get('report_hash') != digest(report_path.read_text(encoding='utf-8')) or
                proof.get('differences_hash') != digest(difference_path.read_text(encoding='utf-8'))):
            raise ValueError('Missing exact UI browser proof')
        expected_receipt['ui_verification_hash'] = digest(proof_path.read_text(encoding='utf-8'))
    if receipt != expected_receipt:
        raise ValueError('Missing exact-candidate test evidence')
    # git helper strips trailing whitespace; read exact bytes for deterministic comparison.
    if verification:
        exists = subprocess.run(['git', 'cat-file', '-e', sha + ':' + target],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if exists:
            raise ValueError('Verification must create only the fixed new file')
        original, expected = '', VERIFY_CONTENT
    else:
        original = subprocess.check_output(['git', 'show', sha + ':' + target]).decode('utf-8')
        expected = ui_repair(original) if ui else repair(original)
        if ui and ui_decisions(read_optional('audit-results/step3-ui/report.json'), original, sha).get('recipe') != ui_recipe:
            raise ValueError('UI cause not reproduced on exact source')
    if Path(target).is_symlink():
        raise ValueError('Symlink candidate forbidden')
    candidate = Path(target).read_text(encoding='utf-8')
    if digest(original) != plan['original_hash'] or expected != candidate or digest(candidate) != plan['candidate_hash']:
        raise ValueError('Candidate differs from approved repair')
    changed = git('diff', '--name-only', sha).splitlines()
    untracked = [p for p in git('ls-files', '--others', '--exclude-standard').splitlines()
                 if not p.startswith('audit-results/')]
    allowed = {target}
    if (not set(changed).issubset(allowed) or not set(untracked).issubset(allowed) or
            set(changed + untracked) != allowed):
        raise ValueError('Unexpected repository changes')
    marker = '<!-- daily-cost-step2:' + plan['fingerprint'] + ' -->'
    branch = 'auto-ops/' + plan['fingerprint']
    for pr in all_prs(token, request):
        if marker in (pr.get('body') or '') or pr.get('head', {}).get('ref') == branch:
            return {'status': 'DUPLICATE_OR_DISMISSED', 'url': pr.get('html_url')}
    run_id = env.get('GITHUB_RUN_ID', '')
    if not run_id.isdigit():
        raise ValueError('Invalid run identity')
    current = request('/git/ref/heads/main', token)['object']['sha']
    if current != sha:
        return {'status': 'MAIN_CHANGED_RETRY_NEXT_CADENCE'}
    try:
        request('/git/ref/heads/' + branch, token)
        return {'status': 'EXISTING_BRANCH_REQUIRES_REVIEW'}
    except HTTPError as exc:
        if exc.code != 404:
            raise
    base = request('/git/commits/' + sha, token)
    tree = request('/git/trees', token, 'POST', {'base_tree': base['tree']['sha'], 'tree': [
        {'path': target, 'mode': '100644', 'type': 'blob', 'content': candidate}]})
    commit = request('/git/commits', token, 'POST', {'message': ('docs: verify workflow token' if verification else 'docs: restore operations safety review policy') + ' [skip netlify]',
                    'tree': tree['sha'], 'parents': [sha]})
    # Create branch at main, then advance it; never touch main or a deployment ref.
    request('/git/refs', token, 'POST', {'ref': 'refs/heads/' + branch, 'sha': sha})
    request('/git/refs/heads/' + branch, token, 'PATCH', {'sha': commit['sha'], 'force': False})
    description = ('Create the fixed manual token-verification document. DO NOT MERGE. ' if verification else
                   'Restore the missing, predefined safety policy under the unique documentation anchor. ')
    if ui:
        description = 'Restore the existing ranking link 44px tap area with one fixed CSS block. '
    scope = 'Only the approved CSS selector changes; no prices, product rules, URLs, SEO, tracking or feature code changes.' if ui else 'Only documentation changes; no product, SEO, analytics or site changes.'
    browser_note = 'PC/390px/320px: 18 before/after screens, protected DOM, search, compare and save checks PASS. Evidence screenshots and geometry differences are in the generating run artifact. ' if ui else 'PC/390px/320px QA not required for a documentation-only diff. '
    body = (marker + '\n\n' + description +
            scope + '\n\n'
            'Evidence: validated fixed candidate, recipe ' + plan['recipe'] + '.\n\n'
            'Before PR creation: complete Python and JavaScript unit/regression suites and syntax checks passed '
            'on candidate hash `' + plan['candidate_hash'] + '`.\n\n'
            'Test run: https://github.com/' + REPO + '/actions/runs/' + run_id + '\n\n' +
            browser_note + 'Human review required. '
            'GITHUB_TOKEN PR event execution is not assumed; tests already ran in the generating job. '
            'No automatic merge or deployment. Related investigation: #74.')
    title = 'docs: restore automatic operations safety policy'
    if ui:
        title = 'fix: restore ranking link tap target (fixed STEP 3 recipe)'
    if verification:
        title = '[DO NOT MERGE] STEP 2 workflow token verification'
        body = marker + '\n\nMANUAL TOKEN VERIFICATION — DO NOT MERGE.\n\n' + body.split('\n\n', 1)[1]
    pr = request('/pulls', token, 'POST', {'head': branch, 'base': 'main', 'draft': True,
                 'title': title + ' [skip netlify]', 'body': body})
    if verification:
        confirmed = request('/pulls/' + str(pr['number']), token)
        if (confirmed.get('draft') is not True or 'auto_merge' not in confirmed or confirmed['auto_merge'] is not None or
                confirmed.get('user', {}).get('login') != 'github-actions[bot]' or
                confirmed.get('base', {}).get('ref') != 'main' or
                confirmed.get('head', {}).get('sha') != commit['sha']):
            raise ValueError('Verification PR is not Draft or has auto-merge enabled')
        paths = request('/pulls/' + str(pr['number']) + '/files?per_page=100', token)
        if not isinstance(paths, list) or len(paths) != 1 or paths[0].get('filename') != VERIFY_TARGET or paths[0].get('status') != 'added':
            raise ValueError('Verification PR diff is not the one allowed new document')
        if request('/git/ref/heads/main', token)['object']['sha'] != sha:
            raise ValueError('Main moved during verification; inspect independently')
    return {'status': 'DRAFT_CREATED', 'url': pr.get('html_url'), 'sha': commit['sha']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'prepare-verification', 'publish'])
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'prepare-verification':
        prepare_verification()
    else:
        try:
            result = publish(read_optional('audit-results/step2-plan.json'),
                             read_optional('audit-results/step2-tests.json'),
                             os.environ.get('GITHUB_TOKEN', ''), os.environ)
        except HTTPError as exc:
            result = {'status': 'GITHUB_API_FAILURE', 'http_status': exc.code}
            Path('audit-results/step2-result.json').write_text(json.dumps(result, indent=2))
            print('STEP 2 stopped: GitHub API HTTP ' + str(exc.code))
            raise SystemExit(1) from None
        Path('audit-results/step2-result.json').write_text(json.dumps(result, indent=2))
        print('STEP 2 publication: ' + result['status'])


if __name__ == '__main__':
    main()
