from __future__ import annotations
import math, os, pathlib, subprocess
from typing import Any
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from PIL import Image
from hexa_v31.util import ensure_dir
from hexa_v31.typography import render_text_rgba
from hexa_v31.motion_solver import min_jerk5, s_curve7
from hexa_v31.preset_authority import preset as _preset_def, progress as _preset_progress, scale as _preset_scale, opacity as _preset_opacity

class PreviewError(RuntimeError): pass


def _alpha_blend_top_left(canvas:np.ndarray, layer:np.ndarray, x:int, y:int, opacity:float=1.0, scale:float=1.0):
    if opacity<=0.001:return
    img=layer
    if abs(scale-1.0)>0.002:
        nw=max(1,int(round(img.shape[1]*scale)));nh=max(1,int(round(img.shape[0]*scale)))
        img=cv2.resize(img,(nw,nh),interpolation=cv2.INTER_CUBIC)
    h,w=img.shape[:2]
    x=int(round(x-(w-layer.shape[1])/2));y=int(round(y-(h-layer.shape[0])/2))
    x0=max(0,x);y0=max(0,y);x1=min(canvas.shape[1],x+w);y1=min(canvas.shape[0],y+h)
    if x1<=x0 or y1<=y0:return
    lx0=x0-x;ly0=y0-y;lx1=lx0+(x1-x0);ly1=ly0+(y1-y0)
    crop=img[ly0:ly1,lx0:lx1]
    a=(crop[:,:,3].astype(np.float32)/255.0)*max(0.0,min(1.0,float(opacity)));aa=a[...,None]
    dst=canvas[y0:y1,x0:x1].astype(np.float32);src=crop[:,:,:3].astype(np.float32)
    canvas[y0:y1,x0:x1]=(src*aa+dst*(1.0-aa)).astype(np.uint8)

def _text_state(e:dict,t:float):
    st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st))
    if t<st or t>en:return None
    fi=max(0.04,float(e.get('fade_in_seconds',0.18)));fo=max(0.04,float(e.get('fade_out_seconds',0.16)))
    if t<st+fi: opacity=_ease((t-st)/fi)
    elif t>en-fo: opacity=1.0-_ease((t-(en-fo))/fo)
    else: opacity=1.0
    q=max(0.0,min(1.0,(t-st)/max(0.001,fi+0.16)))
    s0=float(e.get('pop_scale_from',1.0));sp=float(e.get('pop_scale_peak',1.0));se=float(e.get('pop_scale_end',1.0))
    if q<0.55: scale=_lerp(s0,sp,_ease(q/0.55))
    else: scale=_lerp(sp,se,_ease((q-0.55)/0.45))
    slide_d=max(0.40,float(e.get('slide_duration_seconds',0.42)));slide_q=1.0-_ease_position(min(1.0,max(0.0,(t-st)/max(0.001,slide_d))))
    dx=float(e.get('slide_dx_norm',0.0))*slide_q;dy=float(e.get('slide_dy_norm',0.0))*slide_q
    return opacity,scale,dx,dy

def _ease(t:float)->float:
    # Minimum-jerk ease for opacity/scale/text. It is smoother than cubic smoothstep
    # while retaining the reference's readable mid-motion energy.
    return min_jerk5(t)

def _ease_position(t:float)->float:
    # V31 position authority: seventh-order S-curve with zero velocity, acceleration
    # and jerk at both endpoints. This is the pre-rendered equivalent of the locked
    # Premiere Bezier/Ease In-Out contract and removes V28's stop/start shocks.
    return s_curve7(t)

def _lerp(a,b,t):return a+(b-a)*t

def _load_rgba(path:str):return np.array(Image.open(path).convert('RGBA'))

def _prescale(img:np.ndarray, base_scale_percent:float, out_w:int)->np.ndarray:
    # Premiere plan coordinates are based on 1920x1080. Apply the same normalized fit once.
    factor=(float(base_scale_percent)/100.0)*(out_w/1920.0)
    nw=max(1,int(round(img.shape[1]*factor))); nh=max(1,int(round(img.shape[0]*factor)))
    return cv2.resize(img,(nw,nh),interpolation=cv2.INTER_AREA if factor<1 else cv2.INTER_CUBIC)

