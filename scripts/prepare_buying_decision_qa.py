"""Exercise the approved display state on an unpublished real-build copy.

No API calls, source-offer edits, production flags, or live feedback overrides.
The existing controller's strict product/freshness checks remain in force.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from bs4 import BeautifulSoup
from buying_decision_summary import build
from step4_automation import build_content, diagnose


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if (source == output or source in output.parents or output in source.parents or
            output.exists()):
        raise ValueError('QA output must be a new directory outside the source')
    source_catalog = (source / 'data.json').read_bytes()
    snapshot = json.loads(source_catalog)
    control = diagnose(snapshot, enabled=True)
    if control['content_action'] != 'ALLOW_FIXED_SELECTION':
        raise ValueError('Strict controller rejected active QA data')
    shutil.copytree(source, output)
    for cid in ('laundry', 'tissue', 'toilet-paper'):
        page = output / 'categories' / cid / 'index.html'
        soup = BeautifulSoup(page.read_text(), 'html.parser')
        for layer in soup.select('.step4-recommendations, #buying-decisions, '
                                 '#buying-decisions-css, #step4-purpose-style'):
            layer.decompose()
        page.write_text(str(soup))
    # This is the same unpublished-preview pattern as step4_prepare_candidate:
    # locally validated feedback, explicitly not a real-token/publication proof.
    build_content(output, {'STEP4_ENABLE_CONTENT': 'true'}, feedback=control)
    build(output)
    if (output / 'data.json').read_bytes() != source_catalog:
        raise ValueError('Source product catalog changed during QA preparation')
    receipt = {'mode': 'UNPUBLISHED_ACTIVE_DISPLAY', 'real_token_verified': False,
               'catalog_sha256': hashlib.sha256(source_catalog).hexdigest()}
    (output / 'buying-decision-qa-mode.json').write_text(json.dumps(receipt))
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
