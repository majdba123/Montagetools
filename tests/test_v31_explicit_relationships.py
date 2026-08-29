from pathlib import Path
from copy import deepcopy
from hexa_v31.motion import build_motion_plan
ROOT=Path(__file__).resolve().parents[1]
def vu(uid,role,cx,cy=.5):return {'physical_id':'P_'+uid,'semantic_unit_id':uid,'semantic_type':'CONCEPT' if role=='PRIMARY' else 'ICON','semantic_role':role,'center_norm':[cx,cy],'bbox_norm':[cx-.05,cy-.05,.1,.1],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':0.99}
units=[{'unit_id':'MAIN','semantic_name':'source','type':'CONCEPT','role':'PRIMARY'},{'unit_id':'A','semantic_name':'target','type':'ICON','role':'SUPPORTING'},{'unit_id':'B','semantic_name':'b','type':'ICON','role':'SUPPORTING'},{'unit_id':'C','semantic_name':'c','type':'ICON','role':'SUPPORTING'}]
base={'scene_id':'S1','units':units,'relation_to_previous':'START','script_span':{'global_char_start':0,'global_char_end':10,'text':'abcdefghij'}}
align={'method':'TEST','scene_count':1,'scene_timings':[{'scene_id':'S1','start':0.0,'end':4.4}],'word_timings':[]}
vis=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.22,'raw_component_count':4,'grouped_detail_count':4,'units':[vu('MAIN','PRIMARY',.5),vu('A','SUPPORTING',.83),vu('B','SUPPORTING',.18),vu('C','SUPPORTING',.5,.78)]}]
args=(ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
s0=deepcopy(base);s0['visual_progression']=[]
m0=build_motion_plan({'project_id':'X','scenes':[s0]},align,vis,*args)
assert sum(1 for e in m0['events'] for a in (e.get('preset_actions') or []) if a.get('action_type')=='SEMANTIC_RELATIONSHIP')==0
assert m0['visual_cards']['cards'][0]['relationship_resolutions']==[]
# Declaring a relationship must change semantic grammar, but it must NOT force an unsafe
# movement merely to satisfy the test. Geometry/preset endpoints remain a physical hard gate.
s1=deepcopy(base);s1['visual_progression']=[{'targets':['MAIN','A']}]
m1=build_motion_plan({'project_id':'X','scenes':[s1]},align,vis,*args)
c=m1['visual_cards']['cards'][0]
assert c['universal_scene_grammar']['explicit_edges'],c
res=c['relationship_resolutions']
assert len(res)==1 and res[0]['source']=='MAIN' and res[0]['target']=='A',res
acts=[a for e in m1['events'] for a in (e.get('preset_actions') or []) if a.get('action_type')=='SEMANTIC_RELATIONSHIP']
if acts:
    assert len(acts)==1 and acts[0]['relationship_confidence']==1.0 and acts[0]['relationship_evidence']
else:
    assert res[0]['mode']=='TEMPORAL_HANDOFF' and res[0]['reason'],res
print('V31_EXPLICIT_RELATIONSHIP_PASS',res[0]['mode'])
