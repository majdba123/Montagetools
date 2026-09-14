from pathlib import Path
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
from hexa_v31.interaction.scene_ownership_contract import _coverage_with_boundary_carriers
from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa
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

# Regression: coverage is certified on encoded frame timestamps, not a card-local
# floating clock. A real missing encoded frame must still fail closed.
def _coverage_event(eid,start,end,own_start=None,own_end=None,carrier=None):
    row={'event_id':eid,'scene_id':eid,'visual_card_id':'CARD_FRAME_GRID','render_mode':'ROOT_ATOMIC',
         'start_seconds':start,'end_seconds':end,'physical_start_seconds':start,'physical_end_seconds':end,
         'motion_start_seconds':start,'motion_end_seconds':end}
    if own_start is not None: row['scene_ownership_start_seconds']=own_start
    if own_end is not None: row['scene_ownership_end_seconds']=own_end
    if carrier is not None:
        row.update(scene_boundary_carrier_start_seconds=carrier[0],scene_boundary_carrier_end_seconds=carrier[1],
                   scene_boundary_carrier_sample_seconds=carrier[2],scene_boundary_carrier_authority='OUTGOING_LAST_MATERIAL_PIXEL_HOLD')
    return row
frame_grid_plan={'fps':30.0,'events':[
    _coverage_event('OUT',6.9,8.0,6.9,8.7,(8.0,8.7,239/30.0)),
    _coverage_event('IN',8.7,12.0,8.7,12.0),
], 'visual_cards':{'cards':[{'card_id':'CARD_FRAME_GRID','start_seconds':8.033333,'end_seconds':12.0,'duration_seconds':3.966667}]}}
legacy=visual_timeline_coverage_qa(frame_grid_plan,fps=30.0)
assert not legacy['pass'] and 'VISUAL_TIMELINE_COVERAGE_GAP' in legacy['failures'],legacy
encoded=_coverage_with_boundary_carriers(frame_grid_plan,30.0,visual_timeline_coverage_qa)
assert encoded['pass'],encoded
assert encoded.get('coverage_sampling_authority')=='GLOBAL_ENCODED_FRAME_GRID',encoded
broken={**frame_grid_plan,'events':[dict(e) for e in frame_grid_plan['events']]}
broken['events'][0]['scene_boundary_carrier_end_seconds']=260/30.0
rejected=_coverage_with_boundary_carriers(broken,30.0,visual_timeline_coverage_qa)
assert not rejected['pass'] and 'VISUAL_TIMELINE_COVERAGE_GAP' in rejected['failures'],rejected
assert any(g.get('start_frame')==260 and g.get('end_frame')==261 for g in rejected['visual_gaps']),rejected
print('V31_FAILURE_LOG_CARD_COMPILER_PASS',len(cards))
