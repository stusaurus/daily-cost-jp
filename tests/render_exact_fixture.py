"""Reproduce editorial relocation of the exact-comparison section."""
from pathlib import Path
from bs4 import BeautifulSoup
import contextlib
import io
import os
import runpy
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    os.chdir(directory)
    page = Path('site/index.html')
    page.parent.mkdir()
    page.write_text('<html><head><style></style></head><body><main><section class="product-finder-home" id="product-finder-home"></section></main></body></html>', encoding='utf-8')
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(root / 'scripts/add_exact_store_compare.py'), run_name='__main__')
    soup = BeautifulSoup(page.read_text(), 'html.parser')
    # redesign_laboratory moves only the section, leaving its script earlier.
    soup.main.append(soup.select_one('#exact-store-compare').extract())
    print(soup)
