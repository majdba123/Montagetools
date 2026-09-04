from __future__ import annotations
import copy,json
from hexa_v31.interaction.director import apply_interaction_director
from hexa_v31.preset_authority import duration

FPS=30.0
SCENE_COUNT=49
CARD_COUNT=21
INTERACTION_COUNT=9
EVENT_COUNT=79
UNSAFE_SCENES={'SCENE_002','SCENE_010','SCENE_014','SCENE_019','SCENE_022','SCENE_027','SCENE_030','SCENE_040'}
INTERACTION_SCENES=['SCENE_001','SCENE_002','SCENE_010','SCENE_014','SCENE_019','SCENE_022','SCENE_027','SCENE_030','SCENE_040']

def entry(name,start):
    return {'name':name,'start_seconds':round(start,6),'duration_seconds':duration(name)}

def event(eid,scene_id,card_id,semantic_id,role,card_start,card_end,*,intent='',entry_name=None,entry_start=None,hit=None,translation_safe=True,render_mode='ROOT_ATOMIC'):
    x=.34 if role=='PRIMARY' else .66
    row={
        'event_id':eid,'scene_id':scene_id,'visual_card_id':card_id,'semantic_unit_id':semantic_id,
        'semantic_scope_id':scene_id+'::'+semantic_id,'semantic_type':'CONCEPT','semantic_role':role,
        'attention_priority':role,'semantic_intent':intent,'canonical_clause':intent,
        'semantic_mapping_confidence':.99,'translation_safe_after_occlusion':bool(translation_safe),'animation_safe':bool(translation_safe),
        'scale_safe':True,'reveal_safe':True,'animation_mode':'TRANSLATE_SAFE' if translation_safe else 'IN_PLACE_ACTING_ONLY',
        'occlusion_class':'INDEPENDENT_ACTOR' if translation_safe else 'ATOMIC_PARENT_DEPENDENT',
        'render_mode':render_mode,'source_path':'synthetic.png','card_rest_position_norm':[x,.493],
        'planned_rect_norm':[x-.055,.433,.11,.12],'source_bbox_norm':[x-.055,.433,.11,.12],
        'layout_scale_multiplier':1.0,'reference_camera_scale':1.0,
        'start_seconds':round(card_start,6),'settle_seconds':round(card_start,6),'end_seconds':round(card_end,6),
        'physical_start_seconds':round(card_start,6),'physical_end_seconds':round(card_end,6),
        'motion_end_seconds':round(card_start,6),'preset_entry':None,'preset_exit':None,
        'preset_actions':[],'motion_intervals':[],'perceptual_hit_seconds':round(hit if hit is not None else card_start+.4,6),
    }
    if entry_name:
        en=entry(entry_name,float(entry_start));row['preset_entry']=en
        row['start_seconds']=round(float(entry_start),6);row['settle_seconds']=round(float(entry_start)+float(en['duration_seconds']),6)
        row['motion_end_seconds']=row['settle_seconds']
    return row

cards=[]
for i in range(CARD_COUNT):
    start=float(i)*4.0;cards.append({'card_id':f'CARD_{i+1:03d}','start_seconds':start,'end_seconds':start+4.0})

scenes=[{'scene_id':f'SCENE_{i+1:03d}','units':[]} for i in range(SCENE_COUNT)]
scene_index={x['scene_id']:i for i,x in enumerate(scenes)}
events=[];sentences=[]
for i,sid in enumerate(INTERACTION_SCENES):
    card=cards[i];cs=float(card['start_seconds']);ce=float(card['end_seconds']);cid=card['card_id'];unsafe=sid in UNSAFE_SCENES
    source_id=f'{sid}_PHYS_01';target_id=f'{sid}_PHYS_02'
    if unsafe:
        source_entry_name='APPEAR_HIGH_SCALE';source_entry_start=cs+.12;source_d=duration(source_entry_name);source_hit=source_entry_start+.70*source_d
        target_entry_name='APPEAR_HIGH_SCALE';target_entry_start=source_entry_start+source_d+.08;target_d=duration(target_entry_name);target_hit=target_entry_start+.70*target_d
        render_mode='CHILD_PARTITION'
    else:
        source_entry_name='ENTRY_LEFT_TO_MIDDLE';source_entry_start=cs+.08;source_d=duration(source_entry_name);source_hit=source_entry_start+.90*source_d
        target_entry_name='ENTRY_RIGHT_TO_MIDDLE';target_entry_start=source_entry_start+source_d+.10;target_d=duration(target_entry_name);target_hit=target_entry_start+.90*target_d
        render_mode='ROOT_ATOMIC'
    events.append(event(source_id,sid,cid,source_id,'PRIMARY',cs,ce,intent='REACT',entry_name=source_entry_name,entry_start=source_entry_start,hit=source_hit,translation_safe=not unsafe,render_mode=render_mode))
    events.append(event(target_id,sid,cid,target_id,'SUPPORTING',cs,ce,entry_name=target_entry_name,entry_start=target_entry_start,hit=target_hit,translation_safe=not unsafe,render_mode=render_mode))
    scenes[scene_index[sid]]['units']=[{'unit_id':source_id},{'unit_id':target_id}]
    sentences.append({'sentence_id':f'SENTENCE_{sid}','scene_id':sid,'visual_card_id':cid,'subject_event_id':source_id,'action':'REACT','object_event_id':target_id,'result_event_id':None,'confidence':.95,'physical_support':True})

