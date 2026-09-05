from __future__ import annotations
import copy,json,pathlib,tempfile
from PIL import Image,ImageDraw
from hexa_v31.planning.preset_story_planner import build_preset_story_motion_plan
from hexa_v31.interaction.director import apply_interaction_director
from hexa_v31.scene_media import render_scene_media

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
    base=build_preset_story_motion_plan(plan,alignment,vision,RULES,REFERENCE,fps=30.0)
    base_rows=[]
    for e in sorted(base['events'],key=lambda x:x['event_id']):
        entry=e.get('preset_entry') or {};base_rows.append({
            'event_id':e['event_id'],'attention_priority':e.get('attention_priority'),
            'semantic_intent':e.get('semantic_intent'),'perceptual_hit_seconds':e.get('perceptual_hit_seconds'),
            'start_seconds':e.get('start_seconds'),'settle_seconds':e.get('settle_seconds'),'end_seconds':e.get('end_seconds'),
            'physical_start_seconds':e.get('physical_start_seconds'),'physical_end_seconds':e.get('physical_end_seconds'),
            'preset_entry':entry,'preset_exit':e.get('preset_exit'),'planned_rect_norm':e.get('planned_rect_norm'),
            'translation_safe_after_occlusion':e.get('translation_safe_after_occlusion'),'independent_motion_allowed':e.get('independent_motion_allowed'),
        })
    print('V31_FULL_PLANNER_REACT_BASE_STATE',json.dumps(base_rows,sort_keys=True),flush=True)
    base_by={e['event_id']:copy.deepcopy(e) for e in base['events']}
    motion=apply_interaction_director(base,plan,alignment,fps=30.0)
    engine=motion.get('interaction_engine') or {};qa=motion.get('interaction_plan_qa') or {}
    assert qa.get('pass'),qa
    assert engine.get('actionable_interaction_count')==1,engine
    assert engine.get('embodied_interaction_count')==1 and engine.get('embodiment_ratio')==1.0,engine
    assert engine.get('react_reverse_direction_count')==1,engine
    assert engine.get('semantic_promoted_reaction_count')==1,engine
    assert engine.get('retimed_existing_motion_count')==1,engine
    intent=next(x for x in engine['intents'] if x.get('semantic_action')=='REACT')
    assert intent['causal_source_event_id']=='S_REACT_CAUSE_PHYS' and intent['causal_target_event_id']=='S_REACT_REACTOR_PHYS',intent
    rows=sorted((x for x in engine['physical_actions'] if x['interaction_id']==intent['interaction_id']),key=lambda x:float(x['start_seconds']))
    assert len(rows)==2 and [x['phase'] for x in rows]==['ACTION','REACTION'],rows
    assert [x['event_id'] for x in rows]==['S_REACT_CAUSE_PHYS','S_REACT_REACTOR_PHYS'],rows
    assert all('TRANSLATE' not in set(x.get('required_operations') or []) for x in rows),rows
    assert float(rows[1]['start_seconds'])>=float(rows[0]['end_seconds'])+1/30.-1e-6,rows
    by={e['event_id']:e for e in motion['events']}
    cause=by['S_REACT_CAUSE_PHYS'];reaction=by['S_REACT_REACTOR_PHYS'];old_reaction=base_by['S_REACT_REACTOR_PHYS']
    assert not cause.get('translation_safe_after_occlusion') and not reaction.get('translation_safe_after_occlusion')
    assert (cause.get('preset_entry') or {}).get('name')=='APPEAR_HIGH_SCALE' and (reaction.get('preset_entry') or {}).get('name')=='APPEAR_HIGH_SCALE'
    assert abs(float(cause['preset_entry']['start_seconds'])-float(base_by['S_REACT_CAUSE_PHYS']['preset_entry']['start_seconds']))<1e-6
    expected_reaction_start=float(intent['semantic_hit_seconds'])-.70*float(reaction['preset_entry']['duration_seconds'])
    assert abs(float(reaction['preset_entry']['start_seconds'])-expected_reaction_start)<=1/30.+1e-6,(reaction,intent)
    assert float(reaction['preset_entry']['start_seconds'])>float(old_reaction['preset_entry']['start_seconds'])+.5
    assert abs(float(reaction['start_seconds'])-float(reaction['preset_entry']['start_seconds']))<1e-6
    assert abs(float(reaction['settle_seconds'])-(float(reaction['preset_entry']['start_seconds'])+float(reaction['preset_entry']['duration_seconds'])))<1e-6
    retime=(reaction['preset_entry'].get('interaction_causal_retime') or {})
    assert retime.get('reason')=='REACT_SOURCE_INTERVAL_FALLBACK_PROMOTED_TO_SEMANTIC_HIT',retime
    assert reaction['preset_entry'].get('semantic_promotion_authority')=='REACT_SOURCE_INTERVAL_FALLBACK_PROMOTED_TO_SEMANTIC_HIT'
    assert float(reaction['physical_start_seconds'])==float(old_reaction['physical_start_seconds'])==0.0
    assert float(reaction['physical_end_seconds'])==float(old_reaction['physical_end_seconds'])==4.0
    entry_interval=next(x for x in reaction.get('motion_intervals') or [] if str(x.get('kind')).upper()=='ENTRY')
    assert abs(float(entry_interval['start_seconds'])-float(reaction['preset_entry']['start_seconds']))<1e-6,entry_interval
    assert abs(float(entry_interval.get('effective_end_seconds',0))-(float(reaction['preset_entry']['start_seconds'])+float(reaction['preset_entry']['duration_seconds'])))<1e-6,entry_interval
    assert abs(float(rows[1]['perceptual_impact_seconds'])-float(intent['semantic_hit_seconds']))<=1/30.+1e-6,rows[1]
    for row in rows:
        e=by[row['event_id']];assert float(row['start_seconds'])>=float(e['physical_start_seconds'])-1e-6;assert float(row['end_seconds'])<=float(e['physical_end_seconds'])+1e-6

    # Render the exact production-planner result.  The interaction is not certified
    # unless the encoded pixels prove both the early cause and the promoted reaction.
    edit_events=[]
    for e in motion['events']:
        row=copy.deepcopy(e);row['source_path']=row.get('source_layer_path');row['base_fit_scale_percent']=100.0;rect=row.get('planned_rect_norm') or [.4,.4,.2,.2];row['object_rest_position_px']=[(float(rect[0])+float(rect[2])/2)*1920,(float(rect[1])+float(rect[3])/2)*1080];row['sequence_width']=1920;row['sequence_height']=1080;edit_events.append(row)
    manifest=render_scene_media({'events':edit_events},motion,vision,{'events':[]},{'events':[]},td/'rendered',td/'render_cache',width=640,height=360,fps=30.0)
    pixel=manifest.get('interaction_pixel_qa') or {}
    assert pixel.get('pass') and pixel.get('verified_action_count')==2 and not pixel.get('vacuous'),pixel
    assert manifest.get('visual_timeline_coverage_qa',{}).get('pass'),manifest.get('visual_timeline_coverage_qa')
    assert manifest.get('encoded_visual_gap_qa',{}).get('pass'),manifest.get('encoded_visual_gap_qa')
    print('V31_PROBLEM2_FULL_PLANNER_REACT_PASS',json.dumps({'semantic_promoted_reaction_count':engine.get('semantic_promoted_reaction_count'),'cause_entry_start':cause['preset_entry']['start_seconds'],'reaction_entry_start':reaction['preset_entry']['start_seconds'],'semantic_hit_seconds':intent['semantic_hit_seconds'],'physical_actions':engine['physical_action_count'],'pixel_verified':pixel.get('verified_action_count')},sort_keys=True))
