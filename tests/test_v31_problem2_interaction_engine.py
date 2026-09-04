from __future__ import annotations
import copy,json
from hexa_v31.interaction.director import apply_interaction_director

def event(eid,x,role='PRIMARY',semantic_intent=''):
    return {'event_id':eid,'scene_id':'ARBITRARY_SCENE','visual_card_id':'ARBITRARY_CARD','semantic_unit_id':eid,'semantic_scope_id':'ARBITRARY_SCENE::'+eid,'semantic_type':'CONCEPT','semantic_role':role,'attention_priority':role,'semantic_intent':semantic_intent,'canonical_clause':semantic_intent,'semantic_mapping_confidence':.99,'translation_safe_after_occlusion':True,'animation_safe':True,'card_rest_position_norm':[x,.493],'planned_rect_norm':[x-.055,.433,.11,.12],'source_bbox_norm':[x-.055,.433,.11,.12],'layout_scale_multiplier':1.0,'reference_camera_scale':1.0,'start_seconds':0.0,'settle_seconds':.35,'end_seconds':4.4,'physical_start_seconds':0.0,'physical_end_seconds':4.4,'motion_end_seconds':.35,'preset_entry':None,'preset_exit':None,'preset_actions':[],'motion_intervals':[],'perceptual_hit_seconds':1.0,'render_mode':'ROOT_ATOMIC','source_path':'synthetic.png'}
base={'fps':30.0,'events':[event('SOURCE',.487,'PRIMARY','TRANSFER'),event('TARGET',.833,'SUPPORTING')],'visual_cards':{'cards':[{'card_id':'ARBITRARY_CARD','start_seconds':0.0,'end_seconds':4.4}]},'semantic_visual_sentence_compiler':{'sentences':[{'sentence_id':'SENTENCE_ARBITRARY','scene_id':'ARBITRARY_SCENE','visual_card_id':'ARBITRARY_CARD','subject_event_id':'SOURCE','action':'TRANSFER','object_event_id':'TARGET','result_event_id':None,'confidence':.94,'physical_support':True}]},'budget_summary':{},'hard_invariants':{},'motion_dna_version':'BASE','scenes':[{'scene_id':'ARBITRARY_SCENE','start_seconds':0.0,'end_seconds':4.4}]}
# No package visual_progression/interaction_target is required when the semantic sentence
# already supplies an explicit high-confidence physical subject/object pair.
source_plan={'scenes':[{'scene_id':'ARBITRARY_SCENE','units':[{'unit_id':'SOURCE'},{'unit_id':'TARGET'}]}]}
a=apply_interaction_director(copy.deepcopy(base),source_plan,{},30.0);b=apply_interaction_director(copy.deepcopy(base),source_plan,{},30.0)
assert a['interaction_plan_qa']['pass'],a['interaction_plan_qa'];engine=a['interaction_engine']
assert engine['logical_interaction_count']==1 and engine['actionable_interaction_count']==1,engine
assert engine['physical_action_count']==2 and engine['embodiment_ratio']==1.0,engine
assert engine['intent_compiler']['physical_pair_candidate_count']==1,engine['intent_compiler']
assert engine['intent_compiler']['intents'][0]['pair_authority']=='SEMANTIC_SENTENCE_EXPLICIT_PAIR',engine['intent_compiler']
phases=[x['phase'] for x in engine['physical_actions']];assert phases==['ACTION','REACTION'],phases
action,reaction=engine['physical_actions'];assert reaction['start_seconds']>=action['end_seconds']+1/30-1e-6,(action,reaction)
assert all((x.get('swept_geometry') or {}).get('pass') for x in engine['physical_actions'])
assert all(a.get('action_type')=='SEMANTIC_RELATIONSHIP' and a.get('relationship_confidence')==1.0 and a.get('target_semantic_unit_id')=='TARGET' for e in a['events'] for a in e.get('preset_actions') or [])
canonical=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False);assert canonical(a['interaction_engine'])==canonical(b['interaction_engine'])
# Low-confidence semantic evidence remains non-actionable and may safely stay static.
low=copy.deepcopy(base);low['semantic_visual_sentence_compiler']['sentences'][0]['confidence']=.55
low_plan=apply_interaction_director(low,source_plan,{},30.0);assert low_plan['interaction_engine']['actionable_interaction_count']==0 and low_plan['interaction_engine']['physical_action_count']==0
print('V31_PROBLEM2_INTERACTION_ENGINE_PASS')
