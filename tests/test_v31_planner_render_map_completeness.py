from __future__ import annotations
import copy,json,pathlib,tempfile,wave
from types import SimpleNamespace
import cv2,numpy as np
from PIL import Image,ImageDraw
from hexa_v31.premiere import PremiereError,build_layer_render_map
from hexa_v31.scene_media import render_scene_media
from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa

def make_layer(path,box,color):
    rgba=Image.new('RGBA',(640,360),(255,255,255,0));ImageDraw.Draw(rgba).rounded_rectangle(box,24,fill=(*color,255));rgba.save(path)

def event(eid,scene,pid,start,end,layer_path,center,role='PRIMARY'):
    return {'event_id':eid,'scene_id':scene,'visual_card_id':'CARD_ARBITRARY','physical_id':pid,'render_mode':'ROOT_ATOMIC','source_layer_path':str(layer_path),
        'start_seconds':start,'settle_seconds':start,'end_seconds':end,'physical_start_seconds':start,'physical_end_seconds':end,'motion_start_seconds':start,'motion_end_seconds':start,
        'preset_entry':None,'preset_exit':None,'preset_actions':[],'appearance_method':'CONTINUATION','disappearance_method':'HOLD_TO_BOUNDARY','position_animated':False,
        'start_x_norm':center[0],'start_y_norm':center[1],'end_x_norm':center[0],'end_y_norm':center[1],'exit_x_norm':center[0],'exit_y_norm':center[1],
        'card_rest_position_norm':list(center),'reference_camera_scale':1.0,'layout_scale_multiplier':1.0,'attention_priority':role,'semantic_role':role,'kind':'VISUAL',
        'focus_beats':[],'story_beats':[],'story_actions':[],'drift_dx_norm':0.0,'drift_dy_norm':0.0,'suppressed_by_card_density':False,'visual_carrier_id':f'CARD_ARBITRARY::{scene}::{eid}'}

with tempfile.TemporaryDirectory(prefix='hexa_render_map_flat_scene_') as raw:
    root=pathlib.Path(raw);scene_a='ALPHA_ARBITRARY';scene_b='OMEGA_ARBITRARY'
    image_a=root/'alpha.png';image_b=root/'omega.png';Image.new('RGB',(640,360),'white').save(image_a);Image.new('RGB',(640,360),'white').save(image_b)
    layer_a=root/'actor_a.png';layer_b=root/'actor_b.png';layer_c=root/'actor_c.png'
    make_layer(layer_a,(40,30,300,335),(220,45,45));make_layer(layer_b,(340,25,620,335),(45,95,220));make_layer(layer_c,(80,25,560,335),(45,175,85))
    units_a=[{'physical_id':'PHYS_ALPHA','layer_path':str(layer_a),'mask_path':str(layer_a),'layer_canvas_mode':'FULL_SCENE_ALPHA_CANVAS','center_norm':[.27,.52],'semantic_role':'PRIMARY'},
             {'physical_id':'PHYS_BETA','layer_path':str(layer_b),'mask_path':str(layer_b),'layer_canvas_mode':'FULL_SCENE_ALPHA_CANVAS','center_norm':[.73,.50],'semantic_role':'SUPPORTING'}]
    units_b=[{'physical_id':'PHYS_GAMMA','layer_path':str(layer_c),'mask_path':str(layer_c),'layer_canvas_mode':'FULL_SCENE_ALPHA_CANVAS','center_norm':[.50,.52],'semantic_role':'PRIMARY'}]
    vision=[{'scene_id':scene_a,'mode':'FLAT_SCENE','width':640,'height':360,'units':units_a,'artifacts':{}},{'scene_id':scene_b,'mode':'CLEAN_LAYERED','width':640,'height':360,'units':units_b,'artifacts':{}}]
    events=[event('EV_ALPHA',scene_a,'PHYS_ALPHA',0.0,2.0,layer_a,(.27,.52),'PRIMARY'),event('EV_BETA',scene_a,'PHYS_BETA',0.0,2.0,layer_b,(.73,.50),'SUPPORTING'),event('EV_GAMMA',scene_b,'PHYS_GAMMA',2.0,4.0,layer_c,(.50,.52),'PRIMARY')]
    motion={'fps':30.0,'events':events,'scenes':[{'scene_id':scene_a,'start_seconds':0.0,'end_seconds':2.0},{'scene_id':scene_b,'start_seconds':2.0,'end_seconds':4.0}],
            'visual_cards':{'cards':[{'card_id':'CARD_ARBITRARY','start_seconds':0.0,'end_seconds':4.0}]},'hard_invariants':{}}
    package=SimpleNamespace(scenes=[{'scene_id':scene_a,'image':image_a.name},{'scene_id':scene_b,'image':image_b.name}],extract_root=root)
    wav=root/'voice.wav'
    with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*(16000*4))
    result=build_layer_render_map(package,wav,{},vision,motion,root/'render_map',width=640,height=360,fps=30.0)
    edit=json.loads(pathlib.Path(result['edit_map']).read_text(encoding='utf-8'));qa=edit['planner_render_map_completeness_qa']
    assert qa['pass'],qa
    assert qa['expected_renderable_event_count']==3 and qa['mapped_event_count']==3,qa
    assert qa['missing_event_ids']==[] and qa['unexpected_event_ids']==[],qa
    mapped={row['event_id']:row for row in edit['events']};assert set(mapped)=={'EV_ALPHA','EV_BETA','EV_GAMMA'},mapped
    assert all(mapped[e['event_id']]['source_path']==str(pathlib.Path(e['source_layer_path']).resolve()) for e in events)
    assert all((mapped[e['event_id']]['physical_start_seconds'],mapped[e['event_id']]['physical_end_seconds'])==(e['physical_start_seconds'],e['physical_end_seconds']) for e in events)
    assert all(x['item_role']=='PLANNER_RENDER_EVENT' for x in edit['assembly']['video_items']);assert not any(x.get('item_role')=='FLAT_SCENE' for x in edit['assembly']['video_items'])
    mapped_plan=dict(motion);mapped_plan['events']=edit['events'];coverage=visual_timeline_coverage_qa(mapped_plan,fps=30.0,duration_seconds=4.0);assert coverage['pass'],coverage
    manifest=render_scene_media(edit,motion,vision,{'events':[]},{'events':[]},root/'rendered',root/'render_cache',width=640,height=360,fps=30.0)
    assert manifest['motion_event_count']==3,manifest
    output=pathlib.Path(manifest['clips'][0]['source_path']);assert output.is_file() and output.stat().st_size>4096,output
    cap=cv2.VideoCapture(str(output));ok,first=cap.read();cap.release();assert ok and first is not None
    foreground=np.max(255-first.astype(np.int16),axis=2)>15;assert np.count_nonzero(foreground)>250,(np.count_nonzero(foreground),first.shape)
    broken=copy.deepcopy(motion);broken['events'][0]['physical_id']='PHYS_DOES_NOT_EXIST';broken['events'][0]['source_layer_path']=str(root/'does-not-exist.png')
    try:
        build_layer_render_map(package,wav,{},vision,broken,root/'broken_map',width=640,height=360,fps=30.0);raise AssertionError('unresolved planner event was silently accepted')
    except PremiereError as exc:
        message=str(exc);assert 'PLANNER_RENDER_MAP_EVENT_UNRESOLVED' in message,message;assert 'event_id=EV_ALPHA' in message,message;assert 'physical_id=PHYS_DOES_NOT_EXIST' in message,message
print('V31_PLANNER_RENDER_MAP_COMPLETENESS_PASS')
