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

# Multi-actor, same-source cards must now be authored as progressive temporal
# states before geometry is solved. The old one-poster phase made all three
# support icons readable almost simultaneously.
phase_plan=c['story_phase_plan']
assert phase_plan.get('progressive_reveal_compiled'),phase_plan
assert phase_plan.get('choreography_authority')=='SEMANTIC_ARCHETYPE_TEMPORAL_TOPOLOGY_V2',phase_plan
assert phase_plan['phase_count']>=3,phase_plan
phase_sets=[p['event_ids'] for p in phase_plan['phases']]
assert len(phase_sets[0])==1,phase_sets
assert len(set(phase_plan.get('reveal_order_event_ids') or []))==4,phase_plan
last_phase=phase_plan['phases'][-1]
assert float(last_phase['end_seconds'])-float(last_phase['start_seconds'])>=1.27,last_phase

active=[x for x in m['events'] if not x.get('suppressed_by_card_density')]
for e in active:
    assert e['hierarchy_level']==0 and not e['motion_blur_enabled']
    assert e['preset_entry']['name'] in {'ENTRY_LEFT_TO_MIDDLE','ENTRY_RIGHT_TO_MIDDLE','APPEAR_HIGH_SCALE'}
    if e['attention_priority']!='PRIMARY':
        assert e['preset_entry']['name']=='APPEAR_HIGH_SCALE'

# Reveal clocks must be materially staggered across the spoken card instead of
# the previous 60ms index offsets. Directional arrival is authored as an
# ordinary composition state so it can settle and yield to later focus/rebuild
# states while the preset-family contract for support actors remains intact.
starts=sorted({round(float(e['physical_start_seconds']),2) for e in active})
assert len(starts)>=3,starts
phase_geometry=[s for e in active for s in e.get('composition_states') or []
                if s.get('state_reason')=='SEMANTIC_ARCHETYPE_PHASE_GEOMETRY']
assert phase_geometry,active
assert any(abs(float(s.get('scale_multiplier',1.0))-1.0)>=.10 for s in phase_geometry),phase_geometry
assert sum(float(e['physical_start_seconds'])<=.01 for e in active)==1,active
directional=[e for e in active if e.get('editorial_entry_direction')]
assert directional,directional
assert all(e['editorial_entry_direction'] in {'LEFT','RIGHT','TOP','BOTTOM'} for e in directional)
assert all(
    any(
        s.get('envelope_track')=='EDITORIAL_ENTRY' and s.get('position_envelope')
        for key in ('composition_states','composition_participant_states')
        for s in e.get(key) or []
    )
    for e in directional
),directional
beat=m.get('beat_choreography_compiler') or {}
assert beat.get('staggered_sentence_count',0)>=1,beat
assert beat.get('directional_entry_count',0)>=1,beat

print('V31_MOTION_CARDS_PASS')
