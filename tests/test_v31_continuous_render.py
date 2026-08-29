from pathlib import Path
import tempfile
import numpy as np
from PIL import Image,ImageDraw
import cv2
from hexa_v31.scene_media import render_scene_media
with tempfile.TemporaryDirectory() as raw:
    td=Path(raw);rgba=Image.new('RGBA',(640,360),(0,0,0,0));d=ImageDraw.Draw(rgba);d.rounded_rectangle((260,120,380,240),radius=18,fill=(220,60,60,255));src=td/'layer.png';rgba.save(src)
    ev={'event_id':'E1','scene_id':'S1','source_path':str(src),'base_fit_scale_percent':300.0,'start_seconds':0.0,'end_seconds':3.6,'semantic_type':'CONCEPT','semantic_role':'PRIMARY','attention_priority':'PRIMARY','preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':0.0,'duration_seconds':1.44},'preset_exit':{'name':'EXIT_MIDDLE_TO_RIGHT','start_seconds':2.12,'duration_seconds':1.48},'preset_actions':[]}
    edit={'events':[ev]};motion={'motion_dna_version':'HEXA_MOTION_DNA_V31_0_1_UNIVERSAL_COMPOSITION_STORY_DIRECTOR','preset_authority':'HEXA_USER_PRESET_AUTHORITY_V31','hard_invariants':{'full_frame_crossfade_forbidden':True},'scenes':[{'scene_id':'S1','start_seconds':0.0,'end_seconds':3.6}],'visual_cards':{'cards':[{'card_id':'C1','start_seconds':0.0,'end_seconds':3.6}]}}
    m=render_scene_media(edit,motion,[],{'events':[]},{'events':[]},td/'out',td/'cache',width=640,height=360,fps=30.0)
    assert m['scene_count']==1 and m['full_frame_crossfade_count']==0 and m['mask_wipe_count']==0 and m['white_dip_count']==0
    cap=cv2.VideoCapture(m['clips'][0]['source_path']);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));frames=[]
    for idx in [0,36,54,90]:cap.set(cv2.CAP_PROP_POS_FRAMES,idx);ok,f=cap.read();assert ok;frames.append(f)
    cap.release()
    occ=[float(np.mean(np.any(f<245,axis=2))) for f in frames]
    assert max(occ)>0.01,occ
print('V31_CONTINUOUS_RENDER_PASS')
