from __future__ import annotations
import copy,json
from hexa_v31.interaction.director import apply_interaction_director
from hexa_v31.preset_authority import duration

FPS=30.0
SCENE_COUNT=49
CARD_COUNT=21
ACTIONABLE_COUNT=9
EVENT_COUNT=79
UNSAFE_REACT_SCENES=['SCENE_002','SCENE_010','SCENE_014','SCENE_019','SCENE_022','SCENE_027','SCENE_030','SCENE_040']
FOCUS_SCENE='SCENE_001'

def entry(name,start):return {'name':name,'start_seconds':round(start,6),'duration_seconds':duration(name)}

def event(eid,scene_id,card_id,semantic_id,role,card_start,card_end,*,intent='',entry_name=None,entry_start=None,hit=None,translation_safe=True,render_mode='ROOT_ATOMIC'):
    x=.34 if role=='PRIMARY' else .66
    row={'event_id':eid,'scene_id':scene_id,'visual_card_id':card_id,'semantic_unit_id':semantic_id,'semantic_scope_id':scene_id+'::'+semantic_id,'semantic_type':'CONCEPT','semantic_role':role,'attention_priority':role,'semantic_intent':intent,'canonical_clause':intent,'semantic_mapping_confidence':.99,'translation_safe_after_occlusion':bool(translation_safe),'animation_safe':bool(translation_safe),'scale_safe':True,'reveal_safe':True,'animation_mode':'TRANSLATE_SAFE' if translation_safe else 'IN_PLACE_ACTING_ONLY','occlusion_class':'INDEPENDENT_ACTOR' if translation_safe else 'ATOMIC_PARENT_DEPENDENT','render_mode':render_mode,'source_path':'synthetic.png','card_rest_position_norm':[x,.493],'planned_rect_norm':[x-.055,.433,.11,.12],'source_bbox_norm':[x-.055,.433,.11,.12],'layout_scale_multiplier':1.0,'reference_camera_scale':1.0,'start_seconds':round(card_start,6),'settle_seconds':round(card_start,6),'end_seconds':round(card_end,6),'physical_start_seconds':round(card_start,6),'physical_end_seconds':round(card_end,6),'motion_end_seconds':round(card_start,6),'preset_entry':None,'preset_exit':None,'preset_actions':[],'motion_intervals':[],'perceptual_hit_seconds':round(hit if hit is not None else card_start+.4,6)}
    if entry_name:
        en=entry(entry_name,float(entry_start));row['preset_entry']=en;row['start_seconds']=round(float(entry_start),6);row['settle_seconds']=round(float(entry_start)+float(en['duration_seconds']),6);row['motion_end_seconds']=row['settle_seconds']
    return row

cards=[{'card_id':f'CARD_{i+1:03d}','start_seconds':float(i)*4.0,'end_seconds':float(i)*4.0+4.0} for i in range(CARD_COUNT)]
scenes=[{'scene_id':f'SCENE_{i+1:03d}','units':[]} for i in range(SCENE_COUNT)];scene_index={x['scene_id']:i for i,x in enumerate(scenes)};events=[];sentences=[]

focus_card=cards[0];fcs=float(focus_card['start_seconds']);fce=float(focus_card['end_seconds']);focus_id=f'{FOCUS_SCENE}_PHYS_01';focus_start=fcs+.12;focus_d=duration('APPEAR_HIGH_SCALE');focus_hit=focus_start+.70*focus_d
focus=event(focus_id,FOCUS_SCENE,focus_card['card_id'],focus_id,'PRIMARY',fcs,fce,intent='REVEAL',entry_name='APPEAR_HIGH_SCALE',entry_start=focus_start,hit=focus_hit,translation_safe=True,render_mode='ROOT_ATOMIC');events.append(focus);scenes[scene_index[FOCUS_SCENE]]['units']=[{'unit_id':focus_id}];sentences.append({'sentence_id':f'SENTENCE_{FOCUS_SCENE}','scene_id':FOCUS_SCENE,'visual_card_id':focus_card['card_id'],'subject_event_id':focus_id,'action':'REVEAL','object_event_id':None,'result_event_id':None,'confidence':.95,'physical_support':True})

for i,sid in enumerate(UNSAFE_REACT_SCENES,start=1):
    card=cards[i];cs=float(card['start_seconds']);ce=float(card['end_seconds']);cid=card['card_id'];subject_id=f'{sid}_PHYS_01';object_id=f'{sid}_PHYS_02';cause_name='APPEAR_HIGH_SCALE';cause_start=cs+.12;cause_d=duration(cause_name);cause_hit=cause_start+.70*cause_d;reaction_name='APPEAR_HIGH_SCALE';reaction_start=cause_start+cause_d+.08;reaction_d=duration(reaction_name);reaction_hit=reaction_start+.70*reaction_d
    subject=event(subject_id,sid,cid,subject_id,'PRIMARY',cs,ce,intent='REACT',entry_name=reaction_name,entry_start=reaction_start,hit=reaction_hit,translation_safe=False,render_mode='CHILD_PARTITION')
    obj=event(object_id,sid,cid,object_id,'SUPPORTING',cs,ce,entry_name=cause_name,entry_start=cause_start,hit=cause_hit,translation_safe=False,render_mode='CHILD_PARTITION')
    events.extend([subject,obj]);scenes[scene_index[sid]]['units']=[{'unit_id':subject_id},{'unit_id':object_id}];sentences.append({'sentence_id':f'SENTENCE_{sid}','scene_id':sid,'visual_card_id':cid,'subject_event_id':subject_id,'action':'REACT','object_event_id':object_id,'result_event_id':None,'confidence':.95,'physical_support':True})

