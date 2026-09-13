from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.errors import RecoveryDataError, RecoveryPromotionRejected
from recovery.store import RecoveryStore


def write(path: pathlib.Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def seed(root: pathlib.Path) -> RecoveryStore:
    root.mkdir(parents=True, exist_ok=True)
    write(root / 'problem_registry.json', {
        'schema': 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1',
        'problems': [
            {
                'problem_id': 'P1',
                'canonical_name': 'problem one',
                'allowed_sources': ['CI', 'RENDER'],
                'reusable_fingerprint_fields': ['cross_scene', 'actor_a_role'],
            }
        ],
    })
    write(root / 'proven_solutions.json', {
        'schema': 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1',
        'solutions': [],
    })
    write(root / 'recovery_history.json', {
        'schema': 'HEXA_RECOVERY_HISTORY_V1',
        'records': [],
    })
    return RecoveryStore(root)


def valid_solution(solution_id='SOL-1', *, constraints=None, visual_count=1, cost=4.0):
    return {
        'solution_id': solution_id,
        'problem_id': 'P1',
        'status': 'PROVEN',
        'strategy': 'SAFE_HANDOFF',
        'fingerprint_constraints': constraints or {'cross_scene': True},
        'successful_visual_validations': visual_count,
        'average_cost': cost,
        'technical_approval': {
            'status': 'PASS',
            'source_commit': 'a' * 40,
        },
        'visual_approval': {
            'status': 'PASS',
            'render_sha256': 'b' * 64,
            'reviewed_against': 'encoded MP4 + visual requirements',
        },
    }


def expect_raises(exc_type, fn, token=None):
    try:
        fn()
    except exc_type as exc:
        if token:
            assert token in str(exc), (token, str(exc))
        return exc
    raise AssertionError(f'expected {exc_type.__name__}')


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = pathlib.Path(temp_dir) / 'recovery_data'
        store = seed(root)

        assert store.problem('P1')['canonical_name'] == 'problem one'
        assert store.problem('UNKNOWN') is None
        assert store.proven_solutions('P1', {'cross_scene': True}) == []

        # Promotion requires BOTH technical and visual proof.
        missing_visual = valid_solution('SOL-NO-VISUAL')
        missing_visual['visual_approval']['status'] = 'PENDING'
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(missing_visual),
            'PROVEN_REQUIRES_VISUAL_PASS',
        )

        missing_technical = valid_solution('SOL-NO-CI')
        missing_technical['technical_approval']['status'] = 'FAIL'
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(missing_technical),
            'PROVEN_REQUIRES_TECHNICAL_PASS',
        )

        missing_sha = valid_solution('SOL-NO-RENDER-SHA')
        missing_sha['visual_approval']['render_sha256'] = ''
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(missing_sha),
            'PROVEN_REQUIRES_VALID_RENDER_SHA256',
        )

        malformed_sha = valid_solution('SOL-BAD-RENDER-SHA')
        malformed_sha['visual_approval']['render_sha256'] = 'not-a-sha'
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(malformed_sha),
            'PROVEN_REQUIRES_VALID_RENDER_SHA256',
        )

        missing_review = valid_solution('SOL-NO-REVIEW')
        missing_review['visual_approval']['reviewed_against'] = ''
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(missing_review),
            'PROVEN_REQUIRES_VISUAL_REVIEW_TARGET',
        )

        missing_commit = valid_solution('SOL-NO-COMMIT')
        missing_commit['technical_approval']['source_commit'] = ''
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(missing_commit),
            'PROVEN_REQUIRES_VALID_SOURCE_COMMIT',
        )

        malformed_commit = valid_solution('SOL-BAD-COMMIT')
        malformed_commit['technical_approval']['source_commit'] = '1234'
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(malformed_commit),
            'PROVEN_REQUIRES_VALID_SOURCE_COMMIT',
        )

        no_visual_validation = valid_solution('SOL-NO-VISUAL-COUNT', visual_count=0)
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(no_visual_validation),
            'PROVEN_REQUIRES_SUCCESSFUL_VISUAL_VALIDATION',
        )

        unknown_problem = valid_solution('SOL-UNKNOWN')
        unknown_problem['problem_id'] = 'P404'
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(unknown_problem),
            'PROVEN_REQUIRES_REGISTERED_PROBLEM',
        )

        instance_hardcode = valid_solution(
            'SOL-HARDCODED', constraints={'cross_scene': True, 'card_id': 'VCARD_009'}
        )
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(instance_hardcode),
            'PROVEN_FORBIDS_INSTANCE_FINGERPRINT_FIELDS',
        )

        unknown_constraint = valid_solution(
            'SOL-UNKNOWN-CONSTRAINT', constraints={'cross_scene': True, 'magic_layout': 'LEFT'}
        )
        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(unknown_constraint),
            'PROVEN_UNKNOWN_FINGERPRINT_FIELDS',
        )

        # A valid promotion is persisted and can be matched by generic fingerprint.
        store.promote_solution(valid_solution('SOL-GOOD', constraints={
            'cross_scene': True,
            'actor_a_role': ['PRIMARY', 'SUPPORTING'],
        }))
        matches = store.proven_solutions('P1', {
            'cross_scene': True,
            'actor_a_role': 'PRIMARY',
            'irrelevant_instance_id': 'ANY',
        })
        assert [row['solution_id'] for row in matches] == ['SOL-GOOD']
        assert store.proven_solutions('P1', {'cross_scene': False, 'actor_a_role': 'PRIMARY'}) == []
        assert store.proven_solutions('P1', {'cross_scene': True}) == []  # required key absent

        expect_raises(
            RecoveryPromotionRejected,
            lambda: store.promote_solution(valid_solution('SOL-GOOD')),
            'DUPLICATE_PROVEN_SOLUTION_ID',
        )

        store.append_history({'history_id': 'H1', 'problem_id': 'P1', 'status': 'DETECTED'})
        assert store.load_history()['records'][0]['history_id'] == 'H1'
        expect_raises(
            RecoveryDataError,
            lambda: store.append_history({'history_id': 'H1', 'problem_id': 'P1', 'status': 'DETECTED'}),
            'duplicate history_id',
        )
        expect_raises(
            RecoveryDataError,
            lambda: store.append_history({'history_id': 'H2', 'problem_id': 'P404', 'status': 'DETECTED'}),
            'HISTORY_UNKNOWN_PROBLEM_ID',
        )
        expect_raises(
            RecoveryDataError,
            lambda: store.append_history({'history_id': 'H3', 'problem_id': 'P1', 'status': 'MAGIC'}),
            'HISTORY_INVALID_STATUS',
        )

        # Persisted bad PROVEN data must fail loudly rather than poisoning matching.
        bad_persisted = valid_solution('SOL-PERSISTED-HARDCODE')
        bad_persisted['fingerprint_constraints'] = {'card_id': 'VCARD_009'}
        write(root / 'proven_solutions.json', {
            'schema': 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1',
            'solutions': [bad_persisted],
        })
        expect_raises(
            RecoveryDataError,
            store.load_proven,
            'PROVEN_FORBIDS_INSTANCE_FINGERPRINT_FIELDS',
        )

        # Corruption must be surfaced rather than silently treated as no knowledge.
        (root / 'problem_registry.json').write_text('{broken', encoding='utf-8')
        expect_raises(RecoveryDataError, store.load_registry, 'RECOVERY_DATA_INVALID_JSON')

    with tempfile.TemporaryDirectory() as temp_dir:
        root = pathlib.Path(temp_dir) / 'recovery_data'
        store = seed(root)
        write(root / 'problem_registry.json', {
            'schema': 'WRONG',
            'problems': [],
        })
        expect_raises(RecoveryDataError, store.load_registry, 'SCHEMA_MISMATCH')

    with tempfile.TemporaryDirectory() as temp_dir:
        root = pathlib.Path(temp_dir) / 'recovery_data'
        store = seed(root)
        write(root / 'problem_registry.json', {
            'schema': 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1',
            'problems': [
                {'problem_id': 'DUP', 'allowed_sources': ['CI'], 'reusable_fingerprint_fields': []},
                {'problem_id': 'DUP', 'allowed_sources': ['CI'], 'reusable_fingerprint_fields': []},
            ],
        })
        expect_raises(RecoveryDataError, store.load_registry, 'duplicate problem_id')

    with tempfile.TemporaryDirectory() as temp_dir:
        root = pathlib.Path(temp_dir) / 'recovery_data'
        store = seed(root)
        write(root / 'problem_registry.json', {
            'schema': 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1',
            'problems': [
                {
                    'problem_id': 'BAD-FIELDS',
                    'allowed_sources': ['CI'],
                    'reusable_fingerprint_fields': ['cross_scene', 'card_id'],
                }
            ],
        })
        expect_raises(RecoveryDataError, store.load_registry, 'forbidden reusable_fingerprint_fields')

    print('RECOVERY_STORE_PASS')


if __name__ == '__main__':
    main()
