#!/usr/bin/env python3
"""Fixed local checks, no report-derived command execution and no secrets."""
import json
from pathlib import Path
import subprocess
from autonomous_operations_step2 import TARGET, digest, git, read_optional

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
        if digest(Path(TARGET).read_text()) != plan['candidate_hash'] or git('rev-parse', 'HEAD') != plan['base_sha']:
            raise ValueError('Candidate changed during testing')
        receipt.write_text(json.dumps({'base_sha': plan['base_sha'], 'candidate_hash': plan['candidate_hash'], 'tests': 'PASS'}))
    print('STEP 2 fixed validation suite: PASS')


if __name__ == '__main__':
    main()
