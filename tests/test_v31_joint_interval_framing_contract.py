from __future__ import annotations
import copy,pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.layout.reference_joint_interval_framing import _semantic_cohort,_append_scale_envelope,AUTHORITY

card={'card_id':'CARD_GENERIC','story_phase_plan':{'phases':[]}}
a={'event_id':'A','visual_card_id':'CARD_GENERIC','scene_id':'SCENE_GENERIC','render_mode':'ROOT_ATOMIC','attention_priority':'PRIMARY','visible_ink_fraction':.12,'card_rest_position_norm':[.32,.52]}
b={'event_id':'B','visual_card_id':'CARD_GENERIC','scene_id':'SCENE_GENERIC','render_mode':'ROOT_ATOMIC','attention_priority':'SUPPORT','visible_ink_fraction':.08,'card_rest_position_norm':[.68,.52]}
cohort=_semantic_cohort(card,[b,a])
assert [x['event_id'] for x in cohort]==['A','B'],cohort

before=copy.deepcopy(a)
_append_scale_envelope(a,card,1.2,3.8,.30,1.16,['A','B'])
states=a.get('composition_participant_states') or []
assert len(states)==2,states
assert all(s['authority']==AUTHORITY and s['envelope_track']=='DENSITY_FRAME' for s in states)
assert states[0]['scale_multiplier']==1.16 and states[1]['scale_multiplier']==1.0
assert states[0]['center_norm']==before['card_rest_position_norm']==a['card_rest_position_norm']
assert states[1]['semantic_beat']=='RESTORE_BEFORE_SEMANTIC_HANDOFF'
# Permanent geometry authority is untouched; the pass is temporal-only.
assert 'layout_scale_multiplier' not in a and 'planned_rect_norm' not in a

print('V31_JOINT_INTERVAL_FRAMING_CONTRACT_PASS')
