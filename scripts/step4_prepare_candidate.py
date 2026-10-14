"""Apply only reviewable STEP4 presentation/measurement code to a captured preview."""
import json
import re
import subprocess
import sys
from pathlib import Path
from step4_recommendations import apply
from add_analytics import inject_file

def refresh_diagnostic(old, diagnostic):
    """Keep the candidate controller and its diagnostic helper in one version."""
    pattern = r'<script\b[^>]*\bid=["\']step4-search-diagnostics["\'][^>]*>.*?</script>'
    matches = list(re.finditer(pattern, old, re.S))
    if len(matches) > 1:
        raise ValueError('Expected at most one captured diagnostic helper')
    if matches:
        m = matches[0]
        return old[:m.start()] + diagnostic + old[m.end():]
    if old.count('</head>') != 1:
        raise ValueError('Expected one head for diagnostic helper')
    return old.replace('</head>', diagnostic + '</head>', 1)

def main(site=Path('audit-results/step4-preview-after')):
    # Reuse the existing production renderer and strictly offline API fixture.
    markup=subprocess.check_output([sys.executable,'tests/render_analytics_fixture.py'],text=True)
    from bs4 import BeautifulSoup
    fixture=BeautifulSoup(markup,'html.parser')
    new_script=next(s for s in fixture.find_all('script') if 'const API =' in s.get_text())
    diagnostic=fixture.select_one('#step4-search-diagnostics')
    page=site/'products/index.html';old=page.read_text()
    scripts=list(re.finditer(r'<script\b[^>]*>.*?</script>',old,re.S))
    target=[m for m in scripts if 'const API =' in m.group()]
    if len(target)!=1:raise ValueError('Expected exactly one realtime search script')
    m=target[0];old=old[:m.start()]+str(new_script)+old[m.end():]
    if diagnostic is None:raise ValueError('Candidate diagnostic helper missing')
    old=refresh_diagnostic(old,str(diagnostic))
    page.write_text(old)
    (site/'assets/purchase-tools.js').write_text(Path('scripts/purchase_tools.js').read_text())
    for path in site.rglob('index.html'):inject_file(path,'G-GFVSZ8YDQ5')
    from step4_automation import build_content,diagnose
    snapshot=json.loads((site/'data.json').read_text())
    control=diagnose(snapshot,True)
    build_content(site,{'STEP4_ENABLE_CONTENT':'true'},feedback=control)
    (site/'step4-preview-mode.json').write_text(json.dumps({'mode':'OFFLINE_CURRENT_DATA_FEEDBACK','real_token_verified':False}))
    print('Applied unpublished STEP4 candidate; pricing/URLs/catalog retained')
if __name__=='__main__':main()
