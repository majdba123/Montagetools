"""Reject generated HEXA runtime output from the Git index."""
from __future__ import annotations
import subprocess

FORBIDDEN=(
    '.hexa_real_build', '.hexa_tmp', 'tmp_frames/', '__pycache__/', '.pyc',
    'failure_bundle', 'failure_bundles', 'diagnostics/', 'runs/', 'builds/',
    'rendered/', 'renders/', 'exports/', 'outputs/', 'dist/', '.log',
)

def main():
    tracked=subprocess.check_output(['git','ls-files'],text=True).splitlines()
    bad=[p for p in tracked if any(x in p or p.endswith(x) for x in FORBIDDEN)]
    if bad:
        raise SystemExit('REPOSITORY_HYGIENE_FAIL\n'+'\n'.join(bad))
    print('REPOSITORY_HYGIENE_PASS',len(tracked))

if __name__=='__main__': main()
