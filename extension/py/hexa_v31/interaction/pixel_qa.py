from __future__ import annotations
import cv2,numpy as np
from hexa_v31.preset_authority import preset

def _read(cap,index,total):
    index=max(0,min(total-1,int(index)));cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,frame=cap.read();return frame if ok else None

def _preset_change_signature(p:dict)->dict:
    a=p.get('start_norm') or [.5,.5];b=p.get('end_norm') or [.5,.5];displacement=((float(b[0])-float(a[0]))**2+(float(b[1])-float(a[1]))**2)**.5;scales=[]
    for row in p.get('scale_keyframes') or []:
        try:scales.append(float(row[1]))
        except Exception:pass
    opacities=[]
    for row in p.get('opacity_keyframes') or []:
        try:opacities.append(float(row[1]))
        except Exception:pass
    return {'displacement':displacement,'scale_change':(max(scales)-min(scales)) if scales else 0.0,'opacity_change':(max(opacities)-min(opacities)) if opacities else 0.0,'opacity_start':opacities[0] if opacities else 1.0,'opacity_end':opacities[-1] if opacities else 1.0}

def _roi(event,preset_name,width,height):
    p=preset(preset_name);family=str(p.get('family') or '');rect=event.get('planned_rect_norm') or [0,0,.18,.18];rw=max(.04,float(rect[2]));rh=max(.04,float(rect[3]));pad=.035
    if family in {'ENTRY_EXIT','WITHIN_FRAME'}:
        a=p.get('start_norm') or [.5,.5];b=p.get('end_norm') or [.5,.5];minx=min(float(a[0]),float(b[0]));maxx=max(float(a[0]),float(b[0]));miny=min(float(a[1]),float(b[1]));maxy=max(float(a[1]),float(b[1]))
    else:
        cx=float(rect[0])+float(rect[2])/2;cy=float(rect[1])+float(rect[3])/2;scales=[]
        for row in p.get('scale_keyframes') or []:
            try:scales.append(float(row[1]))
            except Exception:pass
        envelope=max([1.0]+scales);rw*=envelope;rh*=envelope;minx=maxx=cx;miny=maxy=cy
    x0=max(0,minx-rw/2-pad);y0=max(0,miny-rh/2-pad);x1=min(1,maxx+rw/2+pad);y1=min(1,maxy+rh/2+pad)
    return int(x0*width),int(y0*height),max(1,int(x1*width)),max(1,int(y1*height))

def _event_roi_at(event:dict,t:float,width:int,height:int,preset_name:str):
    """Return the actor ROI at the exact geometry rendered at ``t``.

    Encoded interaction QA must follow the same composition-state authority as the
    renderer. ``planned_rect_norm`` is only the authored/rest footprint; late
    composition states may legally relocate or scale the actor during the action.
    """
    from hexa_v31.render.preview import _event_state

    state=_event_state(event,float(t))
    if state is None:
        return _roi(event,preset_name,width,height),False
    center,scale,_opacity=state
    rect=event.get('planned_rect_norm') or [0,0,.18,.18]
    rw=max(.04,float(rect[2]))*max(.05,abs(float(scale)))
    rh=max(.04,float(rect[3]))*max(.05,abs(float(scale)))
    cx=float(center[0])/1920.0;cy=float(center[1])/1080.0;pad=.035
    x0=max(0.0,cx-rw/2-pad);y0=max(0.0,cy-rh/2-pad);x1=min(1.0,cx+rw/2+pad);y1=min(1.0,cy+rh/2+pad)
    return (int(x0*width),int(y0*height),max(1,int(x1*width)),max(1,int(y1*height))),True

def _union_roi(a,b,width,height):
    return (max(0,min(a[0],b[0])),max(0,min(a[1],b[1])),min(width,max(a[2],b[2])),min(height,max(a[3],b[3])))

def _crop(frame,roi):
    x0,y0,x1,y1=roi
    return frame[y0:y1,x0:x1]

