from pathlib import Path
import tempfile

from hexa_v31.motion import build_motion_plan
from hexa_v31.editorial_motion import EditorialMotionGrammarDirector, PacingDirector
from hexa_v31.continuity_character import SemanticCharacterDirector, VisualContinuityQA
from hexa_v31.preset_story_planner import _final_physical_certification

ROOT=Path(__file__).resolve().parents[1]
RULES=ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json'
REFERENCE=ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json'

def unit(pid,level,role,bbox,**extra):
    row={'physical_id':pid,'semantic_unit_id':'ROOT_SEM','semantic_type':'CONCEPT','semantic_role':role,
         'center_norm':[bbox[0]+bbox[2]/2,bbox[1]+bbox[3]/2],'bbox_norm':bbox,'hierarchy_level':level,
         'composition_slot_id':'ROOT_SEM','animation_safe':True,'reveal_safe':True,
         'translation_safe_after_occlusion':True,'semantic_mapping_confidence':.99}
    row.update(extra);return row

def plan_for(units,artifacts,intent='REVEAL',words=None):
    scene={'scene_id':'S','units':[{'unit_id':'ROOT_SEM','semantic_name':'generic object','type':'CONCEPT','role':'PRIMARY','semantic_intent':intent}],
           'visual_progression':[],'relation_to_previous':'START','script_span':{'global_char_start':0,'global_char_end':8,'text':'generic'}}
    vision=[{'scene_id':'S','mode':'CLEAN_LAYERED','foreground_fraction':.20,'raw_component_count':3,'units':units,'artifacts':artifacts}]
    alignment={'method':'TEST','scene_timings':[{'scene_id':'S','start':0.,'end':4.}], 'word_timings':words or []}
    return build_motion_plan({'project_id':'GENERIC','scenes':[scene]},alignment,vision,RULES,REFERENCE)

with tempfile.TemporaryDirectory() as raw:
    tmp=Path(raw);a=tmp/'child_a.png';b=tmp/'child_b.png';root=tmp/'root.png'
    for path in (a,b,root):path.write_bytes(b'PNG')
    root_u=unit('ROOT',0,'PRIMARY',[.30,.30,.40,.35],root_id='R',layer_path=str(root),mask_path=str(root))
    a_u=unit('CHILD_A',1,'PRIMARY',[.30,.30,.17,.35],root_id='R',parent_id='R',child_id='R::A',layer_path=str(a),mask_path=str(a))
    b_u=unit('CHILD_B',1,'PRIMARY',[.53,.30,.17,.35],root_id='R',parent_id='R',child_id='R::B',layer_path=str(b),mask_path=str(b))
    accepted={'hierarchy_decisions':[{'root_id':'R','accepted':True,'child_count':2,'decomposition_mode':'EXACT_SOURCE_PARTITION'}]}
    motion=plan_for([root_u,a_u,b_u],accepted)
    child_events=[e for e in motion['events'] if e.get('render_mode')=='CHILD_PARTITION']
    assert motion['budget_summary']['hierarchical_motion_unit_count']==2
    assert {e['physical_id'] for e in child_events}=={'CHILD_A','CHILD_B'}
    assert not any(e['physical_id']=='ROOT' for e in motion['events'])
    assert all(Path(e['source_layer_path']).is_file() for e in child_events)
    assert any(e.get('independent_motion_allowed') for e in child_events)
    assert len({e['composition_slot_id'] for e in child_events})==1
    unsafe=unit('CHILD_UNSAFE',1,'PRIMARY',[.30,.30,.17,.35],root_id='R',parent_id='R',child_id='R::U',layer_path=str(a),mask_path=str(a),reveal_safe=False)
    fallback=plan_for([root_u,unsafe,b_u],accepted)
    assert [e['physical_id'] for e in fallback['events']]==['ROOT']

