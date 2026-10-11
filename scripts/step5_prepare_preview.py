"""Real API purpose pool over a faithful unpublished production capture."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from step4_prepare_candidate import main as apply_current

ROOT=Path('audit-results')


def main():
    before=ROOT/'step4-preview-before';after=ROOT/'step4-preview-after'
    shutil.copytree(before,after)
    # Remove only the independent existing purpose layer; all ranking bytes stay.
    for path in after.rglob('index.html'):
        text=path.read_text()
        text=re.sub(r'<details class="step4-home-purpose">.*?</details>','',text,flags=re.S)
        text=re.sub(r'<section\b[^>]*data-step4-category=[^>]*>.*?</section>','',text,flags=re.S)
        text=re.sub(r'<style id="step4-purpose-style">.*?</style>','',text,flags=re.S)
        path.write_text(text)
    original=json.loads((before/'data.json').read_text())
    subprocess.run([sys.executable,'scripts/step5_household_candidates.py',str(after)],check=True)
    revised=json.loads((after/'data.json').read_text())
    protected=json.loads(json.dumps(revised))
    for cid in ('tissue','laundry','toilet-paper'):
        for key in ('purpose_candidates','household_acquisition'):protected['categories'][cid].pop(key,None)
    expected=json.loads(json.dumps(original))
    for cid in ('tissue','laundry','toilet-paper'):
        for key in ('purpose_candidates','household_acquisition'):expected['categories'][cid].pop(key,None)
    assert protected==expected, 'Original ranking/source changed'
    apply_current(after)
    (ROOT/'step5-acquisition-verification.json').write_text(json.dumps({
        'source':'real API unpublished household preview', 'ranking_unchanged':True,
        'categories':{c:revised['categories'][c]['household_acquisition'] for c in ('tissue','laundry','toilet-paper')},
        'sales_status':'NOT_CONNECTED'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
