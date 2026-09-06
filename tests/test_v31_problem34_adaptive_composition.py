from __future__ import annotations
import copy,hashlib,pathlib,tempfile
import cv2,numpy as np
from PIL import Image,ImageDraw
from hexa_v31.composition_solver import composition_state_at
from hexa_v31.preset_story_planner import _adaptive_composition_state_optimize
from hexa_v31.render.scene_media import render_scene_media
from hexa_v31.layout.encoded_composition_qa import verify_encoded_composition

def event(eid,x,hit,path,translation_safe=True):
    return {'event_id':eid,'scene_id':'GENERIC_SCENE','visual_card_id':'GENERIC_CARD','source_path':str(path),'source_bbox_norm':[0,0,.18,.28],'matting':{'opaque_foreground_fraction':.82},'card_rest_position_norm':[x,.52],'planned_rect_norm':[x-.09,.38,.18,.28],'layout_scale_multiplier':1.0,'reference_camera_scale':1.0,'base_fit_scale_percent':100.0,'attention_priority':'PRIMARY' if eid=='FOCUS' else 'SUPPORTING','composition_role':'LEAD' if eid=='FOCUS' else 'SUPPORT','start_seconds':0.0 if eid=='FOCUS' else 2.0,'settle_seconds':.8 if eid=='FOCUS' else 2.8,'end_seconds':5.0,'physical_start_seconds':0.0 if eid=='FOCUS' else 2.0,'physical_end_seconds':5.0,'motion_start_seconds':0.0 if eid=='FOCUS' else 2.0,'motion_end_seconds':5.0,'perceptual_hit_seconds':hit,'translation_safe_after_occlusion':translation_safe,'animation_safe':translation_safe,'independent_motion_allowed':translation_safe,'render_mode':'ROOT_ATOMIC','preset_entry':None,'preset_exit':None,'preset_actions':[]}

with tempfile.TemporaryDirectory(prefix='hexa_problem34_') as raw:
    root=pathlib.Path(raw)
    def layer(name,color):
        p=root/(name+'.png');im=Image.new('RGBA',(320,240),(255,255,255,0));d=ImageDraw.Draw(im);d.rounded_rectangle((80,35,240,205),24,fill=(*color,255));im.save(p);return p
    a=event('FOCUS',.50,.5,layer('focus',(35,90,215)),True);b=event('SUPPORT',.72,2.8,layer('support',(220,65,55)),True);card={'card_id':'GENERIC_CARD','start_seconds':0.0,'end_seconds':5.0,'duration_seconds':5.0,'universal_scene_grammar':{'archetype':'CHARACTER_EXPLAINS_OBJECT'}};cards={'cards':[card]}
    first=_adaptive_composition_state_optimize([a,b],cards,30.0);second_events=[event('FOCUS',.50,.5,a['source_path'],True),event('SUPPORT',.72,2.8,b['source_path'],True)];second=_adaptive_composition_state_optimize(second_events,cards,30.0)
    assert first==second and first['candidates_committed']==1,(first,second)
    assert len(a['composition_states'])==2 and abs(a['composition_states'][1]['center_norm'][0]-.28)<1e-6,a
    before=composition_state_at(a,1.0);after=composition_state_at(a,3.5);assert abs(before[0][0]-after[0][0])>=.20 and after[1]==.92,(before,after)
    unsafe=event('UNSAFE',.50,.5,a['source_path'],False);unsafe['attention_priority']='PRIMARY';target=event('TARGET',.72,2.8,b['source_path'],True);safe_stats=_adaptive_composition_state_optimize([unsafe,target],cards,30.0);assert safe_stats['candidates_committed']==1,safe_stats;assert unsafe['composition_states'][1]['center_norm']==unsafe['composition_states'][0]['center_norm'] and unsafe['composition_states'][1]['scale_multiplier']==1.14,unsafe
    motion={'fps':30.0,'scenes':[{'scene_id':'GENERIC_SCENE','start_seconds':0.0,'end_seconds':5.0,'transition':{'mode':'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND'}}],'events':[a,b],'visual_cards':cards,'motion_dna_version':'PROBLEM34_TEST','hard_invariants':{}}
    edit={'events':[copy.deepcopy(a),copy.deepcopy(b)]};out=root/'out';cache=root/'cache';manifest=render_scene_media(edit,motion,[],{'events':[]},{'events':[]},out,cache,width=640,height=360,fps=30.0);video=manifest['clips'][0]['source_path'];qa=verify_encoded_composition(video,motion,{'median_estimated_alpha_coverage':.03},30.0)
    assert qa['pass'] and qa['planned_recomposition_count']==1 and qa['encoded_recomposition_verified_count']==1,qa
    first_sha=hashlib.sha256(pathlib.Path(video).read_bytes()).hexdigest();mutated=copy.deepcopy(motion);mutated['events'][0]['composition_states'][1]['center_norm']=[.72,.52];mutated_edit={'events':[copy.deepcopy(x) for x in mutated['events']]};manifest2=render_scene_media(mutated_edit,mutated,[],{'events':[]},{'events':[]},root/'out2',cache,width=640,height=360,fps=30.0);second_sha=hashlib.sha256(pathlib.Path(manifest2['clips'][0]['source_path']).read_bytes()).hexdigest();assert first_sha!=second_sha,(first_sha,second_sha)
print('V31_PROBLEM34_ADAPTIVE_COMPOSITION_PASS')
