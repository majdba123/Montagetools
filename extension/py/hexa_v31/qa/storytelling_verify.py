from __future__ import annotations
import os, pathlib
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from hexa_v31.util import write_json


def _read_at(cap, seconds:float):
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0.0,float(seconds))*1000.0)
    ok,fr=cap.read()
    return fr if ok and fr is not None else None


def _roi(frame,bbox,extra_pad=0.0):
    if frame is None:return None
    h,w=frame.shape[:2]
    if not bbox or len(bbox)!=4:return frame
    x,y,bw,bh=map(float,bbox);pad=0.035+max(0.0,float(extra_pad))
    x0=max(0,int((x-pad)*w));y0=max(0,int((y-pad)*h));x1=min(w,int((x+bw+pad)*w));y1=min(h,int((y+bh+pad)*h))
    if x1-x0<8 or y1-y0<8:return frame
    return frame[y0:y1,x0:x1]


def verify_storytelling_render(video_path:str|os.PathLike,motion_plan:dict,out_json:str|os.PathLike|None=None)->dict:
    """Verify that V31's semantic story plan physically survives in the final MP4.

    V26 could report 0/0 story actions as PASS. V31 explicitly forbids that vacuous
    success: if the single semantic graph marks any scene story-eligible, that scene
    must own at least one planned story action and the final MP4 must visibly change
    inside the corresponding object ROI. Both staged introductions and safe stateful
    transfers count because both are meaningful temporal story states.
    """
    p=pathlib.Path(video_path);cap=cv2.VideoCapture(str(p))
    if not cap.isOpened():raise RuntimeError('Cannot open final MP4 for storytelling verification: '+str(p))
    scenes=motion_plan.get('scenes') or []
    eligible={str(s.get('scene_id')) for s in scenes if bool((s.get('semantic_object_graph') or {}).get('story_eligible'))}
    planned_by_scene={sid:0 for sid in eligible}
    rows=[]
    for e in motion_plan.get('events') or []:
        sid=str(e.get('scene_id'))
        actions=e.get('story_actions') or []
        if sid in planned_by_scene: planned_by_scene[sid]+=len(actions)
        for i,b in enumerate(actions):
            bs=float(b.get('start_seconds',0));be=float(b.get('end_seconds',bs));bp=(bs+be)/2.0
            if be-bs<0.12:
                rows.append({'event_id':e.get('event_id'),'scene_id':sid,'beat_index':i,'kind':b.get('kind'),'source':b.get('source'),'pass':False,'reason':'STORY_BEAT_TOO_SHORT'})
                continue
            eps=min(0.04,max(0.01,(be-bs)*0.08));t0=min(bp-0.01,bs+eps);t1=max(bp+0.01,be-eps)
            extra=max(abs(float(b.get('dx_norm',0.0))),abs(float(b.get('dy_norm',0.0))))+0.02
            f0=_roi(_read_at(cap,t0),e.get('bbox_norm'),extra);fp=_roi(_read_at(cap,bp),e.get('bbox_norm'),extra);f1=_roi(_read_at(cap,t1),e.get('bbox_norm'),extra)
            if f0 is None or fp is None or f1 is None or f0.shape!=fp.shape or f1.shape!=fp.shape:
                rows.append({'event_id':e.get('event_id'),'scene_id':sid,'beat_index':i,'kind':b.get('kind'),'source':b.get('source'),'pass':False,'reason':'FRAME_READ_OR_ROI_MISMATCH'});continue
            g0=cv2.cvtColor(f0,cv2.COLOR_BGR2GRAY);gp=cv2.cvtColor(fp,cv2.COLOR_BGR2GRAY);g1=cv2.cvtColor(f1,cv2.COLOR_BGR2GRAY)
            d0=cv2.absdiff(g0,gp);d1=cv2.absdiff(gp,g1)
            mean_diff=max(float(np.mean(d0)),float(np.mean(d1)))
            changed=max(float(np.mean(d0>=3)*100.0),float(np.mean(d1>=3)*100.0))
            ok=bool(mean_diff>=0.12 or changed>=0.45)
            rows.append({'event_id':e.get('event_id'),'scene_id':sid,'beat_index':i,'kind':b.get('kind'),'render_mode':b.get('render_mode'),'source':b.get('source'),'mean_luma_diff':round(mean_diff,4),'changed_pixels_percent':round(changed,4),'pass':ok})
    cap.release()
    zero_story_scenes=sorted(sid for sid,n in planned_by_scene.items() if n<=0)
    planned=len(rows);passed=sum(1 for r in rows if r.get('pass'));ratio=0.0 if planned==0 and eligible else (1.0 if planned==0 else passed/planned)
    pass_render=bool(not zero_story_scenes and (not eligible or planned>0) and (planned==0 or ratio>=0.88))
    result={
        'schema':'HEXA_V31_STORY_ACTION_RENDER_VERIFICATION','version':'2.0','video':str(p),
        'story_eligible_scene_count':len(eligible),'zero_story_eligible_scenes':zero_story_scenes,
        'planned_story_actions':planned,'verified_story_actions':passed,'planned_story_beats':planned,'verified_story_beats':passed,
        'verified_ratio':round(ratio,4),'pass':pass_render,'rows':rows,
        'policy':'ELIGIBLE_SCENES_REQUIRE_NONVACUOUS_PHYSICAL_STORY_CHANGE','vacuous_zero_over_zero_pass_forbidden':True,
        'reference_metric_autotuning':False
    }
    if out_json:write_json(out_json,result)
    return result
