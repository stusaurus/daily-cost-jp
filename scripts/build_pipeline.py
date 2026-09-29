"""One acquisition/render/validation path for PR, push and scheduled builds.

Deployment and actual X publication remain separate workflow jobs.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    'build_realtime_products',
    'enable_realtime_search',
    'improve_seo',
    'improve_category_seo',
    'improve_category_design',
    'sharpen_home_value_prop',
    'build_dynamic_trends_v2',
    'expand_ranking_detail',
    'fill_ranking_gaps',
    'fix_trend_query_links',
    'improve_trend_labels',
    'sync_trend_search_chips',
    'promote_home_ranking',
    'move_home_ranking_below_tools',
    'polish_home_design',
    'add_exact_store_compare',
    'add_daily_buy_picks',
    'build_daily_deals',
    'diversify_daily_deals',
    'build_daily_og',
    'jump_to_rank11',
    'simplify_product_ranking_cta',
    'improve_realtime_search_ux',
    'add_trust_faq',
    'add_trend_conversion_tracking',
    'add_search_landing_pages',
    'improve_purchase_pages',
    'add_back_to_top',
    'add_analytics',
    'validate_generated_site',
    'validate_product_quality',
)


def write_build_info(root=ROOT):
    site = root / 'site'
    catalog = json.loads((site / 'data.json').read_text(encoding='utf-8'))
    report = json.loads((root / 'quality-report.json').read_text(encoding='utf-8'))
    social = json.loads((site / 'social/latest.json').read_text(encoding='utf-8'))
    info = {
        'commit': os.environ.get('GITHUB_SHA', ''),
        'run_id': os.environ.get('GITHUB_RUN_ID', ''),
        'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
        'event': os.environ.get('GITHUB_EVENT_NAME', ''),
        'catalog_updated_at': catalog['updated_at'],
        'recommendations_generated_at': social['generated_at'],
        'categories': {cid: {
            'published': len(data['items']),
            'before_supplemental': report[cid].get('acquisition', {}).get('baseline', {}).get('ranked'),
            'requests': len(report[cid].get('acquisition', {}).get('requests', [])),
            'supplemental_requests': sum(bool(r.get('supplementary')) for r in report[cid].get('acquisition', {}).get('requests', [])),
        } for cid, data in catalog['categories'].items()},
        'files': {path: hashlib.sha256((site / path).read_bytes()).hexdigest() for path in (
            'data.json', 'today/data.json', 'social/latest.json',
            'index.html', 'today/index.html', 'categories/tissue/index.html')},
    }
    (site / 'build-info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    # Only the generated directory. Never carry old recommendations/OG images
    # into a second build, and never follow a symlink to another directory.
    site = ROOT / 'site'
    if site.is_symlink():
        raise SystemExit('Refusing to clean a symlinked output directory')
    if site.exists():
        shutil.rmtree(site)
    for name in STEPS:
        print(f'::group::{name}', flush=True)
        try:
            subprocess.run([sys.executable, f'scripts/{name}.py'], cwd=ROOT, check=True)
        except subprocess.CalledProcessError:
            if name != 'build_daily_og':
                raise
            print('Optional OG image unavailable; no old image reused.', flush=True)
        finally:
            print('::endgroup::', flush=True)
    verification_file = ROOT / 'googlef35e71acece62b67.html'
    if verification_file.exists():
        shutil.copy2(verification_file, site / verification_file.name)
    write_build_info()


if __name__ == '__main__':
    main()
