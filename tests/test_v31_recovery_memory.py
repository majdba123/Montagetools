from __future__ import annotations

import json
import os
import pathlib
import tempfile

from hexa_v31.recovery.memory import RecoveryMemory


def approved_solution(family: str, strategy: str, *, visual_status: str = 'PASS') -> dict:
    return {
        'solution_id': 'SOL-TEST',
        'problem_id': 'HEXA_MOTION_PATH_OVERLAP',
        'status': 'PROVEN',
        'strategy': strategy,
        'ranking_family': family,
        'successful_visual_validations': 4,
        'average_cost': 3.0,
        'technical_approval': {
            'status': 'PASS',
            'source_commit': 'a' * 40,
        },
        'visual_approval': {
            'status': visual_status,
            'render_sha256': 'b' * 64,
            'reviewed_against': 'encoded MP4 visual review',
        },
    }


def main():
    old_enabled = os.environ.get('HEXA_RECOVERY_MEMORY_ENABLED')
    old_path = os.environ.get('HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH')
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / 'proven_solutions.json'
            os.environ['HEXA_RECOVERY_MEMORY_ENABLED'] = '1'
            os.environ['HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH'] = str(path)

            family = 'DYNAMIC_CROSS_SCENE|PRIMARY|PRIMARY|ENTRY:A|EXIT:B'
            strategies = ['DELAY_0_LEAD_1', 'DELAY_2_LEAD_4']
            payload = {
                'schema': 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1',
                'solutions': [],
            }
            path.write_text(json.dumps(payload), encoding='utf-8')

            memory = RecoveryMemory()
            assert memory.rank(family, strategies) == strategies

            # Technical outcomes are telemetry only. record() must not mutate the
            # repository knowledge or change future ranking before visual approval.
            before = path.read_bytes()
            memory.record(family, strategies[1], True, cost=6.0)
            memory.record(family, strategies[0], False)
            assert path.read_bytes() == before
            assert RecoveryMemory().rank(family, strategies) == strategies

            # A fully proven solution can influence order.
            payload['solutions'] = [approved_solution(family, strategies[1])]
            path.write_text(json.dumps(payload), encoding='utf-8')
            assert RecoveryMemory().rank(family, strategies)[0] == strategies[1]

            # Visual-pending/failed rows are ignored even if marked PROVEN by a
            # malformed hand edit; the compatibility reader fails safe.
            payload['solutions'] = [approved_solution(family, strategies[1], visual_status='PENDING')]
            path.write_text(json.dumps(payload), encoding='utf-8')
            assert RecoveryMemory().rank(family, strategies) == strategies

            # Corrupt knowledge never changes recovery order or breaks CI.
            path.write_text('{broken json', encoding='utf-8')
            assert RecoveryMemory().rank(family, strategies) == strategies

            # Explicit disable always preserves authored deterministic order.
            payload['solutions'] = [approved_solution(family, strategies[1])]
            path.write_text(json.dumps(payload), encoding='utf-8')
            os.environ['HEXA_RECOVERY_MEMORY_ENABLED'] = '0'
            assert RecoveryMemory().rank(family, strategies) == strategies

        print('V31_RECOVERY_MEMORY_PASS')
    finally:
        if old_enabled is None:
            os.environ.pop('HEXA_RECOVERY_MEMORY_ENABLED', None)
        else:
            os.environ['HEXA_RECOVERY_MEMORY_ENABLED'] = old_enabled
        if old_path is None:
            os.environ.pop('HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH', None)
        else:
            os.environ['HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH'] = old_path


if __name__ == '__main__':
    main()