def verify_encoded_interactions(video_path:str,motion_plan:dict,fps:float|None=None)->dict:
    engine=motion_plan.get('interaction_engine') or {};actions=list(engine.get('physical_actions') or []);actionable=int(engine.get('actionable_interaction_count') or 0);embodied=int(engine.get('embodied_interaction_count') or 0)
    if not actions:
        failures=[]
        if actionable>0:failures=[{'reason':'ZERO_ENCODED_INTERACTION_ACTIONS_WITH_ACTIONABLE_INTENTS','actionable_interaction_count':actionable,'embodied_interaction_count':embodied}]
        return {'schema':'HEXA_ENCODED_INTERACTION_PIXEL_QA_V3','version':'3.2_DIRECTIONAL_APPEARANCE_VISIBILITY','pass':not failures,'physical_action_count':0,'verified_action_count':0,'actionable_interaction_count':actionable,'embodied_interaction_count':embodied,'vacuous':actionable==0,'actions':[],'failures':failures}
    events={str(e.get('event_id')):e for e in motion_plan.get('events') or []};cap=cv2.VideoCapture(str(video_path));actual_fps=float(cap.get(cv2.CAP_PROP_FPS) or fps or motion_plan.get('fps') or 30);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0);width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0);height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0);rows=[];fail=[]
    if total<=0 or width<=0 or height<=0:
        cap.release();return {'schema':'HEXA_ENCODED_INTERACTION_PIXEL_QA_V3','version':'3.2_DIRECTIONAL_APPEARANCE_VISIBILITY','pass':False,'physical_action_count':len(actions),'verified_action_count':0,'actionable_interaction_count':actionable,'embodied_interaction_count':embodied,'vacuous':False,'actions':[],'failures':[{'reason':'VIDEO_DECODE_UNAVAILABLE'}]}
    for action in actions:
        event=events.get(str(action.get('event_id')));st=float(action.get('start_seconds',0));en=float(action.get('end_seconds',st))
        if not event or en<=st:
            row={'interaction_id':action.get('interaction_id'),'event_id':action.get('event_id'),'pass':False,'reason':'INVALID_ACTION_METADATA'};rows.append(row);fail.append(row);continue
        f0=int(round((st+min(.08,max(.02,(en-st)*.08)))*actual_fps));f1=int(round((en-min(.08,max(.02,(en-st)*.08)))*actual_fps));a=_read(cap,f0,total);b=_read(cap,f1,total)
        if a is None or b is None:
            row={'interaction_id':action.get('interaction_id'),'event_id':action.get('event_id'),'pass':False,'reason':'ACTION_FRAME_DECODE_FAILED'};rows.append(row);fail.append(row);continue
        t0=f0/actual_fps;t1=f1/actual_fps;preset_name=str(action['preset']);start_roi,start_state_ok=_event_roi_at(event,t0,width,height,preset_name);end_roi,end_state_ok=_event_roi_at(event,t1,width,height,preset_name);motion_roi=_union_roi(start_roi,end_roi,width,height);aa=_crop(a,motion_roi);bb=_crop(b,motion_roi);start_actor=_crop(a,start_roi);end_actor=_crop(b,end_roi);diff=cv2.absdiff(aa,bb);changed=np.max(diff,axis=2)>8;changed_pixels=int(np.count_nonzero(changed));changed_fraction=changed_pixels/max(1,changed.size);mae=float(np.mean(diff));p=preset(preset_name);sig=_preset_change_signature(p);nonwhite_a=int(np.count_nonzero(np.any(start_actor<248,axis=2)));nonwhite_b=int(np.count_nonzero(np.any(end_actor<248,axis=2)));authored_change=bool(sig['displacement']>=.01 or sig['scale_change']>=.01 or sig['opacity_change']>=.01);observed_change=bool(changed_pixels>=40 and (changed_fraction>=.0015 or mae>=.45));opacity_delta=sig['opacity_end']-sig['opacity_start']
        if opacity_delta>.05:visibility_ok=nonwhite_b>=20;visibility_contract='APPEARANCE_END_VISIBLE'
        elif opacity_delta<-.05:visibility_ok=nonwhite_a>=20;visibility_contract='DISAPPEARANCE_START_VISIBLE'
        else:visibility_ok=nonwhite_a>=20 and nonwhite_b>=20;visibility_contract='ACTOR_VISIBLE_BOTH_ENDPOINTS'
        ok=bool(authored_change and visibility_ok and observed_change)
        row={'interaction_id':action.get('interaction_id'),'event_id':action.get('event_id'),'phase':action.get('phase'),'preset':action.get('preset'),'preset_family':p.get('family'),'visibility_contract':visibility_contract,'expected_displacement_norm':round(sig['displacement'],6),'expected_scale_change':round(sig['scale_change'],6),'expected_opacity_change':round(sig['opacity_change'],6),'opacity_start':round(sig['opacity_start'],6),'opacity_end':round(sig['opacity_end'],6),'changed_pixels':changed_pixels,'changed_fraction':round(changed_fraction,6),'mean_abs_difference':round(mae,4),'start_nonwhite_pixels':nonwhite_a,'end_nonwhite_pixels':nonwhite_b,'roi_px':list(motion_roi),'start_roi_px':list(start_roi),'end_roi_px':list(end_roi),'start_state_geometry_resolved':bool(start_state_ok),'end_state_geometry_resolved':bool(end_state_ok),'pass':ok}
        if not ok:row['reason']='ENCODED_MOTION_BELOW_THRESHOLD_OR_ACTOR_VISIBILITY_CONTRACT_FAILED';fail.append(row)
        rows.append(row)
    cap.release();verified=sum(bool(x.get('pass')) for x in rows)
    return {'schema':'HEXA_ENCODED_INTERACTION_PIXEL_QA_V3','version':'3.2_DIRECTIONAL_APPEARANCE_VISIBILITY','pass':not fail,'physical_action_count':len(actions),'verified_action_count':verified,'actionable_interaction_count':actionable,'embodied_interaction_count':embodied,'vacuous':False,'actions':rows,'failures':fail}
