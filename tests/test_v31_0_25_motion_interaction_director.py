from hexa_v31.preset_authority import authority, duration
from hexa_v31.preset_story_planner import (
    _apply_composition_history_variant, _interaction_grammar, _schedule_event, legal_effect_catalog,
    perceptual_sync_qa, rank_legal_effects,
)

catalog=legal_effect_catalog()
approved=set((authority().get('preset_motion') or {}).keys())
assert catalog['WITHIN_FRAME'] and all(x in approved for rows in catalog.values() for x in rows)

carrier={'event_id':'A','semantic_type':'OBJECT','narrative_function':'CAUSE','attention_priority':'PRIMARY','card_rest_position_norm':[.5,.5]}
target={'event_id':'B','semantic_type':'RESULT','narrative_function':'EFFECT RESULT','attention_priority':'SUPPORTING','card_rest_position_norm':[.75,.5]}
choices=tuple(x for x in catalog['WITHIN_FRAME'] if x.startswith('WITHIN_MIDDLE_TO_'))
a=rank_legal_effects(choices,[],carrier,target,'CAUSE_EFFECT')
b=rank_legal_effects(choices,[],carrier,target,'CAUSE_EFFECT')
assert a==b and a and all(x in approved for x in a)
history=[{'within_family':'WITHIN_MIDDLE_TO_LEFT','travel_direction':'LEFT','archetype':'CAUSE_EFFECT','handoff_grammar':'CAUSE_EFFECT_REVEAL'}]*2
c=rank_legal_effects(choices,history,carrier,target,'CAUSE_EFFECT')
assert c[0]!='WITHIN_MIDDLE_TO_LEFT',c
assert _interaction_grammar(carrier,target)=='CAUSE_EFFECT_REVEAL'
assert sum(x.get('attention_priority')=='PRIMARY' for x in (carrier,target))<=2

layout={'pass':True,'placements':{'A':{'center_norm':[.25,.5],'rect_norm':[.15,.3,.2,.4]},'B':{'center_norm':[.70,.5],'rect_norm':[.62,.35,.16,.3]}}}
variant=_apply_composition_history_variant(layout,{'archetype':'COMPARISON'},[{'archetype':'COMPARISON','variant':'CANONICAL'}])
assert variant=='MIRRORED' and layout['placements']['A']['center_norm'][0]==.75
assert layout['placements']['A']['rect_norm']==[.65,.3,.2,.4]

entry='ENTRY_LEFT_TO_MIDDLE';anchor=2.0;dur=duration(entry)
event={'event_id':'SYNC','perceptual_hit_seconds':anchor,'start_seconds':anchor-.90*dur,'preset_entry':{'name':entry,'start_seconds':anchor-.90*dur,'duration_seconds':dur}}
qa=perceptual_sync_qa([event],30.0)
assert qa['pass'] and qa['bounded_pre_roll_pass'] and qa['no_premature_semantic_reveal_pass'],qa
assert abs(qa['events'][0]['anchor_to_visual_impact'])<1e-6

short={'event_id':'SHORT','attention_priority':'PRIMARY','card_rest_position_norm':[.5,.5],'source_center_norm':[.5,.5],'perceptual_hit_seconds':.55,'end_seconds':1.15,'composite_atomic':False}
_schedule_event(short,(0.0,1.15),{'end_seconds':1.15},0,2)
assert short['fast_narration_fallback'] and short['appearance_method']=='SCALE_POP'
assert short['preset_entry']['name'] in approved and not short['position_animated']
assert short['semantic_readable_not_before_seconds']==short['visual_impact_seconds']

print('V31_0_25_MOTION_INTERACTION_DIRECTOR_PASS')
