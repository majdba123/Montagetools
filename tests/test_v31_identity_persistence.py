from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
ROOT=Path(__file__).resolve().parents[1]
scenes=[];timings=[];vision=[];t=0.0
for i in range(4):
    sid=f'S{i+1}';st=t;en=t+1.0;t=en
    main=f'M{i+1}';sup=f'U{i+1}'
    scenes.append({'scene_id':sid,'units':[{'unit_id':main,'semantic_name':'HEXA_MAIN','type':'MAIN_CHARACTER','role':'PRIMARY'},{'unit_id':sup,'semantic_name':f'support_{i+1}','type':'ICON','role':'SUPPORTING'}],'visual_progression':[],'relation_to_previous':'CONTINUE' if i else 'START','script_span':{'global_char_start':i*10,'global_char_end':i*10+8,'text':'abcdefgh'}})
    timings.append({'scene_id':sid,'start':st,'end':en})
    def vu(uid,typ,role,cx):return {'physical_id':'PH_'+uid,'semantic_unit_id':uid,'semantic_type':typ,'semantic_role':role,'center_norm':[cx,.5],'bbox_norm':[cx-.06,.43,.12,.14],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':.99}
    vision.append({'scene_id':sid,'mode':'CLEAN_LAYERED','foreground_fraction':.22,'raw_component_count':4,'grouped_detail_count':4,'units':[vu(main,'MAIN_CHARACTER','PRIMARY',.35),vu(sup,'ICON','SUPPORTING',.72)]})
plan={'project_id':'V31_PERSIST','scenes':scenes};align={'method':'TEST','scene_timings':timings,'word_timings':[]}
m=build_motion_plan(plan,align,vision,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
q=preset_motion_qa(m);assert q['pass'],q['failures']
prim=[e for e in m['events'] if e['attention_priority']=='PRIMARY']
active=[e for e in prim if not e.get('suppressed_by_card_density')]
assert len(active)==1,(len(active),[(e['event_id'],e.get('suppression_reason')) for e in prim])
assert sum(1 for e in prim if e.get('suppression_reason')=='CARD_IDENTITY_PERSISTENCE')==3
assert m['visual_cards']['cards'][0]['rendered_primary_count']==1
print('V31_IDENTITY_PERSISTENCE_PASS')