filler_needed=EVENT_COUNT-len(events)
for j in range(filler_needed):
    card_index=ACTIONABLE_COUNT+(j%(CARD_COUNT-ACTIONABLE_COUNT));card=cards[card_index];si=(ACTIONABLE_COUNT+j)%SCENE_COUNT;sid=f'SCENE_{si+1:03d}';cid=card['card_id'];eid=f'FILLER_{j+1:03d}';events.append(event(eid,sid,cid,eid,'SUPPORTING',float(card['start_seconds']),float(card['end_seconds']),hit=float(card['start_seconds'])+.5));scenes[si]['units'].append({'unit_id':eid})

base={'fps':FPS,'events':events,'visual_cards':{'cards':cards},'semantic_visual_sentence_compiler':{'sentences':sentences},'budget_summary':{'story_action_count':0,'choreography_action_count':150},'hard_invariants':{},'motion_dna_version':'HEXA_MOTION_DNA_PRODUCTION_8_REACT_1_FOCUS_REPLAY','scenes':[{'scene_id':x['scene_id'],'start_seconds':0.0,'end_seconds':84.0} for x in scenes]}
out=apply_interaction_director(copy.deepcopy(base),{'scenes':scenes},{},FPS);engine=out['interaction_engine'];qa=out['interaction_plan_qa']
assert qa['pass'],qa
assert len(out['events'])==EVENT_COUNT and len(out['visual_cards']['cards'])==CARD_COUNT
assert engine['logical_interaction_count']==ACTIONABLE_COUNT and engine['actionable_interaction_count']==ACTIONABLE_COUNT,engine
assert engine['embodied_interaction_count']==ACTIONABLE_COUNT and engine['embodiment_ratio']==1.0,engine
assert engine['physical_action_count']==17 and engine['adopted_existing_motion_count']==17,engine
assert engine['fallback_report']['count']==0,engine['fallback_report']
assert engine['react_reverse_direction_count']==8,engine
focus_rows=[x for x in engine['physical_actions'] if x['interaction_id']==f'INT::SENTENCE_{FOCUS_SCENE}'];assert len(focus_rows)==1 and focus_rows[0]['event_id']==focus_id and focus_rows[0]['phase']=='ACTION',focus_rows
unsafe_actions=0
for sid in UNSAFE_REACT_SCENES:
    iid='INT::SENTENCE_'+sid;rows=sorted((x for x in engine['physical_actions'] if x['interaction_id']==iid),key=lambda x:float(x['start_seconds']));subject_id=f'{sid}_PHYS_01';object_id=f'{sid}_PHYS_02'
    assert [x['phase'] for x in rows]==['ACTION','REACTION'],rows
    assert [x['event_id'] for x in rows]==[object_id,subject_id],rows
    assert all(x.get('source_event_id')==object_id and x.get('target_event_id')==subject_id for x in rows),rows
    assert all(x.get('causal_direction')=='OBJECT_CAUSES_SUBJECT_REACTION' for x in rows),rows
    assert float(rows[1]['start_seconds'])>=float(rows[0]['end_seconds'])+1/FPS-1e-6,rows
    intent=next(x for x in engine['intents'] if x['interaction_id']==iid);assert intent['causal_source_event_id']==object_id and intent['causal_target_event_id']==subject_id,intent
    edge=next(x for x in engine['graph']['edges'] if x.get('interaction_id')==iid and x.get('kind')=='ACTION_TO_REACTION');assert edge['from']==object_id and edge['to']==subject_id and edge.get('causal_direction')=='OBJECT_CAUSES_SUBJECT_REACTION',edge
    unsafe_actions+=len(rows);assert all('TRANSLATE' not in set(x.get('required_operations') or []) for x in rows),rows;assert all(x['preset']=='APPEAR_HIGH_SCALE' for x in rows),rows
assert unsafe_actions==16,unsafe_actions
print('V31_PROBLEM2_SHORT_CARD_PRODUCTION_REPLAY_PASS',json.dumps({'scenes':SCENE_COUNT,'cards':CARD_COUNT,'events':EVENT_COUNT,'actionable_interactions':ACTIONABLE_COUNT,'translation_unsafe_react_interactions':8,'focus_interactions':1,'capability_safe_in_place_actions':unsafe_actions,'react_reverse_direction':engine['react_reverse_direction_count'],'physical_actions':engine['physical_action_count'],'embodiment_ratio':engine['embodiment_ratio'],'adopted_existing_motion':engine['adopted_existing_motion_count']},sort_keys=True))
