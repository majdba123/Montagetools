from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.store import RecoveryStore


def main():
    recovery_root = ROOT / 'recovery'
    data_root = ROOT / 'recovery_data'
    assert recovery_root.is_dir()
    assert data_root.is_dir()

    expected_code = {'__init__.py', 'detector.py', 'engine.py', 'errors.py', 'models.py', 'store.py'}
    assert expected_code.issubset({path.name for path in recovery_root.iterdir()})
    expected_data = {
        'recovery_schema.json',
        'problem_registry.json',
        'proven_solutions.json',
        'recovery_history.json',
    }
    assert expected_data.issubset({path.name for path in data_root.iterdir()})

    store = RecoveryStore(data_root)
    registry = store.load_registry()
    proven = store.load_proven()
    history = store.load_history()

    problem = store.problem('HEXA_MOTION_PATH_OVERLAP')
    assert problem is not None
    assert set(problem['allowed_sources']) == {'CI', 'RENDER'}

    pending = [
        row for row in history['records']
        if row.get('problem_id') == 'HEXA_MOTION_PATH_OVERLAP'
        and row.get('status') == 'CI_VERIFIED_RENDER_PENDING'
    ]
    assert pending, 'current recovered CI defect must remain render-pending'
    assert all((row.get('technical_approval') or {}).get('status') == 'PASS' for row in pending)
    assert all((row.get('visual_approval') or {}).get('status') == 'PENDING' for row in pending)

    # No CI-only candidate may leak into the proven solution table.
    current_proven = [
        row for row in proven['solutions']
        if row.get('problem_id') == 'HEXA_MOTION_PATH_OVERLAP'
    ]
    assert not current_proven, 'motion-path fix is not visually approved yet'

    schema = json.loads((data_root / 'recovery_schema.json').read_text(encoding='utf-8'))
    assert schema['promotion_rule']['requires']['technical_approval.status'] == 'PASS'
    assert schema['promotion_rule']['requires']['visual_approval.status'] == 'PASS'
    assert schema['runtime_policy']['unknown_problem'] == 'FAIL_CLOSED'
    assert schema['runtime_policy']['known_problem_without_proven_solution'] == 'RECOVERY_SOLUTION_NOT_FOUND'

    # Reusable code and proven matching data must never hardcode the historical
    # acceptance-project instance. Raw instance ids are allowed only in history.
    forbidden = ('S017_P_M017', 'S019_P_M019', 'VCARD_009', 'BALANCE_LIMIT')
    reusable_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in sorted(recovery_root.glob('*.py'))
    ) + '\n' + (data_root / 'proven_solutions.json').read_text(encoding='utf-8')
    for token in forbidden:
        assert token not in reusable_text, token

    # Registry ids are unique and every source is explicit.
    ids = [row['problem_id'] for row in registry['problems']]
    assert len(ids) == len(set(ids))
    assert all(row.get('allowed_sources') for row in registry['problems'])

    print('RECOVERY_REPOSITORY_CONTRACT_PASS')


if __name__ == '__main__':
    main()
