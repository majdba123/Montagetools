from __future__ import annotations
import dataclasses, json, pathlib, tempfile, wave
from types import SimpleNamespace
import cv2
import numpy as np
from PIL import Image, ImageDraw
from hexa_v31.vision import analyze_scene
from hexa_v31.motion import build_motion_plan
from hexa_v31.premiere import build_layer_render_map
from hexa_v31.scene_media import render_scene_media

ROOT=pathlib.Path(__file__).resolve().parents[1]

def color_centroid(frame, red):
    channel=2 if red else 0;other=0 if red else 2
    mask=(frame[:,:,channel]>115)&(frame[:,:,channel]>frame[:,:,other]*1.35)
    yy,xx=np.where(mask);assert len(xx)>30
    return np.array([xx.mean(),yy.mean()])

with tempfile.TemporaryDirectory() as raw:
    root=pathlib.Path(raw);mask_dir=root/'masks';mask_dir.mkdir();scenes=[];visions=[]
    specs=[('S1','red',(230,45,35),(100,150,51,51),'START'),('S2','blue',(35,80,230),(490,150,51,51),'NEW_IDEA')]
    for index,(sid,word,color,box,relation) in enumerate(specs,1):
        source=root/(sid+'.png');image=Image.new('RGB',(640,360),'white');x,y,w,h=box;ImageDraw.Draw(image).ellipse((x,y,x+w-1,y+h-1),fill=color);image.save(source)
        cid=f'FV_{index:03d}';arr=np.zeros((360,640),np.uint8);arr[y:y+h,x:x+w]=255;mp=mask_dir/(cid+'.png');Image.fromarray(arr).save(mp)
        foundation={'status':'PASS','backend_used':'FLORENCE2_SAM2','candidates':[{'candidate_id':cid,'semantic_label':word+' actor','description':word+' actor','confidence':.97,'bbox':list(box),'source':'FLORENCE_2','semantic_role':'PRIMARY'}],'masks':[{'candidate_id':cid,'mask_path':str(mp),'sam_score':.98,'bbox_agreement':1.0}],'diagnostics':{'sam2_mask_count':1},'cache_state':{'status':'CACHE_MISS','reason':'TEST','signature':'planner-pixel-'+sid},'error':None}
        scene={'scene_id':sid,'units':[{'unit_id':cid,'semantic_name':word+' actor','type':'CONCEPT','role':'PRIMARY','appear_trigger':word}],'visual_progression':[],'script_span':{'global_char_start':0,'global_char_end':len(word),'text':word},'relation_to_previous':relation}
        scenes.append(scene);visions.append(dataclasses.asdict(analyze_scene(scene,source,root/('vision_'+sid),foundation_result=foundation)))
    plan={'project_id':'FOUNDATION_PLANNER_PIXEL','scenes':scenes}
    alignment={'method':'TEST','scene_count':2,'scene_timings':[{'scene_id':'S1','start':0.0,'end':4.0},{'scene_id':'S2','start':4.0,'end':8.0}],'word_timings':[{'word':'red','start':.65,'end':.85},{'word':'blue','start':4.65,'end':4.85}]}
    motion=build_motion_plan(plan,alignment,visions,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
    eligible=[e for e in motion['events'] if e.get('render_mode')=='CHILD_PARTITION' and e.get('translation_safe_after_occlusion') and e.get('independent_motion_allowed')]
    independent=[e for e in eligible if e.get('position_animated')]
    contract=motion['foundation_partition_motion_contract']
    print('FOUNDATION_PLANNER_DIAGNOSTIC',json.dumps([{
        'event_id':e.get('event_id'),'scene_id':e.get('scene_id'),'position_animated':e.get('position_animated'),
        'foundation_motion_decision':e.get('foundation_motion_decision'),'final_partition_motion_fallback':e.get('final_partition_motion_fallback'),
        'start_seconds':e.get('start_seconds'),'end_seconds':e.get('end_seconds'),
        'motion_start_seconds':e.get('motion_start_seconds'),'motion_end_seconds':e.get('motion_end_seconds'),
        'physical_start_seconds':e.get('physical_start_seconds'),'physical_end_seconds':e.get('physical_end_seconds'),
        'partition_carrier_start_seconds':e.get('partition_carrier_start_seconds'),'partition_carrier_end_seconds':e.get('partition_carrier_end_seconds'),
        'preset_entry':e.get('preset_entry'),'preset_exit':e.get('preset_exit')
    } for e in eligible],sort_keys=True))
    assert len(eligible)>=2,(eligible,motion['events']);assert len(independent)>=2,(independent,motion['visual_cards'])
    assert contract['eligible_foundation_actor_count']==len(eligible)
    assert contract['independently_animated_actor_count']==len(independent)
    assert contract['independent_actor_motion_ratio']==round(len(independent)/len(eligible),4)
    assert contract['distinct_motion_signature_count']>=2,contract
    wav=root/'voice.wav'
    with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*int(8*16000))
    package=SimpleNamespace(scenes=[{'scene_id':'S1','image':'S1.png'},{'scene_id':'S2','image':'S2.png'}],extract_root=root)
    render_map=build_layer_render_map(package,wav,alignment,visions,motion,root/'render_map',width=640,height=360,fps=30)
    edit=json.loads(pathlib.Path(render_map['edit_map']).read_text(encoding='utf-8'))
    manifest=render_scene_media(edit,motion,visions,{'events':[]},{'events':[]},root/'rendered',root/'cache',width=640,height=360,fps=30)
    cap=cv2.VideoCapture(manifest['clips'][0]['source_path']);tracks={True:[],False:[]}
    for fi in range(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))):
        ok,frame=cap.read()
        if not ok:break
        for red in (True,False):
            try:tracks[red].append((fi,color_centroid(frame,red)))
            except AssertionError:pass
    cap.release()
    vectors=[]
    for red in (True,False):
        rows=tracks[red];assert len(rows)>10
        points=[p for _,p in rows];dist=max(np.linalg.norm(b-a) for a in points for b in points);assert dist>25,dist
        vectors.append(points[-1]-points[0])
    assert np.linalg.norm(vectors[0]-vectors[1])>25,vectors
    print('V31_FOUNDATION_PLANNER_TO_PIXEL_PASS',json.dumps(contract,sort_keys=True))
