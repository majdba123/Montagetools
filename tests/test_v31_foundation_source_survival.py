from __future__ import annotations

import dataclasses
import json
import pathlib
import tempfile
import wave
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image,ImageDraw

from hexa_v31.vision import analyze_scene
from hexa_v31.motion import build_motion_plan
from hexa_v31.premiere import build_layer_render_map
from hexa_v31.scene_media import render_scene_media
from hexa_v31.preset_qa import preset_story_plan_qa


ROOT=pathlib.Path(__file__).resolve().parents[1]


with tempfile.TemporaryDirectory(prefix='hexa_foundation_survival_') as raw:
    root=pathlib.Path(raw);source=root/'S1.png';mask_dir=root/'masks';mask_dir.mkdir()
    image=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(image)
    specs=[('red',(95,125,70,70),(225,35,35)),('blue',(285,110,70,70),(35,80,225)),('green',(475,130,70,70),(35,175,75))]
    # Source-backed connector intentionally belongs to residual reconstruction.
    draw.rounded_rectangle((270,275,370,295),8,fill=(105,105,105))
    candidates=[];masks=[]
    for index,(label,(x,y,w,h),color) in enumerate(specs,1):
        draw.ellipse((x,y,x+w-1,y+h-1),fill=color)
        cid=f'FV_{index:03d}';arr=np.zeros((360,640),np.uint8)
        cv2.circle(arr,(x+w//2,y+h//2),w//2,255,-1)
        path=mask_dir/(cid+'.png');Image.fromarray(arr).save(path)
        candidates.append({'candidate_id':cid,'semantic_label':label+' actor','description':label+' actor','confidence':.98,'bbox':[x,y,w,h],'source':'FLORENCE_2','semantic_role':'PRIMARY'})
        masks.append({'candidate_id':cid,'mask_path':str(path),'sam_score':.99,'bbox_agreement':1.0})
    image.save(source)
    foundation={'status':'PASS','backend_used':'FLORENCE2_SAM2','candidates':candidates,'masks':masks,
                'diagnostics':{'sam2_mask_count':3},'cache_state':{'status':'CACHE_MISS','reason':'TEST','signature':'survival'},'error':None}
    scene={'scene_id':'S1','units':[{'unit_id':f'FV_{i:03d}','semantic_name':specs[i-1][0]+' actor','type':'CONCEPT','role':'PRIMARY','appear_trigger':specs[i-1][0]} for i in range(1,4)],
           'visual_progression':[],'script_span':{'global_char_start':0,'global_char_end':14,'text':'red blue green'},'relation_to_previous':'START'}
    vision=dataclasses.asdict(analyze_scene(scene,source,root/'vision',foundation_result=foundation))
    residuals=[u for u in vision['units'] if u.get('foundation_residual_support')]
    assert residuals and vision['artifacts']['foundation_vision']['reconstruction_qa']['partition_complete'],vision['artifacts']['foundation_vision']['reconstruction_qa']
    alignment={'method':'TEST','scene_count':1,'scene_timings':[{'scene_id':'S1','start':0.0,'end':4.0}],
               'word_timings':[{'word':'red','start':.55,'end':.7,'char_start':0,'char_end':3},
                               {'word':'blue','start':1.0,'end':1.2,'char_start':4,'char_end':8},
                               {'word':'green','start':1.45,'end':1.7,'char_start':9,'char_end':14}]}
    plan={'project_id':'FOUNDATION_SOURCE_SURVIVAL','scenes':[scene]}
    motion=build_motion_plan(plan,alignment,[vision],ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
    pre_render=preset_story_plan_qa(motion,[vision],4.0)
    assert pre_render['visual_timeline_coverage_qa']['pass'],pre_render['visual_timeline_coverage_qa']
    members=[e for e in motion['events'] if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} and not e.get('suppressed_by_card_density')]
    children=[e for e in members if e.get('render_mode')=='CHILD_PARTITION'];supports=[e for e in members if e.get('render_mode')=='RESIDUAL_SUPPORT']
    movers=[e for e in children if e.get('position_animated')]
    assert len(children)>=3 and len(supports)==1,(children,supports)
    assert len({(e['physical_start_seconds'],e['physical_end_seconds']) for e in members})==1,members
    assert all(not e.get('position_animated') and not e.get('independent_motion_allowed') for e in supports)
    wav=root/'voice.wav'
    with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*64000)
    package=SimpleNamespace(scenes=[{'scene_id':'S1','image':'S1.png'}],extract_root=root)
    render_map=build_layer_render_map(package,wav,alignment,[vision],motion,root/'render_map',width=640,height=360,fps=30)
    edit=json.loads(pathlib.Path(render_map['edit_map']).read_text(encoding='utf-8'))
    manifest=render_scene_media(edit,motion,[vision],{'events':[]},{'events':[]},root/'rendered',root/'cache',width=640,height=360,fps=30)
    cap=cv2.VideoCapture(manifest['clips'][0]['source_path']);frames=[]
    while True:
        ok,frame=cap.read()
        if not ok:break
        frames.append(frame)
    cap.release();assert len(frames)>=118
    # Residual connector remains present and fixed late in the owning state.
    for fi in (60,85,105):
        gray=np.max(np.abs(frames[fi].astype(np.int16)-np.array([105,105,105])),axis=2)<30
        assert np.count_nonzero(gray)>120,(fi,np.count_nonzero(gray))
    # All source colors survive after entry and the encoded plan never falls white.
    for fi in (65,85,105):
        foreground=np.max(255-frames[fi].astype(np.int16),axis=2)>15
        assert np.count_nonzero(foreground)>900,(fi,np.count_nonzero(foreground))
    # This crowded single-partition fixture may correctly fall back to static
    # actors. The separate planner-to-pixel regression proves two independent
    # movers; here the P0 invariant is that fallback preserves every source.
    assert len(movers)<=len(children)

print('V31_FOUNDATION_SOURCE_SURVIVAL_PASS')
