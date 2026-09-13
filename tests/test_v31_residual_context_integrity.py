from __future__ import annotations
import pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.layout.source_integrity_finalizer import finalize_residual_source_integrity,AUTHORITY

residual={
    'event_id':'R','visual_card_id':'C','scene_id':'S','render_mode':'RESIDUAL_SUPPORT',
    'card_rest_position_norm':[.70,.52],'source_center_norm':[.70,.52],
    'layout_scale_multiplier':1.65,'planned_rect_norm':[.20,.22,.66,.50],
    'collision_envelope_rect_norm':[.20,.22,.66,.50],
    'physical_start_seconds':0.0,'physical_end_seconds':3.0,
    'composition_participant_states':[
        {'state_id':'R1','start_seconds':1.0,'transition_duration_seconds':.3,
         'center_norm':[.62,.45],'scale_multiplier':1.25,'visibility':1.0,'position_envelope':True}
    ],
}
plan={'fps':30.0,'events':[residual],'visual_cards':{'cards':[{
    'card_id':'C','start_seconds':0.0,'end_seconds':3.0,
    'constraint_layout':{'placements':{'R':{'center_norm':[.70,.52],'scale':1.65,'rect_norm':[.20,.22,.66,.50]}}}
}]}}
report=finalize_residual_source_integrity(plan)
e=plan['events'][0]
assert report['changed'] and e['layout_scale_multiplier']==1.0,report
assert e['card_rest_position_norm']==[.70,.52]
assert e['composition_participant_states'][0]['scale_multiplier']==1.0
assert e['composition_participant_states'][0]['center_norm']==[.70,.52]
assert not e['composition_participant_states'][0]['position_envelope']
assert e['residual_context_authority']==AUTHORITY
placement=plan['visual_cards']['cards'][0]['constraint_layout']['placements']['R']
assert placement['scale']==1.0 and placement['center_norm']==[.70,.52]
# Source pixels and carrier timing are never removed/shortened by context normalization.
assert e['physical_start_seconds']==0.0 and e['physical_end_seconds']==3.0
print('V31_RESIDUAL_CONTEXT_INTEGRITY_PASS',report)
