"""Optical scale commits must certify the whole carrier, including later cards."""
from copy import deepcopy

from hexa_v31.planning.preset_story_planner import _optical_scale_optimize
from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.composition_solver import _fp, _rect, MOTION_ENVELOPE_SCALE


def actor(eid, center, bbox, start):
    return {
        'event_id': eid, 'visual_card_id': 'FOLLOWING',
        'source_bbox_norm': [0, 0, *bbox],
        'card_rest_position_norm': [center, .52],
        'layout_scale_multiplier': .68, 'reference_camera_scale': .76,
        'planned_rect_norm': [center-.12, .2, .24, .64],
        'start_seconds': start, 'end_seconds': 6.,
        'physical_start_seconds': start, 'physical_end_seconds': 6.,
        'motion_start_seconds': start, 'motion_end_seconds': 6.,
        'attention_priority': 'PRIMARY',
        'matting': {'opaque_foreground_fraction': .2},
        'composition_states': [{'start_seconds': 3., 'scale_multiplier': 1.14}],
        'translation_safe_after_occlusion': False,
        'preset_entry': {'name':'APPEAR_HIGH_SCALE','start_seconds':start,'duration_seconds':.8},
    }


events=[actor('FOCAL',.75,(.37,.94),1.99),actor('SUPPORT',.34,(.82,.89),2.05)]
events[1]['composition_states'][0]['scale_multiplier']=1.10
events[1]['matting']['opaque_foreground_fraction']=.48
for event in events:
    event['planned_rect_norm']=list(_rect(event['card_rest_position_norm'],_fp(event),.68*MOTION_ENVELOPE_SCALE))
cards={'cards':[
    {'card_id':'PRECEDING','start_seconds':0.,'end_seconds':2.},
    {'card_id':'FOLLOWING','start_seconds':2.,'end_seconds':6.},
]}
assert not card_motion_conflicts(events,2.,6.,30.)
before=deepcopy(events)
stats=_optical_scale_optimize(events,cards,30.)
assert stats['candidates_committed']>0,stats
assert not card_motion_conflicts(events,2.,6.,30.),events
for original,event in zip(before,events):
    for key in ('card_rest_position_norm','start_seconds','end_seconds',
                'physical_start_seconds','physical_end_seconds',
                'motion_start_seconds','motion_end_seconds','composition_states',
                'translation_safe_after_occlusion'):
        assert event[key]==original[key],key
print('V31_COMPOSITION_CROSS_CARD_SCALE_PASS')