def _apply(canvas:np.ndarray, layer:np.ndarray, center_px:tuple[float,float], opacity:float, motion_scale:float, out_w:int,out_h:int):
    if opacity<=0.001:return
    img=layer
    if abs(motion_scale-1.0)>0.002:
        nw=max(1,int(round(img.shape[1]*motion_scale)));nh=max(1,int(round(img.shape[0]*motion_scale)))
        img=cv2.resize(img,(nw,nh),interpolation=cv2.INTER_CUBIC)
    nh,nw=img.shape[:2]
    cx=center_px[0]*(out_w/1920.0); cy=center_px[1]*(out_h/1080.0)
    x0=int(round(cx-nw/2)); y0=int(round(cy-nh/2)); x1=x0+nw; y1=y0+nh
    ox0=max(0,x0);oy0=max(0,y0);ox1=min(out_w,x1);oy1=min(out_h,y1)
    if ox1<=ox0 or oy1<=oy0:return
    lx0=ox0-x0;ly0=oy0-y0;lx1=lx0+(ox1-ox0);ly1=ly0+(oy1-oy0)
    crop=img[ly0:ly1,lx0:lx1];op=max(0.0,min(1.0,float(opacity)))
    dst=canvas[oy0:oy1,ox0:ox1].astype(np.float32)
    # V31.0.25 source-backed contact matte: pale vector art on a white stage can
    # measure as an empty/white trough during otherwise valid handoffs.  This is
    # not a new semantic object and not filler; it is a soft matte derived only
    # from the active source alpha, following the same position/scale/lifecycle.
    if op>0.015:
        mask=crop[:,:,3].astype(np.float32)/255.0
        sh=cv2.GaussianBlur(mask,(0,0),sigmaX=max(1.2,min(7.0,min(crop.shape[:2])*0.018)))
        sh=np.clip(sh*0.30*max(op,0.34),0.0,0.32)[...,None]
        shade=np.array([188.0,202.0,212.0],dtype=np.float32)
        dst=shade*sh+dst*(1.0-sh)
    a=(crop[:,:,3].astype(np.float32)/255.0)*op;aa=a[...,None]
    src=crop[:,:,:3].astype(np.float32)
    canvas[oy0:oy1,ox0:ox1]=(src*aa+dst*(1.0-aa)).astype(np.uint8)



