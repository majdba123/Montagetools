from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recovery.detector import detect_problem
from recovery.errors import RecoveryProblemUnknown


def main():
    ci = detect_problem(
        'FINAL_PHYSICAL_CERTIFICATION_FAILED: VCARD_777@12.34s: motion-path overlap EVT_A x EVT_B=0.050>0.015',
        'CI',
        metadata={
            'actor_a_role': 'PRIMARY',
            'actor_b_role': 'PRIMARY',
            'cross_scene': True,
            'same_visual_card': True,
            'render_mode_a': 'ROOT_ATOMIC',
            'render_mode_b': 'ROOT_ATOMIC',
        },
    )
    assert ci.problem_id == 'HEXA_MOTION_PATH_OVERLAP'
    assert ci.source == 'CI'
    assert ci.metadata['card_id'] == 'VCARD_777'
    assert ci.metadata['event_a'] == 'EVT_A'
    assert ci.metadata['event_b'] == 'EVT_B'
    assert ci.metadata['time_seconds'] == 12.34
    assert 'card_id' not in ci.fingerprint
    assert 'event_a' not in ci.fingerprint
    assert 'event_b' not in ci.fingerprint
    assert 'time_seconds' not in ci.fingerprint
    assert ci.fingerprint['cross_scene'] is True

    render = detect_problem(
        'visible sweep crosses the previous primary',
        'RENDER',
        render_code='MOTION_PATH_OVERLAP',
        metadata={
            'actor_a_role': 'PRIMARY',
            'actor_b_role': 'PRIMARY',
            'cross_scene': True,
            'same_visual_card': True,
        },
    )
    assert render.problem_id == ci.problem_id
    assert render.source == 'RENDER'

    expected = {
        'STALE_ACTOR': 'HEXA_RENDER_STALE_ACTOR',
        'WEAK_FOCUS': 'HEXA_RENDER_WEAK_FOCUS',
        'POSTER_LIKE_CARD': 'HEXA_RENDER_POSTER_LIKE_CARD',
        'BAD_HANDOFF': 'HEXA_RENDER_BAD_HANDOFF',
        'VISUAL_SYNC': 'HEXA_RENDER_VISUAL_SYNC',
        'VIEWPORT_CLIPPING': 'HEXA_VIEWPORT_CLIPPING',
    }
    for code, problem_id in expected.items():
        incident = detect_problem('visual review issue', 'RENDER', render_code=code)
        assert incident.problem_id == problem_id, (code, incident)
        assert incident.stage == 'ENCODED_VIDEO_VISUAL_REVIEW'

    settled = detect_problem('VCARD_X settled overlap between A and B', 'CI')
    assert settled.problem_id == 'HEXA_SETTLED_GEOMETRY_OVERLAP'

    clipping = detect_problem('actor viewport clipping outside safe frame', 'CI')
    assert clipping.problem_id == 'HEXA_VIEWPORT_CLIPPING'

    try:
        detect_problem('some totally new failure class', 'CI')
    except RecoveryProblemUnknown as exc:
        assert 'RECOVERY_PROBLEM_UNKNOWN' in str(exc)
    else:
        raise AssertionError('unknown problems must fail closed')

    print('RECOVERY_DETECTOR_PASS')


if __name__ == '__main__':
    main()
