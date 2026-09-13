from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.engine import RecoveryEngine
from recovery.errors import RecoveryProblemUnknown, RecoverySolutionNotFound
from recovery.store import RecoveryStore


def write(path: pathlib.Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def solution(solution_id: str, strategy: str, count: int, cost: float, constraints: dict):
    return {
        'solution_id': solution_id,
        'problem_id': 'HEXA_MOTION_PATH_OVERLAP',
        'status': 'PROVEN',
        'strategy': strategy,
        'fingerprint_constraints': constraints,
        'successful_visual_validations': count,
        'average_cost': cost,
        'technical_approval': {'status': 'PASS', 'source_commit': 'a' * 40},
        'visual_approval': {
            'status': 'PASS',
            'render_sha256': 'b' * 64,
            'reviewed_against': 'encoded MP4 visual review',
        },
    }


def build_store(root: pathlib.Path, solutions: list[dict]) -> RecoveryStore:
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'problem_registry.json', {
        'schema': 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1',
        'problems': [
            {
                'problem_id': 'HEXA_MOTION_PATH_OVERLAP',
                'canonical_name': 'motion-path overlap',
                'allowed_sources': ['CI', 'RENDER'],
            },
            {
                'problem_id': 'HEXA_RENDER_BAD_HANDOFF',
                'canonical_name': 'bad handoff',
                'allowed_sources': ['RENDER'],
            },
        ],
    })
    write(root / 'proven_solutions.json', {
        'schema': 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1',
        'solutions': solutions,
    })
    write(root / 'recovery_history.json', {
        'schema': 'HEXA_RECOVERY_HISTORY_V1',
        'records': [],
    })
    return RecoveryStore(root)


def main():
    ci_message = 'VCARD_X@4.25s: motion-path overlap ACTOR_A x ACTOR_B=0.04>0.015'
    fp = {
        'actor_a_role': 'PRIMARY',
        'actor_b_role': 'PRIMARY',
        'cross_scene': True,
        'same_visual_card': True,
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        engine = RecoveryEngine(build_store(pathlib.Path(temp_dir), []))
        incident = engine.detect(ci_message, 'CI', metadata=fp)
        assert incident.problem_id == 'HEXA_MOTION_PATH_OVERLAP'
        try:
            engine.resolve(incident)
        except RecoverySolutionNotFound as exc:
            assert exc.problem_id == 'HEXA_MOTION_PATH_OVERLAP'
            assert exc.source == 'CI'
        else:
            raise AssertionError('known-but-unproven problems must fail closed')

    constraints = {
        'conflict_type': 'MOTION_PATH',
        'actor_a_role': 'PRIMARY',
        'actor_b_role': 'PRIMARY',
        'cross_scene': True,
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        solutions = [
            solution('SOL-LOWER-EVIDENCE', 'STRATEGY_A', 2, 2.0, constraints),
            solution('SOL-BEST', 'STRATEGY_B', 8, 5.0, constraints),
            solution('SOL-SAME-EVIDENCE-CHEAPER', 'STRATEGY_C', 8, 3.0, constraints),
        ]
        engine = RecoveryEngine(build_store(pathlib.Path(temp_dir), solutions))
        ci_incident = engine.detect(ci_message, 'CI', metadata=fp)
        ci_decision = engine.resolve(ci_incident)
        assert ci_decision.solution_id == 'SOL-SAME-EVIDENCE-CHEAPER'
        assert ci_decision.strategy == 'STRATEGY_C'
        assert ci_decision.status == 'PROVEN'

        # The same underlying problem discovered from encoded render uses the same
        # canonical identity and therefore the same proven recovery knowledge.
        render_incident = engine.detect(
            'encoded trajectory visibly intersects the outgoing primary',
            'RENDER',
            render_code='MOTION_PATH_OVERLAP',
            metadata=fp,
        )
        assert render_incident.problem_id == ci_incident.problem_id
        render_decision = engine.resolve(render_incident)
        assert render_decision.solution_id == ci_decision.solution_id

        # A materially different fingerprint must not inherit this solution.
        mismatch = engine.detect(
            ci_message,
            'CI',
            metadata={**fp, 'actor_b_role': 'SUPPORTING'},
        )
        try:
            engine.resolve(mismatch)
        except RecoverySolutionNotFound:
            pass
        else:
            raise AssertionError('fingerprint mismatch reused an unsafe solution')

        # Render-only problem must not be accepted from CI source.
        try:
            engine.detect('visual review issue', 'CI', render_code='BAD_HANDOFF')
        except RecoveryProblemUnknown as exc:
            assert 'SOURCE_NOT_ALLOWED' in str(exc)
        else:
            raise AssertionError('render-only problem accepted from CI')

    print('RECOVERY_ENGINE_PASS')


if __name__ == '__main__':
    main()
