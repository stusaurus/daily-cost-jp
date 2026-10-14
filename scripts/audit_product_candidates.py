"""Read-only live acquisition check: local artifacts, no deploy/social posting."""
import json
from pathlib import Path

import build_site_growth as growth
from validate_product_quality import validate_catalog


def main():
    growth.core.build_site()
    payload = json.loads(Path('site/data.json').read_text())
    errors, _ = validate_catalog(payload)
    if errors:
        raise SystemExit('\n'.join(errors))
    report = json.loads(Path('quality-report.json').read_text())
    for category, row in report.items():
        acquisition = row.get('acquisition', {})
        print(json.dumps({'category': category, 'baseline': acquisition.get('baseline'),
                          'requests': len(acquisition.get('requests', [])),
                          'unique_candidates': row['checked'], 'accepted': row['accepted'],
                          'published': row['published'], 'reasons': row['reasons']}, ensure_ascii=False))
    print('Live candidate quality checks passed.')


if __name__ == '__main__':
    main()
