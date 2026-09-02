from pathlib import Path
import tempfile
import cv2
import numpy as np
from PIL import Image, ImageDraw
from hexa_v31.scene_media import render_scene_media

def centroid(frame, rgb):
    # Codec-tolerant color identity tracking for the synthetic Foundation actors.
    bgr=np.array(rgb[::-1]); delta=np.max(np.abs(frame.astype(np.int16)-bgr.astype(np.int16)),axis=2)
    yy,xx=np.where(delta<75)
    assert len(xx)>30
    return np.array([xx.mean(),yy.mean()])

with tempfile.TemporaryDirectory() as raw:
    td=Path(raw); paths=[]
    for name,color in [('red',(230,45,35)),('blue',(35,80,230))]:
        image=Image.new('RGBA',(640,360),(0,0,0,0));ImageDraw.Draw(image).ellipse((270,130,370,230),fill=(*color,255));p=td/(name+'.png');image.save(p);paths.append(p)
    def event(name, path, preset):
        return {'event_id':name,'physical_id':name,'scene_id':'S1','source_path':str(path),'base_fit_scale_percent':100.0,'start_seconds':0.0,'end_seconds':3.5,'render_mode':'CHILD_PARTITION','translation_safe_after_occlusion':True,'independent_motion_allowed':True,'position_animated':True,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','preset_entry':{'name':preset,'start_seconds':0.0,'duration_seconds':1.44},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':2.7,'duration_seconds':0.6},'preset_actions':[]}
    motion={'motion_dna_version':'HEXA_MOTION_DNA_V31_0_26_FOUNDATION_PARTITION_CHOREOGRAPHY','preset_authority':'HEXA_USER_PRESET_AUTHORITY_V31','hard_invariants':{},'scenes':[{'scene_id':'S1','start_seconds':0,'end_seconds':3.5}],'visual_cards':{'cards':[{'card_id':'C1','start_seconds':0,'end_seconds':3.5}]}}
    manifest=render_scene_media({'events':[event('red',paths[0],'ENTRY_LEFT_TO_MIDDLE'),event('blue',paths[1],'ENTRY_RIGHT_TO_MIDDLE')]},motion,[],{'events':[]},{'events':[]},td/'out',td/'cache',width=640,height=360,fps=30)
    cap=cv2.VideoCapture(manifest['clips'][0]['source_path']);frames=[]
    for n in (8,40): cap.set(cv2.CAP_PROP_POS_FRAMES,n);ok,frame=cap.read();assert ok;frames.append(frame)
    cap.release();red=[centroid(f,(230,45,35)) for f in frames];blue=[centroid(f,(35,80,230)) for f in frames]
    rv=red[1]-red[0];bv=blue[1]-blue[0]
    assert np.linalg.norm(rv)>25 and np.linalg.norm(bv)>25
    assert np.linalg.norm(rv-bv)>50  # independently visible trajectories, not a shared transform
print('V31_FOUNDATION_PARTITION_PIXEL_MOTION_PASS')
