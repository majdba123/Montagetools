from __future__ import annotations

import copy

import hexa_v31.design_director as public_director
from hexa_v31.interaction.director import _final_timing_sha256, assert_final_motion_plan_immutable


motion = {
    'events': [{
        'event_id': 'EVENT_A',
        'planned_rect_norm': [0.40, 0.40, 0.20, 0.20],
        'card_rest_position_norm': [0.50, 0.50],
        'layout_scale_multiplier': 1.0,
    }],
}
motion['finalization_barrier'] = {
    'timing_sha256': _final_timing_sha256(motion),
    'pass': True,
}
original = copy.deepcopy(motion)

real_builder = public_director._implementation.build_title_plan
calls = []


def fake_builder(package, alignment, vision_results, candidate_motion, alignment_report=None):
    deferred = list((alignment_report or {}).get('deferred_anchors') or [])
    calls.append(bool(deferred))
    if deferred:
        candidate_motion['events'][0]['planned_rect_norm'] = [0.10, 0.10, 0.20, 0.20]
        candidate_motion['events'][0]['card_rest_position_norm'] = [0.20, 0.20]
    return {
        'schema': 'TEST_TITLE_PLAN',
        'events': [],
        'text_event_count': 0,
        'title_qa': {},
        'pass': True,
    }


try:
    public_director._implementation.build_title_plan = fake_builder
    result = public_director.build_title_plan(
        object(), {}, [], motion,
        {'deferred_anchors': [{'visual_card_id': 'CARD_A'}], 'events': [{}]},
    )
finally:
    public_director._implementation.build_title_plan = real_builder

assert calls == [True, False], calls
assert result.get('post_seal_geometry_rebalance_suppressed') is True
assert motion == original
assert_final_motion_plan_immutable(motion)

print('V31_SEALED_TITLE_PLANNER_READ_ONLY_PASS')