def _preset_event_state(e:dict,t:float):
    """Execute the supplied Premiere preset vocabulary without adding motion.

    V31 supports two coordinate contracts.  Legacy full-canvas layers use relative
    translation around the authored composition.  Production V31 object crops use
    ABSOLUTE_OBJECT_CENTER: the preset Position values are literal Program Monitor
    center coordinates, which matches how the supplied .prfpset operates on a normal
    isolated Premiere clip.  This removes P2/V31-prototype overshoot from translating a
    full 1920x1080 transparent canvas instead of the actual icon.
    """
    rest=e.get('object_rest_position_px') or e.get('end_position_px') or e.get('rest_position_px') or [960.0,540.0]
    rw,rh=float(e.get('sequence_width') or 1920.0),float(e.get('sequence_height') or 1080.0)
    absolute=str(e.get('preset_coordinate_mode') or '').upper()=='ABSOLUTE_OBJECT_CENTER'
    pos=[float(rest[0]),float(rest[1])];sc=1.0;op=1.0
    st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st))
    if t<st-1e-6 or t>=en-1e-6:return None

    pe=e.get('preset_entry')
    if pe:
        name=str(pe.get('name')); ps=float(pe.get('start_seconds',st)); pd=float(pe.get('duration_seconds') or _preset_def(name).get('duration_seconds') or 0.8)
        q=max(0.0,min(1.0,(t-ps)/max(1e-6,pd)));d=_preset_def(name);fam=d.get('family')
        if fam in {'ENTRY_EXIT','WITHIN_FRAME'}:
            a=d.get('start_norm') or [0.5,0.5];b=d.get('end_norm') or [0.5,0.5];pg=_preset_progress(name,q)
            if absolute:
                pos[0]=_lerp(float(a[0])*rw,float(b[0])*rw,pg);pos[1]=_lerp(float(a[1])*rh,float(b[1])*rh,pg)
            else:
                dx=((float(a[0])-float(b[0]))*(1.0-pg))*rw;dy=((float(a[1])-float(b[1]))*(1.0-pg))*rh
                pos[0]+=dx;pos[1]+=dy
        elif fam=='APPEARANCE':
            sc*=_preset_scale(name,q);op*=_preset_opacity(name,q)

    # Within-frame actions are stateful.  V31 only schedules one when the semantic
    # relation is explicit and the previous state physically matches the preset start.
    # The final preset position persists until the exit/disappearance preset begins.
    held_abs=None;accx=accy=0.0
    for a in sorted((e.get('preset_actions') or []),key=lambda x:float(x.get('start_seconds',0))):
        name=str(a.get('name')); ast=float(a.get('start_seconds',0)); ad=float(a.get('duration_seconds') or _preset_def(name).get('duration_seconds') or 0.8)
        d=_preset_def(name);fam=d.get('family')
        if t<ast:continue
        if fam=='WITHIN_FRAME':
            aa=d.get('start_norm') or [0.5,0.5];bb=d.get('end_norm') or [0.5,0.5]
            if absolute:
                if t>=ast+ad:held_abs=[float(bb[0])*rw,float(bb[1])*rh]
                else:
                    q=max(0.0,min(1.0,(t-ast)/max(1e-6,ad)));pg=_preset_progress(name,q)
                    held_abs=[_lerp(float(aa[0])*rw,float(bb[0])*rw,pg),_lerp(float(aa[1])*rh,float(bb[1])*rh,pg)]
            else:
                final_dx=(float(bb[0])-float(aa[0]))*rw;final_dy=(float(bb[1])-float(aa[1]))*rh
                if t>=ast+ad:accx+=final_dx;accy+=final_dy
                else:
                    q=max(0.0,min(1.0,(t-ast)/max(1e-6,ad)));pg=_preset_progress(name,q);accx+=final_dx*pg;accy+=final_dy*pg
        elif fam=='APPEARANCE' and ast<=t<=ast+ad:
            q=max(0.0,min(1.0,(t-ast)/max(1e-6,ad)));sc*=_preset_scale(name,q);op*=_preset_opacity(name,q)
    if absolute and held_abs is not None:pos=held_abs
    else:pos[0]+=accx;pos[1]+=accy

    px=e.get('preset_exit')
    if px:
        name=str(px.get('name')); xs=float(px.get('start_seconds',en)); xd=float(px.get('duration_seconds') or _preset_def(name).get('duration_seconds') or 0.6)
        if t>=xs:
            q=max(0.0,min(1.0,(t-xs)/max(1e-6,xd)));d=_preset_def(name);fam=d.get('family')
            if fam=='ENTRY_EXIT':
                aa=d.get('start_norm') or [0.5,0.5];bb=d.get('end_norm') or [0.5,0.5];pg=_preset_progress(name,q)
                if absolute:
                    pos=[_lerp(float(aa[0])*rw,float(bb[0])*rw,pg),_lerp(float(aa[1])*rh,float(bb[1])*rh,pg)]
                else:
                    pos[0]+=((float(bb[0])-float(aa[0]))*pg)*rw;pos[1]+=((float(bb[1])-float(aa[1]))*pg)*rh
            elif fam=='DISAPPEARANCE':
                dd=d.get('position_delta_norm') or [0.0,0.0]
                # Disappearance operates from the current held object center, matching
                # the supplied visual sample, and is legal for both primary/secondary.
                pos[0]+=float(dd[0])*rw*q;pos[1]+=float(dd[1])*rh*q;sc*=_preset_scale(name,q);op*=_preset_opacity(name,q)
    return (pos[0],pos[1]),sc,op

