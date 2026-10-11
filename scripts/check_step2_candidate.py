#!/usr/bin/env python3
"""Fixed local checks, no report-derived command execution and no secrets."""
import json
import os
from pathlib import Path
import subprocess
from autonomous_operations_step2 import candidate_target, digest, git, read_optional

COMMANDS = [
    ['python3', '-m', 'unittest', 'discover', '-s', 'tests'],
    ['python3', '-m', 'compileall', '-q', 'scripts'],
    ['npm', 'test'],
    ['node', '--check', 'cloudflare-api/src/safe-index.js'],
]


def main():
    receipt = Path('audit-results/step2-tests.json')
    receipt.unlink(missing_ok=True)
    for command in COMMANDS:
        subprocess.run(command, check=True)
    for path in sorted(Path('scripts').glob('*.js')) + sorted(Path('scripts').glob('*.cjs')):
        subprocess.run(['node', '--check', str(path)], check=True)
    plan = read_optional('audit-results/step2-plan.json')
    if plan and plan.get('recipe'):
        if digest(Path(candidate_target(plan)).read_text(encoding='utf-8')) != plan['candidate_hash'] or git('rev-parse', 'HEAD') != plan['base_sha']:
            raise ValueError('Candidate changed during testing')
        result = {'base_sha': plan['base_sha'], 'candidate_hash': plan['candidate_hash'], 'tests': 'PASS'}
        from autonomous_operations_step3 import RECIPE as ui_recipe
        if plan['recipe'] == ui_recipe:
            command = ['node', 'scripts/step3_ui_audit.cjs', 'verify']
            if os.environ.get('STEP3_LOCAL_SNAPSHOT') == 'true':
                command.append('--snapshot')
            subprocess.run(command, check=True)
            result['ui_verification_hash'] = digest(Path('audit-results/step3-ui/verification.json').read_text(encoding='utf-8'))
        receipt.write_text(json.dumps(result))
    print('STEP 2 fixed validation suite: PASS')


if __name__ == '__main__':
    main()
