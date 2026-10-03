"""Fail closed on meaningful catalog regressions, report repeat exposure honestly."""
import json
from pathlib import Path
from price_observations import previous
from validate_product_quality import validate_catalog


def monitor(current, prior, today, history):
    errors, _ = validate_catalog(current)
    warnings = []
    categories = current.get('categories', {})
    older = prior.get('catalog', {}).get('categories', {})
    for cid, cat in categories.items():
        count = len(cat['items']); before = len(older.get(cid, {}).get('items', []))
        if cat.get('error'): errors.append(f'{cid}: acquisition error; preserve last good deployment')
        if before > 0 and count == 0: errors.append(f'{cid}: safe products disappeared')
        if before >= 5 and count < before * .4: errors.append(f'{cid}: product count fell by more than 60% ({before} -> {count})')
        if not count and not before: warnings.append(f'{cid}: no verified candidate')
    if not today.get('items'): errors.append('Today selection empty; preserve last good deployment')
    recent = history.get('selections', [])[-14:]
    if len(recent) >= 6 and len({tuple(e.get('keys', [])) for e in recent}) == 1:
        warnings.append('Today selection unchanged across six updates; no better safe candidate was found')
    old_today = prior.get('today', {})
    if old_today.get('text') == today.get('text'):
        warnings.append('X candidate text identical to previous deployment')
    return errors, warnings


def main():
    site = Path('site')
    current = json.loads((site/'data.json').read_text())
    today = json.loads((site/'today/data.json').read_text())
    history = json.loads((site/'price-observations.json').read_text())
    errors, warnings = monitor(current, previous(), today, history)
    report = {'updated_at':current['updated_at'],'errors':errors,'warnings':warnings,
              'counts':{k:len(v['items']) for k,v in current['categories'].items()},
              'observed_products':len(history['products']),'today_count':len(today['items'])}
    Path('quality-monitor-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (site/'quality-status.json').write_text(json.dumps(report,ensure_ascii=False))
    if errors: raise SystemExit('\n'.join(errors))
    print('Quality monitoring passed:',json.dumps(report,ensure_ascii=False))

if __name__ == '__main__': main()
