from __future__ import annotations
import pathlib,tempfile
from PIL import Image,ImageDraw
from hexa_v31.motion import build_motion_plan

ROOT=pathlib.Path(__file__).resolve().parents[1]
RULES=ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json'
REFERENCE=ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json'

with tempfile.TemporaryDirectory(prefix='hexa_full_planner_react_') as raw:
    td=pathlib.Path(raw)
    def png(name,x0):
        p=td/(name+'.png');im=Image.new('RGBA',(640,360),(255,255,255,0));d=ImageDraw.Draw(im);d.rounded_rectangle((x0,110,x0+130,250),20,fill=(80,120,210,255));im.save(p);return p
    reactor_path=png('reactor',110);cause_path=png('cause',390)
    scene={
        'scene_id':'S_REACT','relation_to_previous':'START','visual_progression':[],
        'script_span':{'global_char_start':0,'global_char_end':24,'text':'react response to cause'},
        'units':[
            {'unit_id':'REACTOR_SEM','semantic_name':'reactor','type':'CONCEPT','role':'PRIMARY','semantic_intent':'REACT','visual_concept':'response'},
            {'unit_id':'CAUSE_SEM','semantic_name':'cause','type':'CONCEPT','role':'SUPPORTING','semantic_intent':'PRESENT','visual_concept':'cause'},
        ],
    }
    def physical(pid,sem,role,center,bbox,path,root_id):
        return {
            'physical_id':pid,'semantic_unit_id':sem,'semantic_type':'CONCEPT','semantic_role':role,
            'center_norm':list(center),'bbox_norm':list(bbox),'hierarchy_level':0,'root_id':root_id,
            'composition_slot_id':sem,'animation_safe':False,'translation_safe_after_occlusion':False,
            'independent_motion_allowed':False,'reveal_safe':True,'scale_safe':True,
            'semantic_mapping_confidence':.99,'layer_path':str(path),'mask_path':str(path),
            'animation_mode':'IN_PLACE_ACTING_ONLY','occlusion_class':'ATOMIC_PARENT_DEPENDENT',
        }
    vision=[{
        'scene_id':'S_REACT','mode':'CLEAN_LAYERED','foreground_fraction':.24,
        'expected_semantic_units':2,'grouped_detail_count':0,
        'units':[
            physical('REACTOR_PHYS','REACTOR_SEM','PRIMARY',[.34,.5],[.25,.38,.18,.24],reactor_path,'R_REACTOR'),
            physical('CAUSE_PHYS','CAUSE_SEM','SUPPORTING',[.66,.5],[.57,.38,.18,.24],cause_path,'R_CAUSE'),
        ],
        'artifacts':{'hierarchy_decisions':[]},
    }]
    alignment={'method':'FULL_PLANNER_REACT_TEST','scene_timings':[{'scene_id':'S_REACT','start':0.0,'end':4.0}],'word_timings':[]}
    plan={'project_id':'GENERIC_REACT_PLANNER','scenes':[scene]}
    motion=build_motion_plan(plan,alignment,vision,RULES,REFERENCE,fps=30.0)
    engine=motion.get('interaction_engine') or {};qa=motion.get('interaction_plan_qa') or {}
    assert qa.get('pass'),qa
    assert engine.get('actionable_interaction_count')==1,engine
    assert engine.get('embodied_interaction_count')==1 and engine.get('embodiment_ratio')==1.0,engine
    assert engine.get('react_reverse_direction_count')==1,engine
    intent=next(x for x in engine['intents'] if x.get('semantic_action')=='REACT')
    assert intent['causal_source_event_id']=='S_REACT_CAUSE_PHYS' and intent['causal_target_event_id']=='S_REACT_REACTOR_PHYS',intent
    rows=sorted((x for x in engine['physical_actions'] if x['interaction_id']==intent['interaction_id']),key=lambda x:float(x['start_seconds']))
    assert len(rows)==2 and [x['phase'] for x in rows]==['ACTION','REACTION'],rows
    assert [x['event_id'] for x in rows]==['S_REACT_CAUSE_PHYS','S_REACT_REACTOR_PHYS'],rows
    assert all('TRANSLATE' not in set(x.get('required_operations') or []) for x in rows),rows
    assert float(rows[1]['start_seconds'])>=float(rows[0]['end_seconds'])+1/30.-1e-6,rows
    by={e['event_id']:e for e in motion['events']}
    for eid in ('S_REACT_CAUSE_PHYS','S_REACT_REACTOR_PHYS'):
        e=by[eid];assert not e.get('translation_safe_after_occlusion'),e
        assert (e.get('preset_entry') or {}).get('name')=='APPEAR_HIGH_SCALE',e
        assert float(rows[0 if eid.endswith('CAUSE_PHYS') else 1]['start_seconds'])>=float(e['physical_start_seconds'])-1e-6
        assert float(rows[0 if eid.endswith('CAUSE_PHYS') else 1]['end_seconds'])<=float(e['physical_end_seconds'])+1e-6
    print('V31_PROBLEM2_FULL_PLANNER_REACT_PASS',{'retimed_existing_motion_count':engine.get('retimed_existing_motion_count'),'cause_physical_start':by['S_REACT_CAUSE_PHYS']['physical_start_seconds'],'cause_entry_start':by['S_REACT_CAUSE_PHYS']['preset_entry']['start_seconds'],'reaction_entry_start':by['S_REACT_REACTOR_PHYS']['preset_entry']['start_seconds']})
