from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
ROOT=Path(__file__).resolve().parents[1]
units=[];vunits=[]
for i in range(6):
    uid=f'P{i+1}'
    units.append({'unit_id':uid,'semantic_name':f'primary_{i+1}','type':'CONCEPT','role':'PRIMARY'})
    vunits.append({'physical_id':'PH_'+uid,'semantic_unit_id':uid,'semantic_type':'CONCEPT','semantic_role':'PRIMARY','center_norm':[.30+.08*(i%2),.45+.08*(i//2)],'bbox_norm':[.2,.3,.15,.2],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':.99})
scene={'scene_id':'S1','units':units,'visual_progression':[],'relation_to_previous':'START','script_span':{'global_char_start':0,'global_char_end':20,'text':'x'*20}}
plan={'project_id':'V31_WAVE','scenes':[scene]}
align={'method':'TEST','scene_timings':[{'scene_id':'S1','start':0.0,'end':4.85}],'word_timings':[]}
vision=[{'scene_id':'S1','mode':'CLEAN_LAYERED','foreground_fraction':.25,'raw_component_count':9,'grouped_detail_count':8,'units':vunits}]
m=build_motion_plan(plan,align,vision,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
q=preset_motion_qa(m)
assert q['pass'],q['failures']
c=m['visual_cards']['cards'][0]
assert 1<=c['rendered_primary_count']<=2,c
active=[e for e in m['events'] if not e.get('suppressed_by_card_density')]
suppressed=[e for e in m['events'] if e.get('suppressed_by_card_density')]
# Primaries beyond the two-object concurrency cap progress through bounded waves;
# source objects are suppressed only when the solver proves them unsafe.
assert 4<=len(active)<=6,(len(active),c)
phases=(c.get('story_phase_plan') or {}).get('phases') or []
assert phases,c
assert all(len(ph['event_ids'])<=2 for ph in phases)
assert all(float(ph['end_seconds'])>float(ph['start_seconds']) for ph in phases),phases
assert all(e.get('suppression_reason') for e in suppressed)
# The old <=3 phase assertion predated semantic focus-transfer tails. A three-wave
# schedule may now legitimately compile relationship+focus phases while preserving the
# hard two-primary concurrency budget. Guard against runaway fragmentation instead of
# forbidding the authored temporal topology.
phase_count=(c.get('story_phase_plan') or {}).get('phase_count')
assert phase_count==len(phases),(phase_count,len(phases))
assert phase_count<=2*len(active),(phase_count,len(active),phases)
print('V31_PRIMARY_DENSITY_BUDGET_PASS',c['rendered_primary_count'],len(active),len(suppressed),phase_count)
