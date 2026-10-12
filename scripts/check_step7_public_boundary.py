#!/usr/bin/env python3
"""Reject private financial artifacts in the tracked public tree, including ignored files forced into git."""
import json
from pathlib import Path
import subprocess

PRIVATE_MARKER='step7-private-revenue-v1'

def inspect(root, paths):
    errors=[]
    for name in paths:
        p=root/name
        if p.is_symlink():
            errors.append('UNVERIFIABLE_SYMLINK_IN_PUBLIC_TREE');continue
        if not p.is_file():continue
        lower=name.lower()
        if p.suffix.lower() in {'.csv','.sqlite','.sqlite3','.db'} or 'monthly-report.' in lower or '.step7-private/' in lower:
            errors.append('PRIVATE_FILE_TYPE_IN_PUBLIC_TREE')
            continue
        with p.open('rb') as handle:prefix=handle.read(16)
        if prefix==b'SQLite format 3\x00':errors.append('PRIVATE_DATABASE_IN_PUBLIC_TREE')
        if p.stat().st_size>10*1024*1024:
            if p.suffix.lower()=='.json':errors.append('UNVERIFIABLE_OVERSIZED_JSON')
            continue
        raw=p.read_bytes()
        if p.suffix.lower()=='.json':
            try:obj=json.loads(raw)
            except (ValueError,UnicodeError):continue
            if isinstance(obj,dict) and obj.get('source')==PRIVATE_MARKER:errors.append('PRIVATE_REPORT_IN_PUBLIC_TREE')
    return sorted(set(errors))

def main():
    root=Path(__file__).resolve().parents[1]
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\x00')
    errors=inspect(root,paths)
    if errors:raise SystemExit('\n'.join(errors))
    print('STEP7 public-tree boundary passed. No financial data read or published.')

if __name__=='__main__':main()