def _event_state(e:dict,t:float):
    physical_start=float(e.get('physical_start_seconds',e.get('start_seconds',0)))
    physical_end=float(e.get('physical_end_seconds',e.get('end_seconds',physical_start)))
    # Physical carriers use the same half-open [start,end) lifetime as QA.\n    if t<physical_start-1e-6 or t>=physical_end-1e-6:return None
    if e.get('render_mode')=='RESIDUAL_SUPPORT':
        rest=e.get('object_rest_position_px') or e.get('end_position_px') or e.get('rest_position_px') or [960.0,540.0]
        return (float(rest[0]),float(rest[1])),1.0,1.0
    motion_start=float(e.get('motion_start_seconds',e.get('start_seconds',physical_start)))
    motion_end=float(e.get('motion_end_seconds',e.get('end_seconds',physical_end)))
    if t>motion_end+1e-6:
        exit_start=float((e.get('preset_exit') or {}).get('start_seconds',motion_end))
        t=max(motion_start,min(motion_end-1e-6,exit_start-1e-6))
    if e.get('preset_entry') or e.get('preset_exit') or e.get('preset_actions'):
        return _preset_event_state(e,t)
    st=float(e.get('start_seconds',0)); settle=float(e.get('settle_seconds',st)); end=float(e.get('end_seconds',st))
    if t<st-1e-6 or t>=end-1e-6:return None
    progress=1.0 if settle<=st else _ease((t-st)/(settle-st))
    sp=e.get('start_position_px') or [960,540];ep=e.get('end_position_px') or [960,540]
    if e.get('position_animated'):
        sx0,sy0=float(sp[0]),float(sp[1]);ex0,ey0=float(ep[0]),float(ep[1])
        q=_ease_position((t-st)/max(1e-6,settle-st)) if settle>st else 1.0
        pos=(_lerp(sx0,ex0,q),_lerp(sy0,ey0,q))
    else:pos=(float(ep[0]),float(ep[1]))
    scale=1.0;opacity=1.0;app=e.get('appearance_method')
    if app=='SCALE_POP':
        peak=float(e.get('scale_pop_peak',1.05)); start_scale=float(e.get('scale_pop_from',max(0.95,1.0-(peak-1.0)*0.65)))
        if progress<0.55:scale=_lerp(start_scale,peak,_ease(progress/0.55))
        else:scale=_lerp(peak,1.0,_ease((progress-0.55)/0.45))
        opacity=progress
    elif app=='OPACITY_FADE_IN':
        opacity=progress
    elif app=='BOUNDARY_CARRY_IN':
        # V31 carry-in clips enter already visible; the boundary director supplies only minimal punctuation.
        opacity=1.0

    # Subtle continuous motion prevents long static plateaus while preserving Worker composition.
    if e.get('continuous_drift'):
        q=max(0.0,min(1.0,(t-st)/max(0.001,end-st)))
        q=_ease(q)
        dx=float(e.get('drift_dx_px',0.0));dy=float(e.get('drift_dy_px',0.0))
        pos=(pos[0]+dx*q,pos[1]+dy*q)
        scale*= _lerp(float(e.get('drift_scale_from',1.0)),float(e.get('drift_scale_to',1.0)),q)

    # Hard-rule continuous still-image motion: only 110->100 and only when the
    # planner certified a >=3 second single-image opportunity.
    if e.get('continuous_image_scale'):
        cs=float(e.get('continuous_scale_scene_start_seconds',st)); ce=float(e.get('continuous_scale_scene_end_seconds',end))
        if ce-cs>=float(e.get('continuous_scale_min_seconds',3.0)):
            q=_ease_position((t-cs)/max(1e-6,ce-cs))
            scale*=_lerp(float(e.get('continuous_scale_from',1.10)),float(e.get('continuous_scale_to',1.0)),q)

    # Purposeful semantic focus beats: one or two short emphasis pulses tied to the beat.
    for fb in (e.get('focus_beats') or []):
        fs=float(fb.get('start_seconds',0));fp=float(fb.get('peak_seconds',fs));fe=float(fb.get('end_seconds',fp))
        if fs<=t<=fe and fe>fs:
            if t<=fp and fp>fs:q=_ease((t-fs)/(fp-fs))
            elif fe>fp:q=1.0-_ease((t-fp)/(fe-fp))
            else:q=0.0
            scale*=1.0+(float(fb.get('scale_peak',1.0))-1.0)*q
            pos=(pos[0]+float(fb.get('dx_px',0.0))*q,pos[1]+float(fb.get('dy_px',0.0))*q)

    # V31 stateful object lifecycle. Persistent actions accumulate their final
    # displacement after completion, so a source can travel toward a target and
    # remain there while the target responds. Transient actions use an envelope.
    persistent_dx=persistent_dy=0.0
    for sa in sorted((e.get('story_actions') or []),key=lambda x:float(x.get('start_seconds',0))):
        bs=float(sa.get('start_seconds',0));be=float(sa.get('end_seconds',bs));hold=bool(sa.get('hold_after'))
        dx=float(sa.get('dx_px',0.0));dy=float(sa.get('dy_px',0.0));arc=float(sa.get('arc_px',0.0))
        sf=float(sa.get('scale_from',1.0));spk=float(sa.get('scale_peak',1.0));sen=float(sa.get('scale_end',1.0))
        of=float(sa.get('opacity_from',1.0));opk=float(sa.get('opacity_peak',1.0));oen=float(sa.get('opacity_end',1.0))
        if t>=be and hold:
            persistent_dx+=dx;persistent_dy+=dy
            scale*=sen;opacity*=oen
            continue
        if not (bs<=t<=be) or be<=bs:continue
        q=_ease_position((t-bs)/(be-bs))
        if hold:
            # Stateful travel: interpolate once and keep the final state. A small
            # sine arc adds organic motion without changing the semantic endpoint.
            pos=(pos[0]+persistent_dx+dx*q,pos[1]+persistent_dy+dy*q-math.sin(math.pi*q)*arc)
            if q<0.55:scale*=_lerp(sf,spk,_ease(q/0.55))
            else:scale*=_lerp(spk,sen,_ease((q-0.55)/0.45))
            opacity*=_lerp(of,oen,q)
            persistent_dx=persistent_dy=0.0
        else:
            env=_ease(q/0.5) if q<0.5 else 1.0-_ease((q-0.5)/0.5)
            pos=(pos[0]+persistent_dx+dx*env,pos[1]+persistent_dy+dy*env-math.sin(math.pi*q)*arc)
            scale*=1.0+(spk-1.0)*env
            opacity*=1.0+(opk-1.0)*env
    if persistent_dx or persistent_dy:
        pos=(pos[0]+persistent_dx,pos[1]+persistent_dy)

    # Legacy V24 story beats remain readable for old caches, but V31 plans do not emit them.
    for sb in (e.get('story_beats') or []):
        bs=float(sb.get('start_seconds',0));bp=float(sb.get('peak_seconds',bs));be=float(sb.get('end_seconds',bp))
        if bs<=t<=be and be>bs:
            if t<=bp and bp>bs:q=_ease((t-bs)/(bp-bs))
            elif be>bp:q=1.0-_ease((t-bp)/(be-bp))
            else:q=0.0
            dx=float(sb.get('dx_px',0.0));dy=float(sb.get('dy_px',0.0));peak=float(sb.get('scale_peak',1.0))
            pos=(pos[0]+dx*q,pos[1]+dy*q);scale*=1.0+(peak-1.0)*q

    # Legacy V21 micro emphasis remains accepted for cache/backward compatibility.
    if e.get('micro_emphasis'):
        ms=float(e.get('micro_start_seconds',0));mm=float(e.get('micro_mid_seconds',0));me=float(e.get('micro_end_seconds',0));mp=e.get('micro_position_px') or ep
        if ms<=t<mm and mm>ms:
            q=_ease((t-ms)/(mm-ms));pos=(_lerp(float(ep[0]),float(mp[0]),q),_lerp(float(ep[1]),float(mp[1]),q))
        elif mm<=t<=me and me>mm:
            q=_ease((t-mm)/(me-mm));pos=(_lerp(float(mp[0]),float(ep[0]),q),_lerp(float(mp[1]),float(ep[1]),q))
    xs=float(e.get('exit_start_seconds',end));xe=float(e.get('exit_end_seconds',end))
    if t>=xs and xe>xs:
        q=_ease_position((t-xs)/(xe-xs));method=e.get('disappearance_method')
        if method=='OPACITY_FADE_OUT':opacity*=1.0-q
        elif method=='POSITION_EXIT':
            xp=e.get('exit_position_px') or ep;pos=(_lerp(pos[0],float(xp[0]),q),_lerp(pos[1],float(xp[1]),q))
        # HOLD_TO_BOUNDARY intentionally does nothing.
    return pos,scale,opacity

