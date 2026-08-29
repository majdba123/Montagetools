from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
ROOT=Path(__file__).resolve().parents[1]
scene={'scene_id':'S1','units':[{'unit_id':'MAIN','semantic_name':'main','type':'CONCEPT','role':'PRIMARY'}],'visual_progression':[],'relation_to_previous':'START','script_span':{'global_char_start':0,'global_char_end':10,'text':'abcdefghij'}}
plan={'project_id':'V31_SHORT','scenes':[scene]};align={'method':'TEST','scene_timings':[{'scene_id':'S1','start':0,'end':3.8}],'word_timings':[]}
vision=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.20,'raw_component_count':1,'grouped_detail_count':1,'units':[{'physical_id':'PH_MAIN','semantic_unit_id':'MAIN','semantic_type':'CONCEPT','semantic_role':'PRIMARY','center_norm':[.5,.5],'bbox_norm':[.4,.4,.2,.2],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':'MAIN','semantic_mapping_confidence':.99}]}]
m=build_motion_plan(plan,align,vision,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
q=preset_motion_qa(m)
assert q['pass'],q['failures']
assert q['source_secondary_density_shortfall_cards']==1
assert any('No synthetic asset/cutout was fabricated' in w for w in q['warnings'])
print('V31_SECONDARY_SHORTFALL_REVIEW_PASS')
