from __future__ import annotations
import os, pathlib, math
import cv2
cv2.setNumThreads(1)
try:cv2.ocl.setUseOpenCL(False)
except Exception:pass
import numpy as np
from hexa_v31.util import write_json


def _read(cap,t):
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0.0,float(t))*1000.0);ok,fr=cap.read();return fr if ok else None


def _roi(fr,b,extra=0.08):
    if fr is None:return None
    h,w=fr.shape[:2];x,y,bw,bh=map(float,b or [0,0,1,1]);x0=max(0,int((x-extra)*w));y0=max(0,int((y-extra)*h));x1=min(w,int((x+bw+extra)*w));y1=min(h,int((y+bh+extra)*h));return fr[y0:y1,x0:x1]


def _action_union_bbox(fr,b,a):
    # Verify a transfer in a crop that contains both source and destination. Using only the
    # source bbox created false negatives when a professional full-zone travel left its origin.
    if fr is None:return b
    h,w=fr.shape[:2];x,y,bw,bh=map(float,b or [0,0,1,1])
    dx=float(a.get('dx_norm',0.0));dy=float(a.get('dy_norm',0.0))
    if abs(dx)<1e-9 and abs(dy)<1e-9:
        dx=float(a.get('dx_px',0.0))/max(1.0,w);dy=float(a.get('dy_px',0.0))/max(1.0,h)
    x2=x+dx;y2=y+dy
    ux=min(x,x2);uy=min(y,y2);ur=max(x+bw,x2+bw);ub=max(y+bh,y2+bh)
    return [max(0.0,ux),max(0.0,uy),min(1.0,ur)-max(0.0,ux),min(1.0,ub)-max(0.0,uy)]


def _fg_centroid(fr):
    if fr is None or fr.size==0:return None,0.0
    mask=np.min(fr,axis=2)<246;yy,xx=np.where(mask)
    if len(xx)<16:return None,float(mask.mean())
    return (float(xx.mean()),float(yy.mean())),float(mask.mean())


def _frame_change(a,b):
    if a is None or b is None:return 0.0,0.0
    aa=cv2.cvtColor(a,cv2.COLOR_BGR2GRAY);bb=cv2.cvtColor(b,cv2.COLOR_BGR2GRAY)
    d=cv2.absdiff(aa,bb)
    return float(np.mean(d)),float(np.mean(d>=6))


def verify_physical_acting(video_path:str|os.PathLike,motion_plan:dict,out_json:str|os.PathLike|None=None)->dict:
    """Physically verify V31 relationship choreography in the encoded MP4.

    P2 only inspected legacy ``story_actions``. V31's authoritative relationship moves live
    in ``preset_actions`` and use the user's supplied WITHIN_FRAME presets.  A zero-action
    plan is *not* awarded a free storytelling score by the reference critic.  When actions
    exist, this verifier requires a measurable pixel change across their physical interval.
    """
    p=pathlib.Path(video_path);cap=cv2.VideoCapture(str(p))
    if not cap.isOpened():raise RuntimeError('Cannot open final MP4 for acting verification')
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.0);duration=float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)/max(1e-6,fps);rows=[]
    p3=('V31_0_1_UNIVERSAL_CONSTRAINT_STORY_DIRECTOR' in str(motion_plan.get('motion_dna_version') or '') or 'USER_PRESET' in str(motion_plan.get('motion_dna_version') or ''))
    for e in motion_plan.get('events') or []:
        if e.get('suppressed_by_card_density'):continue
        if p3:
            actions=e.get('preset_actions') or []
            for a in actions:
                st=float(a.get('start_seconds',0));en=st+float(a.get('duration_seconds',0))
                if en-st<1.0/fps:continue
                pre=_read(cap,max(0.0,st-1.0/fps));mid=_read(cap,(st+en)/2.0);post=_read(cap,min(duration,max(st,en+1.0/fps)))
                d01,p01=_frame_change(pre,mid);d12,p12=_frame_change(mid,post);d02,p02=_frame_change(pre,post)
                # Exact supplied within-frame presets produce a large object travel.  Requiring
                # both mean energy and changed-pixel area prevents a simultaneous tiny blink
                # elsewhere in the frame from falsely certifying the action.
                energy=max(d01,d12,d02);coverage=max(p01,p12,p02)
                ok=bool(energy>=0.55 and coverage>=0.0025)
                rows.append({'event_id':e.get('event_id'),'scene_id':e.get('scene_id'),'visual_card_id':e.get('visual_card_id'),'kind':str(a.get('action_type') or 'USER_PRESET_ACTION'),'preset_name':a.get('name'),'target_semantic_unit_id':a.get('target_semantic_unit_id'),'relationship_evidence':a.get('relationship_evidence'),'start_seconds':round(st,6),'end_seconds':round(en,6),'mean_frame_change':round(energy,5),'changed_pixel_ratio':round(coverage,6),'pass':ok})
        else:
            bbox=e.get('bbox_norm') or [0,0,1,1]
            for a in e.get('story_actions') or []:
                if str(a.get('render_mode') or '')!='MOTION':continue
                kind=str(a.get('kind') or '');st=float(a.get('start_seconds',0));en=float(a.get('end_seconds',st));
                if en-st<1.0/fps:continue
                probe0=_read(cap,max(0,st-1/fps));probe_bbox=_action_union_bbox(probe0,bbox,a)
                f0=_roi(probe0,probe_bbox);fm=_roi(_read(cap,(st+en)/2),probe_bbox);f1=_roi(_read(cap,min(en+1/fps,float(e.get('end_seconds',en)))),probe_bbox)
                c0,o0=_fg_centroid(f0);cm,om=_fg_centroid(fm);c1,o1=_fg_centroid(f1)
                moved=0.0
                if c0 and c1:moved=math.hypot(c1[0]-c0[0],c1[1]-c0[1])
                expected=math.hypot(float(a.get('dx_px',0)),float(a.get('dy_px',0)))
                if kind=='POSITION_TRANSFER':ok=bool(moved>=max(5.0,min(20.0,expected*0.12)))
                else:ok=bool(abs(o1-o0)>=0.004 or (c0 and c1 and moved>=4.0))
                rows.append({'event_id':e.get('event_id'),'scene_id':e.get('scene_id'),'kind':kind,'start_seconds':st,'end_seconds':en,'expected_travel_px':round(expected,2),'observed_centroid_travel_px':round(moved,2),'occupancy_delta':round(o1-o0,5),'pass':ok})
    cap.release();planned=len(rows);passed=sum(1 for r in rows if r['pass']);ratio=0.0 if planned==0 else passed/planned
    eligible=int((motion_plan.get('budget_summary') or {}).get('story_eligible_scene_count',0)) if p3 else sum(1 for s in motion_plan.get('scenes') or [] if (s.get('semantic_object_graph') or {}).get('story_eligible'))
    result={'schema':'HEXA_PHYSICAL_ACTING_VERIFICATION_V31','version':'31.0.9' if p3 else '1.0','video':str(p),'story_eligible_scene_count':eligible,'planned_physical_actions':planned,'verified_physical_actions':passed,'verified_ratio':round(ratio,4),'pass':bool(planned==0 or ratio>=0.88),'rows':rows,'note':'V31 verifies physically encoded USER_PRESET within-frame actions, including layout choreography and explicit semantic relationships. Zero planned actions receive no free reference-score component.','vacuous_semantic_story_score_forbidden':True}
    if out_json:write_json(out_json,result)
    return result
