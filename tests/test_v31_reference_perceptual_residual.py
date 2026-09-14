from __future__ import annotations

import copy

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.position_authority import has_actual_center_travel
from hexa_v31.layout.reference_perceptual_residual import finalize_reference_perceptual_residual


def event(eid,x,y,bbox,*,primary=False,start=0.0,end=4.0,scene='SCENE_GENERIC'):
    row={'event_id':eid,'scene_id':scene,'visual_card_id':'CARD_GENERIC','render_mode':'ROOT_ATOMIC',
        'source_bbox_norm':list(bbox),'visible_ink_fraction':0.88,
        'visible_ink_fraction_basis':'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX','reference_camera_scale':1.0,
        'layout_scale_multiplier':1.0,'card_rest_position_norm':[x,y],
        'attention_priority':'PRIMARY' if primary else 'SUPPORTING','semantic_role':'LEAD' if primary else 'SUPPORTING',
        'composition_role':'LEAD' if primary else 'SUPPORT','start_seconds':start,'end_seconds':end,
        'physical_start_seconds':start,'physical_end_seconds':end,'motion_start_seconds':start,'motion_end_seconds':end,
        'settle_seconds':min(end,start+0.4),'perceptual_hit_seconds':start+0.7,
        'preset_entry':None,'preset_exit':None,'preset_actions':[],
        'translation_safe_after_occlusion':False,'animation_safe':False,'position_animated':False}
    fp=_fp(row);row['planned_rect_norm']=list(_rect((x,y),fp,MOTION_ENVELOPE_SCALE));row['collision_envelope_rect_norm']=list(row['planned_rect_norm'])
    return row


def card(events,*,end=4.0):
    return {'card_id':'CARD_GENERIC','start_seconds':0.0,'end_seconds':end,'duration_seconds':end,
        'story_phase_plan':{'phases':[{'phase_id':'PHASE_GENERIC','start_seconds':0.0,'end_seconds':end,'event_ids':[row['event_id'] for row in events]}]},
        'constraint_layout':{'placements':{row['event_id']:{'center_norm':list(row['card_rest_position_norm']),'scale':row['layout_scale_multiplier'],'rect_norm':list(row['planned_rect_norm'])} for row in events}}}


def plan(events,*,end=4.0):
    return {'fps':30.0,'events':events,'visual_cards':{'cards':[card(events,end=end)]}}


single=event('SINGLE_ROOT',.50,.52,(0,0,.13,.18),primary=True);single_plan=plan([single]);single_stats=finalize_reference_perceptual_residual(single_plan)
assert single_stats['pass'],single_stats
assert single_stats['single_root_commits']==1,single_stats
assert single_stats['closure_satisfied'],single_stats
assert single_stats['after_residual_card_ids']==[],single_stats
assert single_stats['after_mean_projected_ink']>=.24,single_stats
assert single_stats['after_underfilled_seconds']==0.0,single_stats
assert single['layout_scale_multiplier']>=3.3,single
assert single['reference_perceptual_residual_authority'].startswith('REFERENCE_PERCEPTUAL_RESIDUAL')
assert composition_plan_qa(single_plan)['pass'],composition_plan_qa(single_plan)

primary=event('GROUP_PRIMARY',.30,.52,(0,0,.22,.26),primary=True);support=event('GROUP_SUPPORT',.70,.52,(0,0,.22,.26));group_plan=plan([primary,support]);group_stats=finalize_reference_perceptual_residual(group_plan)
assert group_stats['pass'],group_stats
assert group_stats['group_commits']==1,group_stats
assert group_stats['closure_satisfied'],group_stats
assert group_stats['after_mean_projected_ink']>=.24,group_stats
assert group_stats['after_underfilled_seconds']<group_stats['before_underfilled_seconds'],group_stats
assert primary['layout_scale_multiplier']>1.0 and support['layout_scale_multiplier']>1.0
assert primary['layout_scale_multiplier']==support['layout_scale_multiplier']
assert primary['card_rest_position_norm'][0]<support['card_rest_position_norm'][0]
assert composition_plan_qa(group_plan)['pass'],composition_plan_qa(group_plan)