def render_preview(edit_map:dict, motion_plan:dict, vision_results:list[dict], audio_path:str|os.PathLike|None, out_dir:str|os.PathLike, width:int=426,height:int=240,fps:float=30.0,logger=None,text_plan:dict|None=None)->dict:
    out=ensure_dir(out_dir);silent=pathlib.Path(out)/'HEXA_V31_REFERENCE_QA_PREVIEW_SILENT.mp4';final=pathlib.Path(out)/'HEXA_V31_REFERENCE_QA_PREVIEW.mp4'
    vis={v['scene_id']:v for v in vision_results};scene_rows=motion_plan.get('scenes') or []
    duration=max((float(s['end_seconds']) for s in scene_rows),default=0.0);total=max(1,int(math.ceil(duration*fps)))
    # Pre-scale every physical layer once. At 426x240 this stays small and is much faster than resizing high-res layers per frame.
    runtime=[]
    for e in edit_map.get('events',[]):
        img=_prescale(_load_rgba(e['source_path']),float(e.get('base_fit_scale_percent',100)),width)
        typ=e.get('semantic_type') or e.get('kind') or '';z=4 if typ in ('MAIN_CHARACTER','SECONDARY_CHARACTER') or e.get('kind') in ('MAIN_NARRATOR','SECONDARY_CHARACTER') else (3 if e.get('semantic_role')=='PRIMARY' else 2)
        runtime.append({'e':e,'img':img,'sf':max(0,int(math.floor(float(e.get('start_seconds',0))*fps))),'ef':min(total-1,int(math.ceil(float(e.get('end_seconds',0))*fps))),'z':z})
    starts=[[] for _ in range(total+1)];ends=[[] for _ in range(total+1)]
    for i,r in enumerate(runtime):
        starts[r['sf']].append(i)
        if r['ef']+1<=total:ends[r['ef']+1].append(i)
    text_runtime=[]
    for te in ((text_plan or {}).get('events') or []):
        ti=np.array(render_text_rgba(te,width,height).convert('RGBA'))
        text_runtime.append((te,ti))
    fourcc=cv2.VideoWriter_fourcc(*'mp4v');writer=cv2.VideoWriter(str(silent),fourcc,fps,(width,height))
    if not writer.isOpened():raise PreviewError('OpenCV preview VideoWriter failed')
    active=set();scene_idx=0
    try:
        for fi in range(total):
            for i in ends[fi]:active.discard(i)
            for i in starts[fi]:active.add(i)
            t=fi/fps
            while scene_idx+1<len(scene_rows) and t>=float(scene_rows[scene_idx]['end_seconds'])-1e-9:scene_idx+=1
            sid=scene_rows[scene_idx]['scene_id'] if scene_rows else None
            # V20 runtime stage is canonical white. Source background tint is used only for
            # reconstruction diagnostics; it must not drift into the actual montage stage.
            bg=[255,255,255]
            canvas=np.empty((height,width,3),dtype=np.uint8);canvas[:]=np.array(bg,dtype=np.uint8)
            for i in sorted(active,key=lambda k:runtime[k]['z']):
                r=runtime[i];st=_event_state(r['e'],t)
                if st:
                    pos,sc,op=st;_apply(canvas,r['img'],pos,op,sc,width,height)
            for te,ti in text_runtime:
                ts=_text_state(te,t)
                if ts:
                    op,sc,dx,dy=ts;x=int(round((float(te.get('x_norm',0.1))+dx)*width));y=int(round((float(te.get('y_norm',0.08))+dy)*height))
                    _alpha_blend_top_left(canvas,ti,x,y,op,sc)
            writer.write(cv2.cvtColor(canvas,cv2.COLOR_RGB2BGR))
            if logger and fi and fi%(int(fps)*10)==0:logger.log('INFO','REFERENCE_PREVIEW_PROGRESS',seconds=round(t,1),duration_seconds=round(duration,1))
    finally:writer.release()
    if audio_path:
        ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg';cmd=[ff,'-y','-v','error','-i',str(silent),'-i',str(audio_path),'-c:v','copy','-c:a','aac','-b:a','160k','-shortest',str(final)]
        cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if cp.returncode!=0:
            final=silent
            if logger:logger.log('WARNING','REFERENCE_PREVIEW_AUDIO_MUX_FAIL',detail=cp.stderr[-1000:])
    else:final=silent
    if logger:logger.log('PASS','REFERENCE_PREVIEW_RENDERED',path=str(final),duration_seconds=round(duration,3),frames=total,resolution=f'{width}x{height}')
    return {'preview':str(final),'silent_preview':str(silent),'duration_seconds':duration,'frame_count':total,'fps':fps,'width':width,'height':height}