# Planning authority must produce different legal constraints for different
# intent/rate inputs without changing semantic anchors.
def event(intent,hit=.9):
    return {'event_id':intent,'semantic_intent':intent,'perceptual_hit_seconds':hit,'end_seconds':3.,
            'attention_priority':'PRIMARY','card_rest_position_norm':[.7,.5],
            'preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.55}}

compare=[event('COMPARE')];reveal=[event('REVEAL')]
EditorialMotionGrammarDirector().direct(compare);EditorialMotionGrammarDirector().direct(reveal)
assert compare[0]['editorial_within_frame_preference']!=reveal[0]['editorial_within_frame_preference']
fast=[event('REVEAL',.4),event('REVEAL',.8),event('REVEAL',1.2)]
slow=[event('REVEAL',.4),event('REVEAL',.8),event('REVEAL',1.2)]
PacingDirector().plan(fast,{'word_timings':[{'start':0,'end':.1} for _ in range(12)]})
PacingDirector().plan(slow,{'word_timings':[{'start':0,'end':4}]})
assert sum(e['pacing_discretionary_action_allowed'] for e in fast)<sum(e['pacing_discretionary_action_allowed'] for e in slow)
characters=[{'event_id':'CAUSE','visual_card_id':'C','semantic_type':'CONCEPT','attention_priority':'PRIMARY','card_rest_position_norm':[.3,.5]},
            {'event_id':'REACT','visual_card_id':'C','semantic_type':'SECONDARY_CHARACTER','semantic_intent':'REACTION','attention_priority':'PRIMARY','card_rest_position_norm':[.7,.5]}]
SemanticCharacterDirector().direct(characters)
assert characters[1]['character_within_frame_preference']=='WITHIN_MIDDLE_TO_UP'

# Final QA observes the committed post-repair state, not a pre-optimizer copy.
handoff=[{'event_id':'A','visual_card_id':'C','start_seconds':0.,'end_seconds':1.,'physical_end_seconds':1.,'source_bbox_norm':[.2,.3,.2,.2],'planned_rect_norm':[.2,.3,.2,.2],'matting':{'opaque_foreground_fraction':1.0}},
         {'event_id':'B','visual_card_id':'C','start_seconds':1.4,'end_seconds':3.,'source_bbox_norm':[.6,.3,.2,.2],'planned_rect_norm':[.6,.3,.2,.2],'matting':{'opaque_foreground_fraction':1.0}}]
cards={'cards':[{'card_id':'C','start_seconds':0.,'end_seconds':3.,'duration_seconds':3.,'constraint_layout':{'placements':{}}}]}
director=VisualContinuityQA();repair=director.repair_once(handoff,cards)
assert repair['repaired_event_ids']==['A'] and handoff[0]['end_seconds']==1.4
assert director.assess({'events':handoff,'visual_cards':cards})['version']==director.version

def cert_event(eid,center,action=None):
    e={'event_id':eid,'visual_card_id':'C','start_seconds':0.,'end_seconds':3.,'perceptual_hit_seconds':.8,
       'attention_priority':'PRIMARY','source_bbox_norm':[0,0,.12,.14],'card_rest_position_norm':list(center),
       'planned_rect_norm':[center[0]-.06,center[1]-.07,.12,.14],'collision_envelope_rect_norm':[center[0]-.06,center[1]-.07,.12,.14],
       'layout_scale_multiplier':1.,'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':.1,'duration_seconds':.55},
       'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':2.3,'duration_seconds':.6},'preset_actions':[],'matting':{'opaque_foreground_fraction':1.0}}
    if action:e['preset_actions']=[action]
    return e
def cert_cards(events):
    return {'cards':[{'card_id':'C','start_seconds':0.,'end_seconds':3.,'duration_seconds':3.,
                      'universal_scene_grammar':{'archetype':'GENERIC'},
                      'story_phase_plan':{'phases':[{'phase_id':'P','start_seconds':0.,'end_seconds':3.,'event_ids':[e['event_id'] for e in events]}]}}]}

# A late settled overlap is repaired by the authoritative layout solver.
overlap_events=[cert_event('A',[.5,.5]),cert_event('B',[.5,.5])]
overlap_result=_final_physical_certification(overlap_events,cert_cards(overlap_events),30.)
assert overlap_result['pass'] and overlap_result['repair_passes']==1
assert overlap_events[0]['card_rest_position_norm']!=overlap_events[1]['card_rest_position_norm']

# A late path collision drops optional choreography before considering any
# certified static/scale fallback, while preserving both voice anchors.
path_action={'name':'WITHIN_MIDDLE_TO_RIGHT','start_seconds':.8,'duration_seconds':.7,'action_type':'LAYOUT_CHOREOGRAPHY','layout_purpose':'TEST_HANDOFF'}
path_events=[cert_event('A',[.5,.5],path_action),cert_event('B',[.72,.5])]
anchors=[e['perceptual_hit_seconds'] for e in path_events]
path_result=_final_physical_certification(path_events,cert_cards(path_events),30.)
assert path_result['pass'] and path_events[0]['preset_actions']==[]
assert anchors==[e['perceptual_hit_seconds'] for e in path_events]

print('V31_SPRINT1_PRODUCTION_INTEGRATION_PASS')
