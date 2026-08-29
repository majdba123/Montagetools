from pathlib import Path
from hexa_v31.motion import build_motion_plan
ROOT=Path(__file__).resolve().parents[1]
scene={'scene_id':'S1','units':[{'unit_id':'MAIN','type':'CONCEPT','role':'PRIMARY'},{'unit_id':'TARGET','type':'ICON','role':'SUPPORTING'},{'unit_id':'B','type':'ICON','role':'SUPPORTING'},{'unit_id':'C','type':'ICON','role':'SUPPORTING'}],'visual_progression':[{'targets':['MAIN','TARGET']}],'script_span':{'global_char_start':0,'global_char_end':4,'text':'test'}}
align={'method':'TEST','scene_timings':[{'scene_id':'S1','start':0.0,'end':4.0}],'word_timings':[]}
def u(uid,role,cx,conf):return {'physical_id':'P_'+uid,'semantic_unit_id':uid,'semantic_type':'CONCEPT' if role=='PRIMARY' else 'ICON','semantic_role':role,'center_norm':[cx,.5],'bbox_norm':[cx-.05,.45,.1,.1],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':conf}
lo=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.22,'raw_component_count':4,'grouped_detail_count':4,'units':[u('MAIN','PRIMARY',.5,.6),u('TARGET','SUPPORTING',.85,.6),u('B','SUPPORTING',.2,.99),u('C','SUPPORTING',.5,.99)]}]
hi=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.22,'raw_component_count':4,'grouped_detail_count':4,'units':[u('MAIN','PRIMARY',.5,.99),u('TARGET','SUPPORTING',.85,.99),u('B','SUPPORTING',.2,.99),u('C','SUPPORTING',.5,.99)]}]
args=(ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
m0=build_motion_plan({'project_id':'X','scenes':[scene]},align,lo,*args)
r0=m0['visual_cards']['cards'][0]['relationship_resolutions'][0]
assert r0['mode']=='UNRESOLVED_PHYSICAL_MAPPING',r0
assert sum(1 for e in m0['events'] for a in (e.get('preset_actions') or []) if a.get('action_type')=='SEMANTIC_RELATIONSHIP')==0
m1=build_motion_plan({'project_id':'X','scenes':[scene]},align,hi,*args)
r1=m1['visual_cards']['cards'][0]['relationship_resolutions'][0]
assert r1['mode']!='UNRESOLVED_PHYSICAL_MAPPING',r1
# High confidence authorizes consideration, not forced motion: layout/preset geometry may still
# require a temporal handoff. This is the safety behavior that prevents wrong relationships.
acts=[a for e in m1['events'] for a in (e.get('preset_actions') or []) if a.get('action_type')=='SEMANTIC_RELATIONSHIP']
if acts: assert acts[0]['relationship_confidence']==1.0 and acts[0]['target_semantic_unit_id']=='TARGET'
else: assert r1['mode']=='TEMPORAL_HANDOFF' and r1['reason']
print('V31_SEMANTIC_MAPPING_GUARD_PASS',r1['mode'])
