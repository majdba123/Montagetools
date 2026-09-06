from __future__ import annotations

import copy

from hexa_v31.interaction.director import (
    _commit_actions,
    assert_final_motion_plan_immutable,
    finalize_interaction_motion_plan,
)
from hexa_v31.planning.preset_story_planner import (
    _final_physical_certification,
    _finalize_visual_lifetimes,
)


event={
    'event_id':'EVENT_A','scene_id':'SCENE_A','visual_card_id':'CARD_A',
    'physical_id':'PHYS_A','render_mode':'ROOT_ATOMIC','partition_root_id':'ROOT_A',
    'start_seconds':0.0,'end_seconds':1.4,'physical_start_seconds':0.0,
    'physical_end_seconds':1.4,'motion_start_seconds':0.0,'motion_end_seconds':0.8,
    'visibility_interval_seconds':[0.0,1.4],'perceptual_hit_seconds':0.56,
    'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':0.0,'duration_seconds':0.8},
    'preset_actions':[],'preset_exit':None,'motion_intervals':[],
    'card_rest_position_norm':[0.5,0.5],'source_bbox_norm':[0.4,0.4,0.2,0.2],
    'planned_rect_norm':[0.4,0.4,0.2,0.2],'collision_envelope_rect_norm':[0.4,0.4,0.2,0.2],
    'layout_scale_multiplier':1.0,'reference_camera_scale':1.0,
    'attention_priority':'PRIMARY','position_animated':True,
}
cards={'cards':[{
    'card_id':'CARD_A','start_seconds':0.0,'end_seconds':1.8,
    'story_phase_plan':{'phases':[{
        'phase_id':'PHASE_A','start_seconds':0.0,'end_seconds':1.8,'event_ids':['EVENT_A'],
    }]},
}]}
plan={'fps':30.0,'events':[event],'visual_cards':cards}

# The planner first produces a valid certified carrier.
_finalize_visual_lifetimes(plan['events'],cards,30.0)
assert _final_physical_certification(plan['events'],cards,30.0)['pass']
planner_physical_end=float(event['physical_end_seconds'])

# The interaction owner appends a real within-frame action whose end lies past
# that prior carrier. This reproduces the stale-authority failure class without
# depending on a package-specific scene or timestamp.
intent={
    'interaction_id':'INTERACTION_A','semantic_action':'TRANSFER',
    'subject_event_id':'EVENT_A','object_event_id':'EVENT_A',
    'visual_card_id':'CARD_A','scene_id':'SCENE_A',
}
schedule={'steps':[{
    'event_id':'EVENT_A','preset':'WITHIN_MIDDLE_TO_RIGHT','phase':'ACTION',
    'start_seconds':1.0,'end_seconds':1.8,'duration_seconds':0.8,
}]}
committed,rejected=_commit_actions(plan,intent,schedule)
assert committed and not rejected,(committed,rejected)
assert float(event['motion_end_seconds'])>float(event['physical_end_seconds'])

# Production re-enters the existing authoritative lifetime reconciliation,
# certifies the exact result, and seals timing against downstream mutation.
finalize_interaction_motion_plan(plan,30.0)
assert float(event['motion_end_seconds'])<=float(event['physical_end_seconds'])
assert float(event['physical_end_seconds'])>planner_physical_end
assert event['preset_actions'] and event['position_animated']
assert plan['interaction_engine'] if plan.get('interaction_engine') else committed
assert_final_motion_plan_immutable(plan)

snapshot=copy.deepcopy(event['preset_actions'])
event['preset_actions'][0]['start_seconds']+=0.1
try:
    assert_final_motion_plan_immutable(plan)
    raise AssertionError('post-certification timing mutation was not rejected')
except ValueError as exc:
    assert 'FINAL_MOTION_PLAN_MUTATED_AFTER_CERTIFICATION' in str(exc)
event['preset_actions']=snapshot
assert_final_motion_plan_immutable(plan)

print('V31_POST_INTERACTION_FINALIZATION_BARRIER_PASS')
