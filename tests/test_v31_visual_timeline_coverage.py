from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image

from hexa_v31.visual_timeline_coverage import encoded_visual_gap_qa, frame_survival_signature, visual_timeline_coverage_qa
from hexa_v31.render.preview import _event_state
from hexa_v31.render.scene_media import SceneMediaError, render_scene_media


with tempfile.TemporaryDirectory(prefix='hexa_visual_lifetime_') as raw:
    root=pathlib.Path(raw); layer=root/'source.png'
    rgba=np.zeros((90,160,4),np.uint8);rgba[25:65,55:105,:3]=[20,80,220];rgba[25:65,55:105,3]=255
    Image.fromarray(rgba,'RGBA').save(layer)
    card={'card_id':'CARD_1','start_seconds':0.0,'end_seconds':4.0}
    settled={
        'event_id':'ACTOR_A','visual_card_id':'CARD_1','scene_id':'S1','source_layer_path':str(layer),
        'start_seconds':0.0,'end_seconds':1.0,'motion_start_seconds':0.0,'motion_end_seconds':1.0,
        'physical_start_seconds':0.0,'physical_end_seconds':4.0,'end_position_px':[80,45],
        'settle_seconds':.5,'position_animated':False,
    }
    # Motion completion is not disappearance: the settled state survives.
    assert _event_state(settled,.75) is not None
    assert _event_state(settled,3.25) is not None
    good=visual_timeline_coverage_qa({'fps':30,'events':[settled],'visual_cards':{'cards':[card]}},duration_seconds=4.0)
    assert good['pass'] and good['card_coverage'][0]['coverage_ratio']==1.0,good

    residual={**settled,'event_id':'RESIDUAL','render_mode':'RESIDUAL_SUPPORT',
              'foundation_residual_support':True,'independent_motion_allowed':False,
              'translation_safe_after_occlusion':False,'position_animated':False,
              'animation_mode':'STATIC_SUPPORT'}
    a=_event_state(residual,.1);b=_event_state(residual,3.9)
    assert a==b and a[1:]==(1.0,1.0),(a,b)

    gap_event={**settled,'physical_end_seconds':1.0,'end_seconds':1.0,'motion_end_seconds':1.0}
    bad=visual_timeline_coverage_qa({'fps':30,'events':[gap_event],'visual_cards':{'cards':[card]}},duration_seconds=4.0)
    assert not bad['pass'] and bad['longest_uncovered_narration_seconds']>=2.9,bad
    trailing=visual_timeline_coverage_qa({'fps':30,'events':[settled],'visual_cards':{'cards':[card]}},duration_seconds=6.0)
    assert not trailing['pass'] and trailing['trailing_uncovered_seconds']==2.0,trailing
    retired={**settled,'topology_recovery':'TEMPORAL_SPATIAL_REUSE__SUPPORT_EXIT'}
    recovery=visual_timeline_coverage_qa({'fps':30,'events':[retired],'visual_cards':{'cards':[card]}})
    assert not recovery['pass'] and recovery['prematurely_truncated_event_ids']==['ACTOR_A'],recovery
    try:
        render_scene_media({'events':[gap_event]}, {'fps':30,'events':[gap_event],
            'scenes':[{'scene_id':'S1','start_seconds':0.0,'end_seconds':4.0}],
            'visual_cards':{'cards':[card]}}, [], {'events':[]}, {'events':[]},
            root/'rendered',root/'cache',width=160,height=90,fps=30)
        raise AssertionError('renderer accepted a narration-active carrier gap')
    except SceneMediaError as exc:
        message=str(exc)
        assert all(token in message for token in ('VISUAL_TIMELINE_COVERAGE_GAP','timestamp=','frame=','visual_card_id=','previous_carrier=','next_carrier=','active_actor_ids=')),message

    # Actual encode/decode: a source-backed event is expected throughout, but
    # two seconds of white frames must be rejected before delivery.
    mp4=root/'blank_gap.mp4';writer=cv2.VideoWriter(str(mp4),cv2.VideoWriter_fourcc(*'mp4v'),30,(160,90))
    assert writer.isOpened()
    for fi in range(120):
        frame=np.full((90,160,3),255,np.uint8)
        if fi<30 or fi>=90: frame[25:65,55:105]=[220,80,20]
        writer.write(frame)
    writer.release()
    encoded=encoded_visual_gap_qa(mp4,{'fps':30,'events':[settled]})
    assert not encoded['pass'] and encoded['blank_runs'][0]['duration_seconds']>=1.7,encoded

    def encode_h264(frames,path):
        ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg';h,w=frames[0].shape[:2]
        proc=subprocess.Popen([ff,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s:v',f'{w}x{h}','-r','30','-i','pipe:0','-an','-c:v','libx264','-threads','1','-crf','18','-pix_fmt','yuv420p',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
        for item in frames:proc.stdin.write(item.tobytes())
        proc.stdin.close();err=proc.stderr.read();assert proc.wait()==0,err

    members=[
        {'event_id':'CHILD_A','render_mode':'CHILD_PARTITION','bbox_px':[8,14,30,40]},
        {'event_id':'CHILD_B','render_mode':'CHILD_PARTITION','bbox_px':[45,12,92,58]},
        {'event_id':'CHILD_C','render_mode':'CHILD_PARTITION','bbox_px':[108,15,153,57]},
        {'event_id':'RESIDUAL_SUPPORT','render_mode':'RESIDUAL_SUPPORT','bbox_px':[28,68,145,84]},
    ]
    def composition(mode):
        frames=[]
        for fi in range(120):
            im=np.full((90,160,3),255,np.uint8)
            if mode!='white_gap' or not 30<=fi<90:
                im[14:40,8:30]=[225,35,35]
                if mode not in {'missing_major','tiny_only'}:im[12:58,45:92]=[35,80,225]
                if mode!='tiny_only':im[15:57,108:153]=[35,175,75]
                if mode!='residual_missing' and mode!='tiny_only':im[68:84,28:145]=[105,105,105]
            frames.append(im)
        return frames
    full=composition('full')
    evidence=[frame_survival_signature(full[fi],fi,fi/30,members) for fi in range(0,120,5)]
    structured_plan={'fps':30,'events':[{'event_id':m['event_id'],'physical_start_seconds':0,'physical_end_seconds':4} for m in members]}
    cases={}
    for mode in ('full','white_gap','missing_major','tiny_only','residual_missing'):
        path=root/(mode+'.mp4');encode_h264(composition(mode),path)
        cases[mode]=encoded_visual_gap_qa(path,structured_plan,expected_evidence=evidence)
    assert cases['full']['pass'],cases['full']
    assert not cases['white_gap']['pass'],cases['white_gap']
    assert not cases['missing_major']['pass'] and any(x['missing_or_collapsed_members'] for x in cases['missing_major']['source_survival_failures']),cases['missing_major']
    assert not cases['tiny_only']['pass'],cases['tiny_only']
    assert not cases['residual_missing']['pass'] and any(any(m['event_id']=='RESIDUAL_SUPPORT' for m in x['missing_or_collapsed_members']) for x in cases['residual_missing']['source_survival_failures']),cases['residual_missing']

print('V31_VISUAL_TIMELINE_COVERAGE_PASS')
