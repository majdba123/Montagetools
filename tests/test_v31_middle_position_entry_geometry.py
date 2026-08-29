from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.composition_solver import candidate_middle_envelope_geometry, _in_safe
from hexa_v31.preset_story_planner import _schedule_event


def base_event(event_id='E', center=(0.5, 0.52), bbox=(0, 0, .12, .14), scale=1.0):
    rect=[center[0]-bbox[2]*scale*1.12/2, center[1]-bbox[3]*scale*1.12/2, bbox[2]*scale*1.12, bbox[3]*scale*1.12]
    return {
        'event_id': event_id, 'visual_card_id': 'C', 'attention_priority': 'PRIMARY',
        'source_bbox_norm': list(bbox), 'source_center_norm': [0.25, 0.5],
        'reference_camera_scale': 1.0, 'layout_scale_multiplier': scale,
        'card_rest_position_norm': list(center), 'planned_rect_norm': [round(x, 6) for x in rect],
        'collision_envelope_rect_norm': [round(x, 6) for x in rect],
        'start_seconds': 0.0, 'end_seconds': 4.0, 'perceptual_hit_seconds': 1.4,
        'preset_entry': None, 'preset_exit': None, 'preset_actions': [],
    }


card={'card_id':'C','start_seconds':0.0,'end_seconds':4.0}


small=base_event('SMALL', center=(0.49, 0.52), bbox=(0, 0, .12, .14))
_schedule_event(small, (0.0, 4.0), card, 0, 2, local_events=[small])
assert small['appearance_method']=='POSITION_ENTRY', small
assert small['card_rest_position_norm']==[0.5, 0.5], small
assert small['planned_rect_norm']==small['collision_envelope_rect_norm'], small
assert candidate_middle_envelope_geometry(small)['safe'], small


tall=base_event('TALL', center=(0.5, 0.504), bbox=(0, 0, .12, .72))
old_center=list(tall['card_rest_position_norm']); old_rect=list(tall['planned_rect_norm']); old_scale=tall['layout_scale_multiplier']
assert not candidate_middle_envelope_geometry(tall)['safe']
_schedule_event(tall, (0.0, 4.0), card, 0, 2, local_events=[tall])
assert tall['appearance_method']=='SCALE_POP', tall
assert tall['card_rest_position_norm']==old_center, tall
assert tall['planned_rect_norm']==old_rect, tall
assert tall['collision_envelope_rect_norm']==old_rect, tall
assert tall['layout_scale_multiplier']==old_scale, tall
settled_plan={'fps':30,'visual_cards':{'cards':[{'card_id':'C','start_seconds':0,'end_seconds':4,'story_phase_plan':{'phases':[{'phase_id':'P','event_ids':['TALL']}]}}]},'events':[tall]}
assert composition_plan_qa(settled_plan)['pass'], composition_plan_qa(settled_plan)


blocked=base_event('BLOCKED', center=(0.49, 0.52), bbox=(0, 0, .12, .14))
neighbor=base_event('NEIGHBOR', center=(0.5, 0.5), bbox=(0, 0, .18, .18))
neighbor['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':0.0,'duration_seconds':.8}
neighbor['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':3.4,'duration_seconds':.6}
old_center=list(blocked['card_rest_position_norm']); old_rect=list(blocked['planned_rect_norm'])
_schedule_event(blocked, (0.0, 4.0), card, 0, 2, local_events=[blocked, neighbor])
assert blocked['appearance_method']=='SCALE_POP', blocked
assert blocked['card_rest_position_norm']==old_center, blocked
assert blocked['planned_rect_norm']==old_rect, blocked
assert blocked['collision_envelope_rect_norm']==old_rect, blocked
assert _in_safe(blocked['planned_rect_norm']), blocked

print('V31_MIDDLE_POSITION_ENTRY_GEOMETRY_PASS')
