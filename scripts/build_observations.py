import json
from pathlib import Path
from price_observations import previous, update

if __name__ == '__main__':
    payload = json.loads(Path('site/data.json').read_text())
    Path('site/price-observations.json').write_text(json.dumps(update(payload, previous()), ensure_ascii=False),encoding='utf-8')
