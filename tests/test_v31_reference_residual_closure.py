from __future__ import annotations

import copy
from unittest.mock import patch

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.reference_residual_closure import finalize_reference_residual_closure


def event(eid,x,y,bbox,*,primary=False,start=0.0,end=4.0,hit=0.8,scene='SCENE_GENERIC',role=None):
    row={'event_id':eid,'scene_id':scene,'visual_card_id':'CARD_GENERIC','render_mode':'ROOT_ATOMIC',
        'source_bbox_norm':list(bbox),'visible_ink_fraction':0.88,
        'visible_ink_fraction_basis':'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX','reference_camera_scale':1.0,
        'layout_scale_multiplier':1.0,'card_rest_position_norm':[x,y],
        'attention_priority':'PRIMARY' if primary else 'SUPPORTING','semantic_role':'LEAD' if primary else 'SUPPORTING',
        'composition_role':role or ('LEAD' if primary else 'SUPPORT'),'start_seconds':start,'end_seconds':end,
        'physical_start_seconds':start,'physical_end_seconds':end,'motion_start_seconds':start,'motion_end_seconds':end,
        'settle_seconds':min(end,start+0.5),'perceptual_hit_seconds':hit,'preset_entry':None,'preset_exit':None,
        'preset_actions':[],'translation_safe_after_occlusion':False,'animation_safe':False,'position_animated':False}
    fp=_fp(row);row['planned_rect_norm']=list(_rect((x,y),fp,MOTION_ENVELOPE_SCALE));row['collision_envelope_rect_norm']=list(row['planned_rect_norm'])
    return row


def card(events,*,end=4.0,split_phases=False):
    phases=[{'phase_id':'PHASE_GENERIC','start_seconds':0.0,'end_seconds':end,'event_ids':[row['event_id'] for row in events]}]
    if split_phases:
        phases=[{'phase_id':'P1','start_seconds':0.0,'end_seconds':2.0,'event_ids':[events[0]['event_id']]},
                {'phase_id':'P2','start_seconds':2.0,'end_seconds':end,'event_ids':[events[1]['event_id']]}]
    return {'card_id':'CARD_GENERIC','start_seconds':0.0,'end_seconds':end,'duration_seconds':end,
        'story_phase_plan':{'phases':phases},'constraint_layout':{'placements':{row['event_id']:{'center_norm':list(row['card_rest_position_norm']),'scale':row['layout_scale_multiplier'],'rect_norm':list(row['planned_rect_norm'])} for row in events}}}


def plan(events,*,end=4.0,split_phases=False):
    return {'fps':30.0,'events':events,'visual_cards':{'cards':[card(events,end=end,split_phases=split_phases)]}}


single=event('SPARSE_SINGLE',.50,.52,(0,0,.13,.18),primary=True)
single_plan=plan([single]);before_scale=single['layout_scale_multiplier'];single_stats=finalize_reference_residual_closure(single_plan)
assert single_stats['pass'],single_stats
assert single_stats['density_candidates_committed']>=1,single_stats
assert single['layout_scale_multiplier']>before_scale*1.10,single
assert single['reference_residual_density_authority'].startswith('REFERENCE_RESIDUAL_CARD_AND_FOCUS_CLOSURE')
assert single_stats['after_underfilled_seconds']<=single_stats['before_underfilled_seconds'],single_stats
assert single_stats['after_mean_projected_ink']>single_stats['before_mean_projected_ink'],single_stats

owner=event('FOCUS_OWNER',.30,.52,(0,0,.38,.62),primary=True,hit=.55)
target=event('FOCUS_TARGET',.72,.52,(0,0,.22,.26),hit=2.0)
target['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':1.35,'duration_seconds':.8}
focus_plan=plan([owner,target]);focus_stats=finalize_reference_residual_closure(focus_plan)
assert focus_stats['pass'],focus_stats
assert focus_stats['focus_candidates_committed']==1,focus_stats
assert owner.get('meaningful_recomposition'),owner
assert len(owner.get('composition_states') or [])==1,owner
state=owner['composition_states'][0]
assert state['semantic_beat']=='SOURCE_REVEAL_FOCUS_TRANSFER',state
assert set(state['participating_event_ids'])=={'FOCUS_OWNER','FOCUS_TARGET'}
assert float(state['start_seconds'])>=1.35+.8+.04-1e-6,state
assert float(focus_stats['after_static_hold_ratio'])<=float(focus_stats['before_static_hold_ratio'])-.04,focus_stats
participants=target.get('composition_participant_states') or []
assert len(participants)==2,participants
assert participants[0]['scale_multiplier']<participants[1]['scale_multiplier']
assert participants[1]['previous_state_id']==participants[0]['state_id']
assert participants[0]['center_norm']==participants[1]['center_norm']==[.72,.52]
assert not owner.get('position_animated') and not target.get('position_animated')

