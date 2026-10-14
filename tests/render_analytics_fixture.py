"""Offline production product-page pipeline for the JS integration tests."""
from datetime import datetime
from pathlib import Path
import contextlib
import io
import os
import runpy
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
# No network calls: only render functions are invoked, never the API builders.
os.environ['RAKUTEN_APPLICATION_ID'] = 'offline-test'
os.environ['RAKUTEN_ACCESS_KEY'] = 'offline-test'
import build_site_products
from add_analytics import inject_file

with tempfile.TemporaryDirectory() as directory:
    os.chdir(directory)
    page = Path('site/products/index.html')
    page.parent.mkdir(parents=True)
    page.write_text(build_site_products.product_page([], datetime(2026, 9, 14)), encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):
        for script in ['enable_realtime_search.py', 'improve_realtime_search_ux.py', 'add_trend_conversion_tracking.py']:
            runpy.run_path(str(ROOT / 'scripts' / script), run_name='__main__')
        inject_file(page, 'G-GFVSZ8YDQ5')
    print(page.read_text(encoding='utf-8'))
