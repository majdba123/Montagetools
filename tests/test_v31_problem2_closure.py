from __future__ import annotations
import copy,pathlib,tempfile
import numpy as np,cv2
from PIL import Image,ImageDraw
from hexa_v31.interaction.director import apply_interaction_director
from hexa_v31.interaction.graphics_guard import guard_relationship_graphics
from hexa_v31.scene_media import render_scene_media
from hexa_v31.preset_authority import duration

def base_event(eid,x,role,intent,path):
    return {'event_id':eid,'scene_id':'FUTURE_PACKAGE_SCENE_X','visual_card_id':'FUTURE_CARD_X','semantic_unit_id':eid,'semantic_scope_id':'FUTURE_PACKAGE_SCENE_X::'+eid,'semantic_type':'CONCEPT','semantic_role':role,'attention_priority':role,'semantic_intent':intent,'canonical_clause':intent,'semantic_mapping_confidence':.99,'translation_safe_after_occlusion':True,'animation_safe':True,'scale_safe':True,'reveal_safe':True,'render_mode':'ROOT_ATOMIC','card_rest_position_norm':[x,.493],'planned_rect_norm':[x-.075,.413,.15,.16],'source_bbox_norm':[x-.075,.413,.15,.16],'layout_scale_multiplier':1.,'reference_camera_scale':1.,'source_path':str(path),'base_fit_scale_percent':100.,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','object_rest_position_px':[x*1920,.493*1080],'start_seconds':0.,'settle_seconds':.30,'end_seconds':4.4,'physical_start_seconds':0.,'physical_end_seconds':4.4,'motion_start_seconds':0.,'motion_end_seconds':.30,'preset_entry':None,'preset_exit':None,'preset_actions':[],'motion_intervals':[],'perceptual_hit_seconds':.85,'z_order':2 if role=='PRIMARY' else 3}

def set_appearance_entry(e,start):
    name='APPEAR_HIGH_SCALE';dd=duration(name);e['translation_safe_after_occlusion']=False;e['animation_safe']=False;e['scale_safe']=True;e['reveal_safe']=True;e['animation_mode']='IN_PLACE_ACTING_ONLY';e['occlusion_class']='ATOMIC_PARENT_DEPENDENT';e['preset_entry']={'name':name,'start_seconds':round(start,6),'duration_seconds':dd};e['start_seconds']=round(start,6);e['settle_seconds']=round(start+dd,6);e['motion_start_seconds']=round(start,6);e['motion_end_seconds']=round(start+dd,6);e['perceptual_hit_seconds']=round(start+.70*dd,6)

with tempfile.TemporaryDirectory(prefix='hexa_problem2_closure_') as raw:
    root=pathlib.Path(raw)
    def layer(name,color):
        im=Image.new('RGBA',(640,360),(255,255,255,255));d=ImageDraw.Draw(im);d.rounded_rectangle((270,125,370,235),18,fill=(*color,255));p=root/(name+'.png');im.save(p);return p
    source=layer('source',(215,55,55));target=layer('target',(45,95,220))
    base={'fps':30.,'events':[base_event('SOURCE',.487,'PRIMARY','TRANSFER',source),base_event('TARGET',.833,'SUPPORTING','',target)],'visual_cards':{'cards':[{'card_id':'FUTURE_CARD_X','start_seconds':0.,'end_seconds':4.4}]},'semantic_visual_sentence_compiler':{'sentences':[{'sentence_id':'SENTENCE_FUTURE_X','scene_id':'FUTURE_PACKAGE_SCENE_X','visual_card_id':'FUTURE_CARD_X','subject_event_id':'SOURCE','action':'TRANSFER','object_event_id':'TARGET','result_event_id':None,'confidence':.95,'physical_support':True}]},'budget_summary':{},'hard_invariants':{'full_frame_crossfade_forbidden':True},'motion_dna_version':'BASE','scenes':[{'scene_id':'FUTURE_PACKAGE_SCENE_X','start_seconds':0.,'end_seconds':4.4}]}
    source_plan={'scenes':[{'scene_id':'FUTURE_PACKAGE_SCENE_X','units':[{'unit_id':'SOURCE'},{'unit_id':'TARGET'}]}]}
    motion=apply_interaction_director(copy.deepcopy(base),source_plan,{},30.);engine=motion['interaction_engine']
    assert motion['interaction_plan_qa']['pass'] and engine['physical_action_count']==2 and engine['embodiment_ratio']==1.0,engine
    assert engine['intent_compiler']['intents'][0]['pair_authority']=='SEMANTIC_SENTENCE_EXPLICIT_PAIR'
    graphic_motion=copy.deepcopy(motion);source_event=next(e for e in graphic_motion['events'] if e['event_id']=='SOURCE');target_event=next(e for e in graphic_motion['events'] if e['event_id']=='TARGET');source_event['physical_end_seconds']=2.1;source_event['semantic_readable_not_before_seconds']=.4;target_event['physical_start_seconds']=.5;target_event['semantic_readable_not_before_seconds']=.8
    gp={'events':[{'graphic_id':'ARROW_FUTURE','kind':'ARROW','scene_id':'FUTURE_PACKAGE_SCENE_X','source_semantic_unit_id':'SOURCE','target_semantic_unit_id':'TARGET','start_seconds':.1,'end_seconds':3.0}],'event_count':1}
    guarded=guard_relationship_graphics(gp,graphic_motion,30.);assert guarded['event_count']==1,guarded;arrow=guarded['events'][0];assert abs(arrow['start_seconds']-.8)<1e-6 and abs(arrow['end_seconds']-2.1)<1e-6,guarded;assert arrow['interaction_orphan_guard']=='SOURCE_AND_TARGET_VISIBLE_OVERLAP'
    no_overlap=copy.deepcopy(graphic_motion);next(e for e in no_overlap['events'] if e['event_id']=='TARGET')['physical_start_seconds']=2.5;assert guard_relationship_graphics(gp,no_overlap,30.)['event_count']==0
    edit={'events':[copy.deepcopy(e) for e in motion['events']]};manifest=render_scene_media(edit,motion,[],{'events':[]},{'events':[]},root/'out',root/'cache',width=1920,height=1080,fps=30.)
    framing=manifest.get('visible_ink_source_framing') or {};assert framing.get('changed_event_count')==2,framing
    qa=manifest.get('interaction_pixel_qa') or {};assert qa.get('pass') and qa.get('verified_action_count')==2 and not qa.get('vacuous'),qa
    assert manifest['visual_timeline_coverage_qa']['pass'] and manifest['encoded_visual_gap_qa']['pass']

    # Production failure regression: translation safety is an operation-level guard,
    # not a blanket ban on interaction. Both actors are physically unsafe to translate
    # but remain certified for in-place scale/reveal. Existing APPEAR_HIGH_SCALE entries
    # are the causal ACTION/REACTION and must survive through encoded pixel verification.
    unsafe_source=layer('unsafe_source',(55,170,95));unsafe_target=layer('unsafe_target',(175,95,210))
    us=base_event('UNSAFE_SOURCE',.34,'PRIMARY','REACT',unsafe_source);ut=base_event('UNSAFE_TARGET',.66,'SUPPORTING','',unsafe_target)
    set_appearance_entry(us,.12);set_appearance_entry(ut,.12+duration('APPEAR_HIGH_SCALE')+.08)
    unsafe_base={'fps':30.,'events':[us,ut],'visual_cards':{'cards':[{'card_id':'FUTURE_CARD_X','start_seconds':0.,'end_seconds':4.4}]},'semantic_visual_sentence_compiler':{'sentences':[{'sentence_id':'SENTENCE_TRANSLATION_UNSAFE','scene_id':'FUTURE_PACKAGE_SCENE_X','visual_card_id':'FUTURE_CARD_X','subject_event_id':'UNSAFE_SOURCE','action':'REACT','object_event_id':'UNSAFE_TARGET','result_event_id':None,'confidence':.95,'physical_support':True}]},'budget_summary':{},'hard_invariants':{'full_frame_crossfade_forbidden':True},'motion_dna_version':'BASE_UNSAFE','scenes':[{'scene_id':'FUTURE_PACKAGE_SCENE_X','start_seconds':0.,'end_seconds':4.4}]}
    unsafe_plan={'scenes':[{'scene_id':'FUTURE_PACKAGE_SCENE_X','units':[{'unit_id':'UNSAFE_SOURCE'},{'unit_id':'UNSAFE_TARGET'}]}]}
    unsafe_motion=apply_interaction_director(copy.deepcopy(unsafe_base),unsafe_plan,{},30.);ue=unsafe_motion['interaction_engine']
    assert unsafe_motion['interaction_plan_qa']['pass'],unsafe_motion['interaction_plan_qa']
    assert ue['physical_action_count']==2 and ue['embodiment_ratio']==1.0 and ue['fallback_report']['count']==0,ue
    unsafe_rows=sorted(ue['physical_actions'],key=lambda x:float(x['start_seconds']))
    assert [x['phase'] for x in unsafe_rows]==['ACTION','REACTION'],unsafe_rows
    assert all(x['preset']=='APPEAR_HIGH_SCALE' and 'TRANSLATE' not in set(x.get('required_operations') or []) for x in unsafe_rows),unsafe_rows
    unsafe_manifest=render_scene_media({'events':[copy.deepcopy(e) for e in unsafe_motion['events']]},unsafe_motion,[],{'events':[]},{'events':[]},root/'unsafe_out',root/'unsafe_cache',width=1920,height=1080,fps=30.)
    unsafe_pixel=unsafe_manifest.get('interaction_pixel_qa') or {}
    assert unsafe_pixel.get('pass') and unsafe_pixel.get('verified_action_count')==2 and not unsafe_pixel.get('vacuous'),unsafe_pixel

    white=root/'white.mp4';writer=cv2.VideoWriter(str(white),cv2.VideoWriter_fourcc(*'mp4v'),30.,(640,360));frame=np.full((360,640,3),255,np.uint8)
    for _ in range(132):writer.write(frame)
    writer.release();from hexa_v31.interaction.pixel_qa import verify_encoded_interactions;bad=verify_encoded_interactions(str(white),motion,30.);assert not bad['pass'] and bad['failures'],bad
print('V31_PROBLEM2_CLOSURE_PASS')
