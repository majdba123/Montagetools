from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    builder = (ROOT / 'tools' / 'build_latest_release.ps1').read_text(encoding='utf-8')
    memory = (ROOT / 'extension' / 'py' / 'hexa_v31' / 'recovery' / 'memory.py').read_text(encoding='utf-8')

    assert "Join-Path $root 'recovery_data'" in builder
    assert "Join-Path $stage 'recovery_data'" in builder
    assert "Join-Path $stage 'extension\\recovery_data'" in builder
    assert "extension\\recovery_data\\proven_solutions.json" in builder
    assert "problem_registry.json" in builder
    assert "recovery_history.json" in builder

    # Installed runtime lookup must prefer the extension-local snapshot, while a
    # source checkout still resolves the root version-controlled authority.
    assert "parents[3] / 'recovery_data' / 'proven_solutions.json'" in memory
    assert "parents[4] / 'recovery_data' / 'proven_solutions.json'" in memory
    assert 'HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH' in memory
    assert 'def record(' in memory
    assert 'Compatibility no-op' in memory

    print('V31_RECOVERY_RELEASE_CONTRACT_PASS')


if __name__ == '__main__':
    main()
