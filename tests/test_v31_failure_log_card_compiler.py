from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
ROOT=Path(__file__).resolve().parents[1]
# Stress shape mirrors the user's failed build: many sub-3-second audio scenes.
pattern=[0.40,0.92,1.02,3.35,1.46,2.74,1.40,1.99,2.35,2.46,1.76,0.80,1.36,1.14,2.72,1.42,1.12,0.70,2.82,2.76,0.92,1.22,1.64,3.20,1.66,1.22,3.10,1.24,1.90,2.90,2.26,3.25,2.70,2.54,1.60,2.02,3.30,2.40]
durs=(pattern*2)[:49]
# Normalize to roughly 99.3s without creating any >5s micro-scene.
factor=99.32/sum(durs);durs=[d*factor for d in durs]
scenes=[];timings=[];vision=[];t=0.0
for i,d in enumerate(durs,1):
    sid=f'S{i:03d}';st=t;en=t+d;t=en
    main=f'M{i:03d}';sup=f'U{i:03d}'
    scenes.append({'scene_id':sid,'units':[{'unit_id':main,'semantic_name':main,'type':'CONCEPT','role':'PRIMARY'},{'unit_id':sup,'semantic_name':sup,'type':'ICON','role':'SUPPORTING'}],'visual_progression':[],'relation_to_previous':'CONTINUE' if i>1 else 'START','script_span':{'global_char_start':i*10,'global_char_end':i*10+8,'text':'abcdefgh'}})
    timings.append({'scene_id':sid,'start':st,'end':en})
    def vu(uid,role,cx):return {'physical_id':'P_'+uid,'semantic_unit_id':uid,'semantic_type':'CONCEPT' if role=='PRIMARY' else 'ICON','semantic_role':role,'center_norm':[cx,.5],'bbox_norm':[cx-.06,.43,.12,.14],'hierarchy_level':0,'translation_safe_after_occlusion':True,'animation_safe':True,'composition_slot_id':uid,'semantic_mapping_confidence':.99}
    vision.append({'scene_id':sid,'mode':'CLEAN_LAYERED','foreground_fraction':.24,'raw_component_count':4,'units':[vu(main,'PRIMARY',.43 if i%2 else .57),vu(sup,'SUPPORTING',.78 if i%2 else .22)]})
plan={'project_id':'FAILURE_LOG_SHAPE','scenes':scenes};align={'method':'TEST','scene_timings':timings,'word_timings':[]}
m=build_motion_plan(plan,align,vision,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
q=preset_motion_qa(m)
assert q['pass'],q['failures'][:10]
cards=m['visual_cards']['cards']
assert 18<=len(cards)<=33,len(cards)
assert all(3.0-1e-5<=c['duration_seconds']<=5.0+1e-5 for c in cards)
assert all(1<=c['rendered_primary_count']<=2 for c in cards)
assert all(3<=c['rendered_secondary_count']<=8 for c in cards)
assert any(c.get('distinct_primary_authority_count',0)>2 for c in cards), 'stress case did not exercise sequential >2 primary handoff'
# No layout action is allowed to claim a semantic target/evidence.
for e in m['events']:
    for a in e.get('preset_actions') or []:
        if a.get('action_type')=='LAYOUT_CHOREOGRAPHY':
            assert not a.get('target_semantic_unit_id') and not a.get('relationship_evidence')
# Supports must receive deterministic card positions rather than colliding at source coordinates.
assert all(e.get('card_rest_position_norm') for e in m['events'] if e['attention_priority']!='PRIMARY' and not e.get('suppressed_by_card_density'))
print('V31_FAILURE_LOG_CARD_COMPILER_PASS',len(cards))
