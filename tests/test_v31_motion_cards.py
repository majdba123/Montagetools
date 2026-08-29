from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
ROOT=Path(__file__).resolve().parents[1]
def u(uid,role,cx,typ='CONCEPT'):
    return {'physical_id':'P_'+uid,'semantic_unit_id':uid,'semantic_type':typ,'semantic_role':role,'center_norm':[cx,0.5],'bbox_norm':[cx-.05,.42,.1,.16],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':.99}
scene={'scene_id':'S1','units':[{'unit_id':'MAIN','semantic_name':'main','type':'CONCEPT','role':'PRIMARY'},{'unit_id':'A','semantic_name':'a','type':'ICON','role':'SUPPORTING'},{'unit_id':'B','semantic_name':'b','type':'ICON','role':'SUPPORTING'},{'unit_id':'C','semantic_name':'c','type':'ICON','role':'SUPPORTING'}],'visual_progression':[],'relation_to_previous':'START','script_span':{'global_char_start':0,'global_char_end':10,'text':'abcdefghij'}}
plan={'project_id':'V31TEST','scenes':[scene]}
align={'method':'TEST','scene_count':1,'scene_timings':[{'scene_id':'S1','start':0.0,'end':3.8}],'word_timings':[]}
vis=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.23,'raw_component_count':4,'grouped_detail_count':4,'units':[u('MAIN','PRIMARY',.50),u('A','SUPPORTING',.18,'ICON'),u('B','SUPPORTING',.78,'ICON'),u('C','SUPPORTING',.50,'ICON')]}]
m=build_motion_plan(plan,align,vis,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
q=preset_motion_qa(m)
assert q['pass'],q
assert len(m['visual_cards']['cards'])==1
c=m['visual_cards']['cards'][0]
assert 3<=c['duration_seconds']<=5 and c['rendered_primary_count']==1 and c['rendered_secondary_count']>=3
assert c['constraint_layout']['pass'] and c['story_phase_plan']['phase_count']>=1
for e in [x for x in m['events'] if not x.get('suppressed_by_card_density')]:
    assert e['hierarchy_level']==0 and not e['motion_blur_enabled']
    assert e['preset_entry']['name'] in {'ENTRY_LEFT_TO_MIDDLE','ENTRY_RIGHT_TO_MIDDLE','APPEAR_HIGH_SCALE'}
    if e['attention_priority']!='PRIMARY': assert e['preset_entry']['name']=='APPEAR_HIGH_SCALE'
print('V31_MOTION_CARDS_PASS')
