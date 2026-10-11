"""CI-only ACTIVE/fallback integration over real build bytes; never deploys."""
import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from step4_recommendations import apply, CATEGORIES
from validate_product_quality import validate


def strip_layer(text):
    text = re.sub(r'<details class="step4-home-purpose">.*?</details>', '', text, flags=re.S)
    text = re.sub(r'<section\b[^>]*data-step4-category=[^>]*>.*?</section>', '', text, flags=re.S)
    return re.sub(r'<style id="step4-purpose-style">.*?</style>', '', text, flags=re.S)


def verify(source=Path('site'), report_path=Path('quality-report.json')):
    errors, baseline_stats = validate(source, report_path)
    if errors:
        raise ValueError('Source build failed the full product gate')
    original_data = (source / 'data.json').read_bytes()
    pages = ['index.html'] + [f'categories/{cid}/index.html' for cid in CATEGORIES]
    result = {'mode': 'UNPUBLISHED_REAL_BUILD_INTEGRATION', 'original_catalog_unchanged': True,
              'original_ranking_html_unchanged': True, 'baseline': baseline_stats, 'modes': {},
              'automatic_deploy': False, 'sales_status': 'NOT_CONNECTED'}
    with tempfile.TemporaryDirectory() as directory:
        for name, enabled in (('ACTIVE', True), ('FALLBACK', False)):
            root = Path(directory) / name
            shutil.copytree(source, root)
            protected = {}
            for rel in pages:
                p = root / rel
                protected[rel] = strip_layer(p.read_text())
                p.write_text(protected[rel])
            # Explicitly exercise both display modes ONLY on a temporary copy.
            selection = apply(root, enabled=enabled)
            if selection['status'] != 'TRUSTED_RECENT':
                raise ValueError('Real integration snapshot is not recent/trusted')
            assert (root / 'data.json').read_bytes() == original_data
            assert all(strip_layer((root / rel).read_text()) == text for rel, text in protected.items())
            errors, stats = validate(root, report_path)
            if errors:
                raise ValueError(f'{name} failed product link validation: ' + '; '.join(errors))
            rendered_slots = sum(bool(row) for c in selection['categories'].values() for row in c['slots'].values()) if enabled else 0
            result['modes'][name] = {'status': 'PASS', 'rendered_slots': rendered_slots, 'quality_stats': stats}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, default=Path('site'))
    parser.add_argument('--quality-report', type=Path, default=Path('quality-report.json'))
    args = parser.parse_args()
    result = verify(args.site, args.quality_report)
    output = Path('audit-results/step5-product-link-integration.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
