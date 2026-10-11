"""Exact-candidate real build and protected byte/DOM proof before Draft creation."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from step6_seo_content import TARGET, REGISTRY, MARKER, markup, policy, apply
from step6_seo_audit import digest
from validate_generated_site import validate as validate_seo
from validate_product_quality import validate as validate_products

BEFORE = Path('audit-results/step6-before')
AFTER = Path('audit-results/step6-after')


def prepare(site=Path('site'), quality=Path('quality-report.json'), exercise=False):
    cfg = policy(Path(TARGET).read_text())
    if exercise:
        # CI exercises the first fixed hypothesis, never commits/enables it.
        cfg['pages']['laundry'] = True
    for root in (BEFORE, AFTER):
        if root.is_symlink():
            raise ValueError('Symlink QA directory')
        if root.exists():
            shutil.rmtree(root)
        shutil.copytree(site, root)
        # Exercise current approved STEP4 logic on both unpublished copies,
        # including when the PR build intentionally uses the safe fallback.
        from step5_verify_product_links import strip_layer
        from step4_recommendations import apply as apply_purpose
        for rel in ['index.html']+[f'categories/{c}/index.html' for c in REGISTRY]:
            p=root/rel;p.write_text(strip_layer(p.read_text()))
        if root == BEFORE:
            apply_purpose(root, enabled=True)
    # Remove only exact fixed blocks from candidate to derive its own baseline.
    # All source data, prices, rankings, STEP4/5 and analytics bytes stay intact.
    for cid in REGISTRY:
        path = BEFORE/'categories'/cid/'index.html'
        text = path.read_text()
        block = markup(cid)
        if MARKER in text and text.count(block) != 1:
            raise ValueError('Unknown SEO block shape')
        path.write_text(text.replace(block, ''))
    shutil.copytree(BEFORE, AFTER, dirs_exist_ok=True)
    apply(AFTER, cfg)
    for root in (BEFORE, AFTER):
        errors, _ = validate_products(root, quality)
        if errors:
            raise ValueError('Full product gate failed in SEO verification')
        errors, _ = validate_seo(root)
        if errors:
            raise ValueError('SEO/canonical/sitemap/internal link gate failed: ' + '; '.join(errors))
    compared = 0
    for p in BEFORE.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(BEFORE)
        before, after = p.read_bytes(), (AFTER/rel).read_bytes()
        cid = next((c for c in REGISTRY if rel.as_posix() == f'categories/{c}/index.html'), None)
        expected = before.decode().replace('</main>', markup(cid)+'</main>', 1).encode() if cid and cfg['pages'][cid] else before
        if expected != after:
            raise ValueError('Unexpected protected file change: ' + rel.as_posix())
        compared += 1
    result = {'status':'PASS','files_compared':compared,'product_gate':'PASS','seo_gate':'PASS',
              'protected_data_and_rankings':'PASS','catalog_hash':digest((site/'data.json').read_text()),
              'quality_hash':digest(quality.read_text()),'enabled_pages':[c for c,v in cfg['pages'].items() if v]}
    Path('audit-results/step6-build-proof.json').write_text(json.dumps(result,indent=2))
    return result


def finish(plan=None):
    proof_path = Path('audit-results/step6-build-proof.json')
    browser_path = Path('audit-results/step4-qa/report.json')
    proof = json.loads(proof_path.read_text())
    browser = json.loads(browser_path.read_text())
    pairs = browser.get('pairs', [])
    expected = {(p,w) for p in ('','categories/laundry/','categories/tissue/','categories/toilet-paper/','products/','today/') for w in (1440,390,320)}
    if (browser.get('all_pass') is not True or len(pairs)!=18 or
            {(r['after']['route'],r['after']['width']) for r in pairs}!=expected or
            any(r[k]['status']!='PASS' or r[k]['google_requests']!='BLOCKED' or
                r[k]['affiliate_navigation']!='BLOCKED' for r in pairs for k in ('before','after')) or
            any(r['before']['protected_hash']!=r['after']['protected_hash'] for r in pairs)):
        raise ValueError('Complete protected browser matrix missing')
    result = {**proof,'mode':'REAL_BUILD_NO_PUBLISH','screens':18,'browser':'PASS',
              'build_proof_hash':digest(proof_path.read_text()),'browser_proof_hash':digest(browser_path.read_text()),
              'base_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'candidate_hash':digest(Path(TARGET).read_text()),'automatic_deploy':False}
    if plan and (plan['base_sha']!=result['base_sha'] or plan['candidate_hash']!=result['candidate_hash']):
        raise ValueError('SEO candidate changed during verification')
    Path('audit-results/step6-verification.json').write_text(json.dumps(result,indent=2))
    return result


def validate_receipt(proof, plan):
    if not isinstance(proof,dict):return False
    if any(proof.get(k)!=v for k,v in {'status':'PASS','mode':'REAL_BUILD_NO_PUBLISH','screens':18,
               'browser':'PASS','product_gate':'PASS','seo_gate':'PASS','protected_data_and_rankings':'PASS',
               'base_sha':plan['base_sha'],'candidate_hash':plan['candidate_hash']}.items()):return False
    try:
        return (proof['build_proof_hash']==digest(Path('audit-results/step6-build-proof.json').read_text()) and
                proof['browser_proof_hash']==digest(Path('audit-results/step4-qa/report.json').read_text()) and
                proof['catalog_hash']==digest(Path('site/data.json').read_text()) and
                proof['quality_hash']==digest(Path('quality-report.json').read_text()))
    except (OSError,KeyError):return False


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','finish']);parser.add_argument('--exercise',action='store_true')
    args=parser.parse_args()
    print(json.dumps(prepare(exercise=args.exercise) if args.mode=='prepare' else finish(),indent=2))