# Explicitly cover the 22-24% blind band that the older residual interval
# fallback did not consider. The new stage owns the whole-card fallback here.
moderate=event('MODERATE_SINGLE',.50,.52,(0,0,.50,.523),primary=True);moderate_plan=plan([moderate]);moderate_stats=finalize_reference_perceptual_residual(moderate_plan)
assert moderate_stats['pass'],moderate_stats
assert moderate_stats['single_root_commits']==1,moderate_stats
assert moderate_stats['closure_satisfied'],moderate_stats
assert moderate_stats['after_mean_projected_ink']>=.24,moderate_stats

# True center travel protection is actor-scoped. The travelling actor must stay
# byte-for-byte unchanged, but a different static actor in the same sparse card
# may still receive a certified density-only improvement. The synthetic baseline
# is valid itself: physical lifetime begins exactly when the ENTRY begins.
travel_owner=event('TRAVEL_OWNER',.20,.52,(0,0,.14,.22),primary=True)
travel_target=event('TRAVEL_TARGET',.50,.52,(0,0,.10,.14),start=1.2)
travel_target['preset_entry']={'name':'ENTRY_RIGHT_TO_MIDDLE','start_seconds':1.2,'duration_seconds':.8}
travel_plan=plan([travel_owner,travel_target]);assert composition_plan_qa(travel_plan)['pass'],composition_plan_qa(travel_plan)
assert has_actual_center_travel(travel_target),travel_target
travel_owner_before=copy.deepcopy(travel_owner)
travel_target_before=copy.deepcopy(travel_target)
travel_stats=finalize_reference_perceptual_residual(travel_plan)
assert travel_stats['pass'],travel_stats
assert travel_target==travel_target_before,(travel_target_before,travel_target)
assert has_actual_center_travel(travel_target),travel_target
assert travel_target['preset_entry']==travel_target_before['preset_entry']
assert (
    travel_target['physical_start_seconds'],travel_target['physical_end_seconds'],
    travel_target['motion_start_seconds'],travel_target['motion_end_seconds']
)==(
    travel_target_before['physical_start_seconds'],travel_target_before['physical_end_seconds'],
    travel_target_before['motion_start_seconds'],travel_target_before['motion_end_seconds']
)
assert float(travel_owner['layout_scale_multiplier'])>=float(travel_owner_before['layout_scale_multiplier'])
interval_mutations=[row for row in travel_stats['mutations'] if row.get('strategy')=='SOURCE_INTERVAL_FRAMING_WITH_SUPPORT_HANDOFF']
if interval_mutations:
    # Temporary sparse framing must return to the exact settled support
    # composition. Its destination belongs only to the DENSITY_FRAME envelope;
    # moving the static base would recreate the later-actor collision.
    assert travel_owner['card_rest_position_norm']==travel_owner_before['card_rest_position_norm']
    assert travel_owner['planned_rect_norm']==travel_owner_before['planned_rect_norm']
    states=[s for s in travel_owner.get('composition_participant_states') or [] if s.get('envelope_track')=='DENSITY_FRAME']
    assert len(states)==2 and states[-1]['center_norm']==travel_owner_before['card_rest_position_norm'],states
assert composition_plan_qa(travel_plan)['pass'],composition_plan_qa(travel_plan)

child=event('PARTITION_CHILD',.42,.52,(0,0,.10,.15),primary=True);child['render_mode']='CHILD_PARTITION';child['partition_group_id']='PG'
residual=event('PARTITION_RESIDUAL',.62,.52,(0,0,.10,.15));residual['render_mode']='RESIDUAL_SUPPORT';residual['partition_group_id']='PG'
partition_plan=plan([child,residual]);partition_before=copy.deepcopy(partition_plan);partition_stats=finalize_reference_perceptual_residual(partition_plan)
assert partition_stats['pass'],partition_stats
assert partition_stats['commits']==0,partition_stats
assert partition_plan==partition_before,(partition_before,partition_plan)

other=event('COMPLETELY_DIFFERENT_ID',.50,.52,(0,0,.13,.18),primary=True);other_plan=plan([other]);other_stats=finalize_reference_perceptual_residual(other_plan)
assert other_stats['single_root_commits']==1,other_stats
assert other['layout_scale_multiplier']==single['layout_scale_multiplier']
assert other['card_rest_position_norm']==single['card_rest_position_norm']
assert other_stats['after_mean_projected_ink']==single_stats['after_mean_projected_ink']
print('V31_REFERENCE_PERCEPTUAL_RESIDUAL_CARD_CLOSURE_PASS')
