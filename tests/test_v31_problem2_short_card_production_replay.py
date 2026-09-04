from __future__ import annotations
import copy,json
from hexa_v31.interaction.director import apply_interaction_director
from hexa_v31.preset_authority import duration

FPS=30.0
SCENE_COUNT=49
CARD_COUNT=21
INTERACTION_COUNT=9
EVENT_COUNT=79

def entry(name,start):
    return {'name':name,'start_seconds':round(start,6),'duration_seconds':duration(name)}

def event(eid,scene_id,card_id,semantic_id,role,card_start,card_end,*,intent='',entry_name=None,entry_start=None,hit=None):
    x=.34 if role=='PRIMARY' else .66
    row={
        'event_id':eid,'scene_id':scene_id,'visual_card_id':card_id,'semantic_unit_id':semantic_id,
        'semantic_scope_id':scene_id+'::'+semantic_id,'semantic_type':'CONCEPT','semantic_role':role,
        'attention_priority':role,'semantic_intent':intent,'canonical_clause':intent,
        'semantic_mapping_confidence':.99,'translation_safe_after_occlusion':True,'animation_safe':True,
        'render_mode':'ROOT_ATOMIC','source_path':'synthetic.png','card_rest_position_norm':[x,.493],
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
events=[];sentences=[]
for i in range(INTERACTION_COUNT):
    card=cards[i];cs=float(card['start_seconds']);ce=float(card['end_seconds']);sid=f'SCENE_{i+1:03d}';cid=card['card_id']
    source_id=f'SOURCE_{i+1:02d}';target_id=f'TARGET_{i+1:02d}'
    source_entry_start=cs+.08;source_entry_name='ENTRY_LEFT_TO_MIDDLE';source_d=duration(source_entry_name)
    source_hit=source_entry_start+.90*source_d
    target_entry_start=source_entry_start+source_d+.10;target_entry_name='ENTRY_RIGHT_TO_MIDDLE';target_d=duration(target_entry_name)
    target_hit=target_entry_start+.90*target_d
    events.append(event(source_id,sid,cid,source_id,'PRIMARY',cs,ce,intent='TRANSFER',entry_name=source_entry_name,entry_start=source_entry_start,hit=source_hit))
    events.append(event(target_id,sid,cid,target_id,'SUPPORTING',cs,ce,entry_name=target_entry_name,entry_start=target_entry_start,hit=target_hit))
    scenes[i]['units']=[{'unit_id':source_id},{'unit_id':target_id}]
    sentences.append({'sentence_id':f'SENTENCE_{i+1:02d}','scene_id':sid,'visual_card_id':cid,
                      'subject_event_id':source_id,'action':'TRANSFER','object_event_id':target_id,
                      'result_event_id':None,'confidence':.95,'physical_support':True})

# Match the observed production topology: 79 events total, 21 cards, while only
# nine explicit semantic interactions are actionable.  Filler events deliberately
# live on later cards so they cannot make this replay pass by simplifying pair geometry.
filler_needed=EVENT_COUNT-len(events)
for j in range(filler_needed):
    card_index=INTERACTION_COUNT+(j%(CARD_COUNT-INTERACTION_COUNT));card=cards[card_index]
    scene_index=(INTERACTION_COUNT+j)%SCENE_COUNT;sid=f'SCENE_{scene_index+1:03d}';cid=card['card_id']
    eid=f'FILLER_{j+1:03d}';xrole='SUPPORTING'
    events.append(event(eid,sid,cid,eid,xrole,float(card['start_seconds']),float(card['end_seconds']),hit=float(card['start_seconds'])+.5))
    scenes[scene_index]['units'].append({'unit_id':eid})

base={
    'fps':FPS,'events':events,'visual_cards':{'cards':cards},
    'semantic_visual_sentence_compiler':{'sentences':sentences},
    'budget_summary':{'story_action_count':0,'choreography_action_count':150},'hard_invariants':{},
    'motion_dna_version':'HEXA_MOTION_DNA_PRODUCTION_SHAPED_REPLAY',
    'scenes':[{'scene_id':x['scene_id'],'start_seconds':0.0,'end_seconds':84.0} for x in scenes],
}
source_plan={'scenes':scenes}
out=apply_interaction_director(copy.deepcopy(base),source_plan,{},FPS)
engine=out['interaction_engine'];qa=out['interaction_plan_qa']
assert qa['pass'],qa
assert len(out['events'])==EVENT_COUNT,len(out['events'])
assert len(out['visual_cards']['cards'])==CARD_COUNT
assert engine['logical_interaction_count']==INTERACTION_COUNT,engine
assert engine['actionable_interaction_count']==INTERACTION_COUNT,engine
assert engine['embodied_interaction_count']==INTERACTION_COUNT,engine
assert engine['embodiment_ratio']==1.0,engine
assert engine['physical_action_count']==INTERACTION_COUNT*2,engine
assert engine['adopted_existing_motion_count']==INTERACTION_COUNT*2,engine
assert engine['fallback_report']['count']==0,engine['fallback_report']
for i in range(INTERACTION_COUNT):
    iid=f'INT::SENTENCE_{i+1:02d}'
    rows=sorted((x for x in engine['physical_actions'] if x['interaction_id']==iid),key=lambda x:float(x['start_seconds']))
    assert [x['phase'] for x in rows]==['ACTION','REACTION'],rows
    assert float(rows[1]['start_seconds'])>=float(rows[0]['end_seconds'])+1/FPS-1e-6,rows
print('V31_PROBLEM2_SHORT_CARD_PRODUCTION_REPLAY_PASS',json.dumps({
    'scenes':SCENE_COUNT,'cards':CARD_COUNT,'events':EVENT_COUNT,'interactions':INTERACTION_COUNT,
    'physical_actions':engine['physical_action_count'],'embodiment_ratio':engine['embodiment_ratio'],
    'adopted_existing_motion':engine['adopted_existing_motion_count']},sort_keys=True))