def render_production_mp4(edit_map:dict, motion_plan:dict, vision_results:list[dict], audio_path:str|os.PathLike, output_path:str|os.PathLike, width:int=1920, height:int=1080, fps:float=30.0, logger=None)->dict:
    """Render a motion plan as a full-resolution H.264 MP4.

    This is a deterministic production deliverable written to Documents before the
    Premiere physical handoff. Premiere remains the editable timeline authority; the
    MP4 gives the user a stable, immediately reviewable build artifact every run.
    """
    output_path=pathlib.Path(output_path); output_path.parent.mkdir(parents=True,exist_ok=True)
    ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg'
    scene_rows=motion_plan.get('scenes') or []
    duration=max((float(x['end_seconds']) for x in scene_rows),default=0.0); total=max(1,int(math.ceil(duration*fps)))
    runtime=[]
    for e in edit_map.get('events',[]):
        img=_prescale(_load_rgba(e['source_path']),float(e.get('base_fit_scale_percent',100)),width)
        typ=e.get('semantic_type') or e.get('kind') or '';z=4 if typ in ('MAIN_CHARACTER','SECONDARY_CHARACTER') or e.get('kind') in ('MAIN_NARRATOR','SECONDARY_CHARACTER') else (3 if e.get('semantic_role')=='PRIMARY' else 2)
        runtime.append({'e':e,'img':img,'sf':max(0,int(math.floor(float(e.get('start_seconds',0))*fps))),'ef':min(total-1,int(math.ceil(float(e.get('end_seconds',0))*fps))),'z':z})
    starts=[[] for _ in range(total+1)];ends=[[] for _ in range(total+1)]
    for i,r in enumerate(runtime):
        starts[r['sf']].append(i)
        if r['ef']+1<=total:ends[r['ef']+1].append(i)
    cmd=[ff,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s:v',f'{width}x{height}','-r',str(float(fps)),'-i','pipe:0','-i',str(audio_path),'-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(output_path)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    active=set(); scene_idx=0
    try:
        for fi in range(total):
            for i in ends[fi]:active.discard(i)
            for i in starts[fi]:active.add(i)
            t=fi/fps
            while scene_idx+1<len(scene_rows) and t>=float(scene_rows[scene_idx]['end_seconds'])-1e-9:scene_idx+=1
            canvas=np.empty((height,width,3),dtype=np.uint8);canvas[:]=255
            for i in sorted(active,key=lambda k:runtime[k]['z']):
                r=runtime[i];st=_event_state(r['e'],t)
                if st:
                    pos,sc,op=st;_apply(canvas,r['img'],pos,op,sc,width,height)
            try: proc.stdin.write(canvas.tobytes())
            except BrokenPipeError: break
            if logger and fi and fi%(int(fps)*10)==0:logger.log('INFO','PRODUCTION_RENDER_PROGRESS',seconds=round(t,1),duration_seconds=round(duration,1))
    finally:
        try:
            if proc.stdin:proc.stdin.close()
        except Exception:pass
    err=(proc.stderr.read() if proc.stderr else b'').decode('utf-8','replace'); rc=proc.wait()
    if rc!=0 or not output_path.is_file() or output_path.stat().st_size<10000:
        raise PreviewError('Full-resolution production MP4 render failed: '+err[-2000:])
    if logger:logger.log('PASS','PRODUCTION_MP4_READY',path=str(output_path),duration_seconds=round(duration,3),frames=total,resolution=f'{width}x{height}',codec='H264_VERYFAST_CRF16_AAC192')
    return {'path':str(output_path),'duration_seconds':duration,'frame_count':total,'fps':fps,'width':width,'height':height}