# True center travel remains protected. The physical lifetime begins with the
# authored ENTRY so the baseline is itself valid under viewport QA.
travel_owner=event('TRAVEL_OWNER',.20,.52,(0,0,.14,.22),primary=True,hit=.55)
travel_target=event('TRAVEL_TARGET',.50,.52,(0,0,.10,.14),start=1.2,hit=2.0)
travel_target['preset_entry']={'name':'ENTRY_RIGHT_TO_MIDDLE','start_seconds':1.2,'duration_seconds':.8}
travel_plan=plan([travel_owner,travel_target])
assert composition_plan_qa(travel_plan)['pass'],composition_plan_qa(travel_plan)
travel_before=copy.deepcopy(travel_plan);travel_stats=finalize_reference_residual_closure(travel_plan)
assert travel_stats['pass'],travel_stats
assert travel_stats['focus_candidates_committed']==0,travel_stats
assert not travel_owner.get('composition_states')
assert not travel_target.get('composition_participant_states')
assert travel_plan==travel_before,(travel_before,travel_plan)

unrelated_owner=event('UNRELATED_OWNER',.30,.52,(0,0,.38,.62),primary=True,hit=.55,scene='SCENE_A')
unrelated_target=event('UNRELATED_TARGET',.72,.52,(0,0,.22,.26),hit=2.0,scene='SCENE_B')
unrelated_target['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':1.35,'duration_seconds':.8}
unrelated_plan=plan([unrelated_owner,unrelated_target],split_phases=True)
unrelated_stats=finalize_reference_residual_closure(unrelated_plan)
assert unrelated_stats['focus_candidates_committed']==0,unrelated_stats

rejected=event('ATOMIC_ROLLBACK',.50,.52,(0,0,.13,.18),primary=True);rejected_plan=plan([rejected]);original=copy.deepcopy(rejected_plan)
with patch('hexa_v31.layout.reference_residual_closure._candidate_safe',return_value=False):
    rejected_stats=finalize_reference_residual_closure(rejected_plan)
assert rejected_stats['density_candidates_committed']==0,rejected_stats
assert rejected_plan==original,(original,rejected_plan)

partition_child=event('PARTITION_CHILD',.44,.52,(0,0,.09,.14),primary=True);partition_child['render_mode']='CHILD_PARTITION';partition_child['partition_group_id']='PARTITION_GENERIC'
partition_residual=event('PARTITION_RESIDUAL',.62,.52,(0,0,.09,.14));partition_residual['render_mode']='RESIDUAL_SUPPORT';partition_residual['partition_group_id']='PARTITION_GENERIC'
partition_plan=plan([partition_child,partition_residual]);partition_before=copy.deepcopy(partition_plan);partition_stats=finalize_reference_residual_closure(partition_plan)
assert partition_stats['density_candidates_committed']==0,partition_stats
assert partition_stats['focus_candidates_committed']==0,partition_stats
assert partition_plan==partition_before,(partition_before,partition_plan)

repeat_owner=event('OTHER_OWNER',.30,.52,(0,0,.38,.62),primary=True,hit=.55)
repeat_target=event('OTHER_TARGET',.72,.52,(0,0,.22,.26),hit=2.0);repeat_target['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':1.35,'duration_seconds':.8}
repeat_plan=plan([repeat_owner,repeat_target]);repeat_stats=finalize_reference_residual_closure(repeat_plan)
assert repeat_stats['focus_candidates_committed']==1,repeat_stats
assert repeat_owner['composition_states'][0]['scale_multiplier']==owner['composition_states'][0]['scale_multiplier']
assert repeat_target['composition_participant_states'][-1]['scale_multiplier']==participants[-1]['scale_multiplier']
print('V31_REFERENCE_RESIDUAL_P3_P4_CLOSURE_PASS')