filler_needed=EVENT_COUNT-len(events)
for j in range(filler_needed):
    card_index=INTERACTION_COUNT+(j%(CARD_COUNT-INTERACTION_COUNT));card=cards[card_index]
    si=(INTERACTION_COUNT+j)%SCENE_COUNT;sid=f'SCENE_{si+1:03d}';cid=card['card_id'];eid=f'FILLER_{j+1:03d}'
    events.append(event(eid,sid,cid,eid,'SUPPORTING',float(card['start_seconds']),float(card['end_seconds']),hit=float(card['start_seconds'])+.5))
    scenes[si]['units'].append({'unit_id':eid})

base={
    'fps':FPS,'events':events,'visual_cards':{'cards':cards},'semantic_visual_sentence_compiler':{'sentences':sentences},
    'budget_summary':{'story_action_count':0,'choreography_action_count':150},'hard_invariants':{},
    'motion_dna_version':'HEXA_MOTION_DNA_PRODUCTION_TRANSLATION_UNSAFE_REPLAY',
    'scenes':[{'scene_id':x['scene_id'],'start_seconds':0.0,'end_seconds':84.0} for x in scenes],
}
out=apply_interaction_director(copy.deepcopy(base),{'scenes':scenes},{},FPS)
engine=out['interaction_engine'];qa=out['interaction_plan_qa']
assert qa['pass'],qa
assert len(out['events'])==EVENT_COUNT and len(out['visual_cards']['cards'])==CARD_COUNT
assert engine['logical_interaction_count']==INTERACTION_COUNT,engine
assert engine['actionable_interaction_count']==INTERACTION_COUNT,engine
assert engine['embodied_interaction_count']==INTERACTION_COUNT,engine
assert engine['embodiment_ratio']==1.0,engine
assert engine['physical_action_count']==INTERACTION_COUNT*2,engine
assert engine['adopted_existing_motion_count']==INTERACTION_COUNT*2,engine
assert engine['fallback_report']['count']==0,engine['fallback_report']
unsafe_actions=0
for sid in INTERACTION_SCENES:
    iid='INT::SENTENCE_'+sid;rows=sorted((x for x in engine['physical_actions'] if x['interaction_id']==iid),key=lambda x:float(x['start_seconds']))
    assert [x['phase'] for x in rows]==['ACTION','REACTION'],rows
    assert float(rows[1]['start_seconds'])>=float(rows[0]['end_seconds'])+1/FPS-1e-6,rows
    if sid in UNSAFE_SCENES:
        unsafe_actions+=len(rows)
        assert all('TRANSLATE' not in set(x.get('required_operations') or []) for x in rows),rows
        assert all(x['preset']=='APPEAR_HIGH_SCALE' for x in rows),rows
assert unsafe_actions==16,unsafe_actions
print('V31_PROBLEM2_SHORT_CARD_PRODUCTION_REPLAY_PASS',json.dumps({
    'scenes':SCENE_COUNT,'cards':CARD_COUNT,'events':EVENT_COUNT,'interactions':INTERACTION_COUNT,
    'translation_unsafe_interactions':len(UNSAFE_SCENES),'capability_safe_in_place_actions':unsafe_actions,
    'physical_actions':engine['physical_action_count'],'embodiment_ratio':engine['embodiment_ratio'],
    'adopted_existing_motion':engine['adopted_existing_motion_count']},sort_keys=True))
