from __future__ import annotations
import hashlib, inspect, json, math, os, pathlib, subprocess, shutil
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from PIL import Image
from hexa_v31.util import ensure_dir, write_json, read_json
from hexa_v31.preview import _load_rgba, _prescale, _apply, _event_state, _ease, _ease_position, _lerp
from hexa_v31.typography import render_text_rgba

class SceneMediaError(RuntimeError): pass


def _alpha_blend_top_left(canvas,layer,x,y,opacity=1.0,scale=1.0):
    if opacity<=0.001:return
    img=layer
    if abs(scale-1.0)>0.002:
        nw=max(1,int(round(img.shape[1]*scale)));nh=max(1,int(round(img.shape[0]*scale)));img=cv2.resize(img,(nw,nh),interpolation=cv2.INTER_CUBIC)
    h,w=img.shape[:2];x=int(round(x-(w-layer.shape[1])/2));y=int(round(y-(h-layer.shape[0])/2));x0=max(0,x);y0=max(0,y);x1=min(canvas.shape[1],x+w);y1=min(canvas.shape[0],y+h)
    if x1<=x0 or y1<=y0:return
    lx0=x0-x;ly0=y0-y;lx1=lx0+(x1-x0);ly1=ly0+(y1-y0);crop=img[ly0:ly1,lx0:lx1];a=(crop[:,:,3].astype(np.float32)/255.0)*max(0,min(1,float(opacity)));aa=a[...,None];dst=canvas[y0:y1,x0:x1].astype(np.float32);src=crop[:,:,:3].astype(np.float32);canvas[y0:y1,x0:x1]=(src*aa+dst*(1-aa)).astype(np.uint8)


def _text_state(e,t):
    st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st))
    if t<st or t>en:return None
    fi=max(0.04,float(e.get('fade_in_seconds',0.14)));fo=max(0.04,float(e.get('fade_out_seconds',0.12)))
    if t<st+fi:op=_ease((t-st)/fi)
    elif t>en-fo:op=1.0-_ease((t-(en-fo))/fo)
    else:op=1.0
    q=max(0,min(1,(t-st)/max(0.001,fi+0.16)));s0=float(e.get('pop_scale_from',1.0));sp=float(e.get('pop_scale_peak',1.0));se=float(e.get('pop_scale_end',1.0));sc=_lerp(s0,sp,_ease(q/0.55)) if q<0.55 else _lerp(sp,se,_ease((q-0.55)/0.45));slide_d=max(0.40,float(e.get('slide_duration_seconds',0.42)));slide_q=1.0-_ease_position(min(1.0,max(0.0,(t-st)/max(0.001,slide_d))));dx=float(e.get('slide_dx_norm',0.0))*slide_q;dy=float(e.get('slide_dy_norm',0.0))*slide_q
    sweep_d=max(slide_d,float(e.get('read_sweep_duration_seconds',0.0) or 0.0))
    if sweep_d>slide_d+1e-6:
        sq=min(1.0,max(0.0,(t-st)/max(0.001,sweep_d)))
        settle=1.0-_ease_position(sq)
        dx+=float(e.get('read_sweep_dx_norm',0.0))*settle
        dy+=float(e.get('read_sweep_dy_norm',0.0))*settle
    return op,sc,dx,dy


def _graphic_op(e,t):
    st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st))
    if t<st or t>en:return None
    fi=max(0.05,float(e.get('fade_in_seconds',0.12)));fo=max(0.05,float(e.get('fade_out_seconds',0.12)))
    if t<st+fi:q=_ease((t-st)/fi);op=q
    elif t>en-fo:q=1.0;op=1.0-_ease((t-(en-fo))/fo)
    else:q=1.0;op=1.0
    return op,q


def _draw_graphic(canvas,e,t):
    st=_graphic_op(e,t)
    if not st:return
    op,progress=st;overlay=canvas.copy();h,w=canvas.shape[:2];kind=str(e.get('kind'))
    color=(42,42,42);th=max(3,int(round(h/270)))
    if kind=='ARROW':
        a=e.get('from_norm') or [0.3,0.5];b=e.get('to_norm') or [0.7,0.5];x1=int(a[0]*w);y1=int(a[1]*h);x2=int(_lerp(a[0],b[0],progress)*w);y2=int(_lerp(a[1],b[1],progress)*h);cv2.arrowedLine(overlay,(x1,y1),(x2,y2),color,th,cv2.LINE_AA,0,0.12)
    elif kind=='DIVIDER':
        x=int(float(e.get('x_norm',0.5))*w);cy=h//2;half=int(h*0.28*progress);cv2.line(overlay,(x,cy-half),(x,cy+half),color,th,cv2.LINE_AA)
    elif kind=='X_MARK':
        c=e.get('center_norm') or [0.85,0.15];cx=int(c[0]*w);cy=int(c[1]*h);r=int(min(w,h)*0.035*progress);col=(176,48,48);cv2.line(overlay,(cx-r,cy-r),(cx+r,cy+r),col,th+1,cv2.LINE_AA);cv2.line(overlay,(cx+r,cy-r),(cx-r,cy+r),col,th+1,cv2.LINE_AA)
    elif kind=='CHECK_MARK':
        c=e.get('center_norm') or [0.85,0.15];cx=int(c[0]*w);cy=int(c[1]*h);r=int(min(w,h)*0.042*progress);col=(42,128,78);p1=(cx-r,cy);p2=(cx-int(r*0.25),cy+int(r*0.65));p3=(cx+r,cy-int(r*0.75));cv2.line(overlay,p1,p2,col,th+1,cv2.LINE_AA);cv2.line(overlay,p2,p3,col,th+1,cv2.LINE_AA)
    elif kind=='FOCUS_RING':
        b=e.get('bbox_norm') or [0.3,0.3,0.4,0.4];x,y,bw,bh=map(float,b);pad=0.018;cx=int((x+bw/2)*w);cy=int((y+bh/2)*h);rw=max(8,int((bw/2+pad)*w*progress));rh=max(8,int((bh/2+pad)*h*progress));cv2.ellipse(overlay,(cx,cy),(rw,rh),0,0,360,(55,55,55),max(2,th-1),cv2.LINE_AA)
    cv2.addWeighted(overlay,max(0,min(1,op)),canvas,1-max(0,min(1,op)),0,canvas)


def _fifth_overlay_stack(canvas:np.ndarray, strength:float, black_opacity_percent:float=42.0, blur_percent:float=16.0)->np.ndarray:
    """Pre-render equivalent of the mandated Fifth-Element Overlay stack.

    Existing four-element composition persists, an adjustment blur equivalent is
    applied, then black video darkening is blended before the fifth element is drawn.
    """
    q=max(0.0,min(1.0,float(strength)))
    if q<=0.001:return canvas
    sigma=max(0.1,float(blur_percent)*(canvas.shape[0]/1080.0))
    blurred=cv2.GaussianBlur(canvas,(0,0),sigmaX=sigma,sigmaY=sigma)
    mixed=(canvas.astype(np.float32)*(1.0-q)+blurred.astype(np.float32)*q)
    black_alpha=max(0.0,min(1.0,float(black_opacity_percent)/100.0))*q
    return np.clip(mixed*(1.0-black_alpha),0,255).astype(np.uint8)


def _resize_center(img,scale):
    if abs(scale-1.0)<0.003:return img
    h,w=img.shape[:2];nw=max(1,int(round(w*scale)));nh=max(1,int(round(h*scale)));r=cv2.resize(img,(nw,nh),interpolation=cv2.INTER_CUBIC);out=np.empty_like(img);out[:]=255;x=(w-nw)//2;y=(h-nh)//2
    if nw<=w and nh<=h:out[y:y+nh,x:x+nw]=r
    else:
        sx=max(0,(nw-w)//2);sy=max(0,(nh-h)//2);out[:]=r[sy:sy+h,sx:sx+w]
    return out



def _foreground_mask(frame:np.ndarray, threshold:int=248)->np.ndarray:
    """Stable foreground support on the canonical white stage."""
    mask=np.any(frame<int(threshold),axis=2).astype(np.uint8)
    if not np.any(mask):
        return mask.astype(bool)
    ker=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,ker,iterations=1)
    return mask.astype(bool)


def _distance_core(mask:np.ndarray)->np.ndarray:
    """Normalized interior distance used for opaque object reveal/retire.

    Values near 1 are object cores, values near 0 are boundaries.  Unlike opacity
    crossfades, this lets V31 change ownership spatially while every visible ink pixel
    stays fully opaque.  The white stage therefore never receives a pale ghost trough.
    """
    if mask is None or not np.any(mask):
        return np.zeros(mask.shape if mask is not None else (1,1),dtype=np.float32)
    dt=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,5).astype(np.float32)
    mx=float(dt.max())
    return dt/mx if mx>1e-6 else mask.astype(np.float32)


def _object_only_bridge(prev,current,q):
    """Opaque directional object handoff on the stable white stage.

    P1 used opacity-to-white and produced pale ghosts.  An early P2 prototype used
    distance erosion, which kept opacity but made objects visually disintegrate.  The
    production P2 bridge instead performs a conventional directional matte handoff:
    the incoming foreground is revealed from the side it occupies while the outgoing
    foreground is wiped away in the opposite temporal half.  RGB ink is never faded
    toward white and the canvas itself never cross-dissolves.
    """
    if prev is None:
        prev=np.empty_like(current);prev[:]=255
    q=max(0.0,min(1.0,float(q)))
    if q<=1e-6:return prev.copy()
    if q>=1.0-1e-6:return current.copy()
    q=_ease(q)
    pm=_foreground_mask(prev);cm=_foreground_mask(current)
    if not np.any(pm) and not np.any(cm):
        out=np.empty_like(current);out[:]=255;return out

    def centroid(mask):
        yy,xx=np.where(mask)
        if len(xx)==0:return (0.5,0.5)
        return (float(np.mean(xx))/max(1,mask.shape[1]-1),float(np.mean(yy))/max(1,mask.shape[0]-1))
    pcx,pcy=centroid(pm);ccx,ccy=centroid(cm);dx=ccx-pcx;dy=ccy-pcy
    h,w=pm.shape;yy,xx=np.mgrid[0:h,0:w]
    xn=xx/max(1.0,float(w-1));yn=yy/max(1.0,float(h-1))

    # Incoming object is established directionally during the first half.  The old
    # composition remains intact until the new one is fully readable, then retires as a
    # single semantic state.  This avoids both pale ghosts and ugly object-fragment erosion.
    reveal_q=max(0.0,min(1.0,q/0.52))
    if abs(dx)>=abs(dy):
        if dx>=0:cur_show=cm & (xn >= 1.0-reveal_q)
        else:cur_show=cm & (xn <= reveal_q)
    else:
        if dy>=0:cur_show=cm & (yn >= 1.0-reveal_q)
        else:cur_show=cm & (yn <= reveal_q)
    prev_keep=pm if q<0.58 else np.zeros_like(pm)

    out=np.empty_like(current);out[:]=255
    if np.any(prev_keep):out[prev_keep]=prev[prev_keep]
    if np.any(cur_show):out[cur_show]=current[cur_show]
    return out


def _bridge(prev,current,q,mode):
    """Reference-safe boundary punctuation.

    Every normal V31 boundary is now an opaque foreground ownership transition.
    Full-frame opacity blending and white dips are intentionally absent from production.
    Directional wipes remain available only when explicitly selected by the semantic
    transition planner and they copy source pixels at full opacity.
    """
    q=max(0.0,min(1.0,float(q)))
    if prev is None:
        prev=np.empty_like(current);prev[:]=255
    # Opening from white and all legacy blend aliases use the same no-ghost object bridge.
    if mode in ('SEQUENCE_OBJECT_CARRY','OBJECT_MATCH_BLEND','OBJECT_RESET_6F','OPEN_WHITE',
                'CUT_CARRY','CARRY_BLEND_4F','SOFT_MATCH_3F','SOFT_MATCH_6F','SOFT_MATCH_8F',
                'FOCUS_BLEND_3F','WHITE_DIP','OBJECT_CARRY_4F','OBJECT_REVEAL_6F','OBJECT_REPLACE_8F'):
        return _object_only_bridge(prev,current,q)
    h,w=current.shape[:2];out=np.empty_like(current);out[:]=255
    qq=_ease(q)
    if mode=='DIRECTIONAL_WIPE_3F':
        cut=int(round(w*qq));out[:,:cut]=current[:,:cut];out[:,cut:]=prev[:,cut:];return out
    if mode=='SIDE_WIPE_3F':
        half=int(round((w/2)*qq));mid=w//2;out[:]=prev
        if half>0:out[:,max(0,mid-half):min(w,mid+half)]=current[:,max(0,mid-half):min(w,mid+half)]
        return out
    return _object_only_bridge(prev,current,q)


def _apply_event_motion(canvas:np.ndarray,img:np.ndarray,e:dict,t:float,width:int,height:int,fps:float):
    """Render one semantic layer with conservative temporal supersampling.

    The center sample remains dominant. Two low-opacity shutter samples are emitted only
    when the layer actually changes position/scale enough to justify visible motion blur.
    This keeps static illustrated edges crisp while removing the digital stop/start feel
    of fast Position transfers.
    """
    state=_event_state(e,t)
    if not state:return
    pos,sc,op=state
    if not bool(e.get('motion_blur_enabled')) or op<=0.001:
        _apply(canvas,img,pos,op,sc,width,height);return
    shutter=max(60.0,min(180.0,float(e.get('motion_blur_shutter_degrees',144.0))))
    dt=(shutter/360.0)/max(1.0,float(fps))
    a=_event_state(e,max(float(e.get('start_seconds',t)),t-dt))
    b=_event_state(e,min(float(e.get('end_seconds',t)),t+dt))
    if not a or not b:
        _apply(canvas,img,pos,op,sc,width,height);return
    travel=math.hypot(float(b[0][0])-float(a[0][0]),float(b[0][1])-float(a[0][1]))*(width/1920.0)
    scale_travel=abs(float(b[1])-float(a[1]))*min(width,height)
    if travel<0.70 and scale_travel<0.55:
        _apply(canvas,img,pos,op,sc,width,height);return
    # Side samples are intentionally subtle; excessive smear hurts the reference's
    # crisp illustrative language. Center opacity is not reduced to preserve edge density.
    _apply(canvas,img,a[0],min(0.14,op*0.14),a[1],width,height)
    _apply(canvas,img,pos,op,sc,width,height)
    _apply(canvas,img,b[0],min(0.14,op*0.14),b[1],width,height)


def _last_frame_rgb(path):
    cap=cv2.VideoCapture(str(path));n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0);frame=None
    if n>0:cap.set(cv2.CAP_PROP_POS_FRAMES,max(0,n-1))
    ok,fr=cap.read();cap.release()
    if ok and fr is not None:return cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)
    return None


def _scene_signature(scene_row,events,text_events,graphic_events,vision_scene,width,height,fps,prev_sig):
    payload={'version':'HEXA_SCENE_MEDIA_V31_P2_REFERENCE_CHOREOGRAPHY','scene':scene_row,'events':events,'text_events':text_events,'graphic_events':graphic_events,'prev_signature':prev_sig,'vision_cache':[(u.get('physical_id'),u.get('layer_path'),u.get('layer_canvas_mode')) for u in (vision_scene.get('units') or [])],'width':width,'height':height,'fps':fps}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()


def _render_scene_media_per_scene_legacy(render_edit_map,motion_plan,vision_results,text_plan,graphics_plan,out_dir,cache_dir,width=1920,height=1080,fps=30.0,logger=None):
    """Retained forensic per-scene renderer; never the production entry point.

    The continuous-story renderer below is the sole public production authority.
    Keeping this implementation explicitly private preserves old cache inspection
    capability without allowing Python definition order to select it accidentally.
    """
    out=ensure_dir(out_dir);cache=ensure_dir(cache_dir);vis={str(v.get('scene_id')):v for v in vision_results};scene_rows=motion_plan.get('scenes') or [];all_events=render_edit_map.get('events') or [];text_events=text_plan.get('events') or [];graphic_events=(graphics_plan or {}).get('events') or []
    ebs={};tbs={};gbs={}
    # A render scene owns its source image, not every visible physical layer.
    # Continuous instances are selected below by their physical lifetime so an
    # evidence-backed carrier can remain on the canvas across source/card cuts
    # without manufacturing a duplicate entry clip.
    for e in all_events:ebs.setdefault(str(e.get('scene_id')),[]).append(e)
    for e in text_events:tbs.setdefault(str(e.get('scene_id')),[]).append(e)
    for e in graphic_events:gbs.setdefault(str(e.get('scene_id')),[]).append(e)
    clips=[];ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg';prev_final=None;prev_sig='ROOT'
    for idx,s in enumerate(scene_rows,1):
        sid=str(s['scene_id']);vr=vis.get(sid)
        if vr is None:raise SceneMediaError('Vision result missing for '+sid)
        sf=int(round(float(s['start_seconds'])*fps));ef=max(sf+1,int(round(float(s['end_seconds'])*fps)));frames=ef-sf;scene_start=float(s['start_seconds']);scene_end=float(s['end_seconds']);evs=[e for e in all_events if float(e.get('physical_start_seconds',e.get('start_seconds',0)))<scene_end-1e-6 and float(e.get('physical_end_seconds',e.get('end_seconds',0)))>scene_start+1e-6];tes=tbs.get(sid,[]);ges=gbs.get(sid,[]);sig=_scene_signature(s,evs,tes,ges,vr,width,height,fps,prev_sig);scene_cache=ensure_dir(cache/sid);media=scene_cache/(sid+'__ANIMATED_V31_P2.mp4');meta=scene_cache/'scene_media.json';hit=False
        if media.is_file() and media.stat().st_size>4096 and meta.is_file():
            try:hit=read_json(meta).get('signature')==sig
            except Exception:hit=False
        if not hit:
            runtime=[]
            for e in evs:
                src=e.get('source_path')
                if not src or not pathlib.Path(src).is_file():raise SceneMediaError(f'{sid}: missing render source {src}')
                img=_prescale(_load_rgba(src),float(e.get('base_fit_scale_percent',100.0)),width);typ=e.get('semantic_type') or e.get('kind') or '';z=4 if typ in ('MAIN_CHARACTER','SECONDARY_CHARACTER') or e.get('kind') in ('MAIN_NARRATOR','SECONDARY_CHARACTER') else (3 if e.get('semantic_role')=='PRIMARY' else 2);runtime.append((z,e,img))
            text_runtime=[(te,np.array(render_text_rgba(te,width,height).convert('RGBA'))) for te in tes]
            trans=s.get('transition') or {};mode=str(trans.get('mode') or ('OPEN_WHITE' if idx==1 else 'CUT_CARRY'));td=max(1.0/fps,float(trans.get('duration_seconds') or (2.0/fps)));first_start=min([float(e.get('start_seconds',float(s['start_seconds']))) for e in evs] or [float(s['start_seconds'])]);scene_start=float(s['start_seconds']);bridge_start=max(0.0,first_start-scene_start-min(td*0.35,1.0/fps));bridge_end=min(max(bridge_start+td,td),max(1.0/fps,float(s['end_seconds'])-scene_start));prev_occ=(float(np.mean(np.any(prev_final<246,axis=2))) if prev_final is not None else 0.0)
            tmp=scene_cache/(sid+'__tmp.mp4');cmd=[ff,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s:v',f'{width}x{height}','-r',str(float(fps)),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(tmp)];proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            last_canvas=None
            try:
                for j in range(frames):
                    t=(sf+j)/fps;local=j/fps;canvas=np.empty((height,width,3),dtype=np.uint8);canvas[:]=255
                    ordered_runtime=sorted(runtime,key=lambda x:x[0])
                    base_runtime=[r for r in ordered_runtime if not r[1].get('fifth_element_overlay')]
                    overlay_runtime=[r for r in ordered_runtime if r[1].get('fifth_element_overlay')]
                    for _,e,img in base_runtime:
                        state=_event_state(e,t)
                        if state:_apply_event_motion(canvas,img,e,t,width,height,fps)
                    overlay_states=[]
                    for _,e,img in overlay_runtime:
                        state=_event_state(e,t)
                        if state:overlay_states.append((e,img,state))
                    if overlay_states:
                        strength=max(max(0.0,min(1.0,float(st[2])) ) for _,_,st in overlay_states)
                        e0=overlay_states[0][0]
                        canvas=_fifth_overlay_stack(canvas,strength,float(e0.get('overlay_black_opacity_percent') or 42),float(e0.get('overlay_blur_percent') or 16))
                        for e,img,(pos,sc,op) in overlay_states:_apply(canvas,img,pos,op,sc,width,height)
                    for ge in ges:_draw_graphic(canvas,ge,t)
                    for te,ti in text_runtime:
                        ts=_text_state(te,t)
                        if ts:
                            op,sc,dx,dy=ts;x=int(round((float(te.get('x_norm',0.1))+dx)*width));y=int(round((float(te.get('y_norm',0.08))+dy)*height));_alpha_blend_top_left(canvas,ti,x,y,op,sc)
                    # Preserve continuity while the next semantic visual has not started yet.
                    # Never dissolve a meaningful previous frame into a blank white current canvas
                    # merely because the next unit's spoken trigger occurs later in the Scene.
                    if prev_final is not None and mode!='WHITE_DIP' and local<bridge_start-1e-6 and prev_occ>=0.02:
                        canvas=prev_final.copy()
                    elif local<bridge_end:
                        current_occ=float(np.mean(np.any(canvas<246,axis=2)))
                        bridge_target=prev_final if (prev_final is not None and mode!='WHITE_DIP' and current_occ<0.01 and prev_occ>=0.02) else canvas
                        q=(local-bridge_start)/max(1e-6,bridge_end-bridge_start);canvas=_bridge(prev_final,bridge_target,q,mode)
                    last_canvas=canvas;proc.stdin.write(canvas.tobytes())
                proc.stdin.close();err=proc.stderr.read().decode('utf-8','replace');rc=proc.wait()
            except Exception:
                try:proc.kill()
                except Exception:pass
                raise
            if rc!=0 or not tmp.is_file() or tmp.stat().st_size<=4096:raise SceneMediaError(f'{sid}: ffmpeg animated Scene render failed rc={rc}: {err[-1600:]}')
            tmp.replace(media);write_json(meta,{'schema':'HEXA_SCENE_MEDIA_CACHE_V31','version':'31.0.9','signature':sig,'scene_id':sid,'frames':frames,'fps':fps,'width':width,'height':height,'motion_event_count':len(evs),'text_event_count':len(tes),'graphic_event_count':len(ges),'transition_mode':mode,'bridge_start_seconds':round(bridge_start,6),'bridge_duration_seconds':round(max(0.0,bridge_end-bridge_start),6),'previous_frame_nonwhite_fraction':round(prev_occ,6),'path':str(media)})
            if logger:logger.log('PASS','ANIMATED_SCENE_RENDERED',scene_id=sid,frames=frames,motion_events=len(evs),text_events=len(tes),graphic_events=len(ges),transition=mode,progress=f'{idx}/{len(scene_rows)}')
        else:
            if logger:logger.log('PASS','ANIMATED_SCENE_CACHE_HIT',scene_id=sid,frames=frames,motion_events=len(evs),text_events=len(tes),graphic_events=len(ges),progress=f'{idx}/{len(scene_rows)}')
        run_media=out/(sid+'__ANIMATED.mp4')
        if run_media.exists():run_media.unlink()
        try:os.link(media,run_media)
        except Exception:shutil.copy2(media,run_media)
        prev_final=_last_frame_rgb(run_media);prev_sig=sig
        clips.append({'scene_id':sid,'clip_display_name':sid+'__ANIMATED','source_path':str(run_media.resolve()),'start_frame':sf,'end_frame':ef,'start_seconds':sf/fps,'end_seconds':ef/fps,'duration_frames':frames,'duration_seconds':frames/fps,'premiere_track_index':0,'item_role':'ANIMATED_SCENE_MEDIA','motion_event_count':len(evs),'text_event_count':len(tes),'graphic_event_count':len(ges),'transition_mode':(s.get('transition') or {}).get('mode'),'width':width,'height':height,'fps':fps})
    manifest={'schema':'HEXA_ANIMATED_SCENE_MEDIA_MANIFEST_V31','version':'31.0.9','execution_authority':'PROFESSIONAL_SEMANTIC_MOTION__EDGE_MATTING__OCCLUSION_SAFE__VOICE_CHOREOGRAPHED','scene_count':len(clips),'clips':clips,'motion_event_count':sum(x['motion_event_count'] for x in clips),'text_event_count':sum(x['text_event_count'] for x in clips),'graphic_event_count':sum(x['graphic_event_count'] for x in clips),'transition_modes':sorted(set(x.get('transition_mode') for x in clips)),'width':width,'height':height,'fps':fps}
    write_json(pathlib.Path(out)/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json',manifest)
    if logger:logger.log('PASS','ANIMATED_SCENE_MEDIA_READY',scene_count=len(clips),motion_events=manifest['motion_event_count'],text_events=manifest['text_event_count'],graphic_events=manifest['graphic_event_count'],transition_modes=len(manifest['transition_modes']),resolution=f'{width}x{height}')
    return manifest


def assemble_final_mp4(scene_media:dict,audio_path,output_path,work_dir,logger=None):
    clips=scene_media.get('clips') or []
    if not clips:raise SceneMediaError('No animated Scene clips for final MP4 assembly.')
    ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg';work=ensure_dir(work_dir);lst=pathlib.Path(work)/'concat_v31.txt';silent=pathlib.Path(work)/'HEXA_V31_CONCAT_SILENT.mp4';out=pathlib.Path(output_path);out.parent.mkdir(parents=True,exist_ok=True)
    def esc(p):return str(pathlib.Path(p).resolve()).replace("'","'\\''")
    lst.write_text(''.join("file '"+esc(c['source_path'])+"'\n" for c in clips),encoding='utf-8')
    c1=[ff,'-y','-v','error','-f','concat','-safe','0','-i',str(lst),'-c:v','copy','-an','-movflags','+faststart',str(silent)];cp=subprocess.run(c1,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if cp.returncode!=0 or not silent.is_file() or silent.stat().st_size<10000:
        c1=[ff,'-y','-v','error','-f','concat','-safe','0','-i',str(lst),'-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(silent)];cp=subprocess.run(c1,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if cp.returncode!=0:raise SceneMediaError('Final Scene concat failed: '+(cp.stderr or '')[-1800:])
    c2=[ff,'-y','-v','error','-i',str(silent),'-i',str(audio_path),'-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(out)];cp=subprocess.run(c2,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if cp.returncode!=0 or not out.is_file() or out.stat().st_size<100000:raise SceneMediaError('Final MP4 audio mux failed: '+(cp.stderr or '')[-1800:])
    if logger:logger.log('PASS','FINAL_MP4_ASSEMBLED',path=str(out),bytes=out.stat().st_size,scene_count=len(clips),authority='SAME_ANIMATED_SCENE_MEDIA_AS_PREMIERE')
    return {'path':str(out),'bytes':out.stat().st_size,'scene_count':len(clips)}

# ---------------------------------------------------------------------------
# V31.0.1 CONTINUOUS VISUAL TIMELINE
# Production override: render one uninterrupted visual story.  Original audio
# scene boundaries remain timing/semantic metadata only; they are not full-frame
# transition operators.  Every visible change is an object preset event.
# ---------------------------------------------------------------------------
def render_scene_media(render_edit_map,motion_plan,vision_results,text_plan,graphics_plan,out_dir,cache_dir,width=1920,height=1080,fps=30.0,logger=None):
    from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa, encoded_visual_gap_qa, frame_survival_signature
    out=ensure_dir(out_dir);cache=ensure_dir(cache_dir)
    events=[e for e in (render_edit_map.get('events') or []) if not e.get('suppressed_by_card_density') and float(e.get('physical_end_seconds',e.get('end_seconds',0)))>float(e.get('physical_start_seconds',e.get('start_seconds',0)))+1e-6]
    duration=max([float(s.get('end_seconds',0)) for s in (motion_plan.get('scenes') or [])]+[float(e.get('physical_end_seconds',e.get('end_seconds',0))) for e in events]+[0.0])
    total=max(1,int(math.ceil(duration*float(fps))))
    cards=list((motion_plan.get('visual_cards') or {}).get('cards') or [])
    coverage_plan=dict(motion_plan);coverage_plan['events']=events
    coverage=visual_timeline_coverage_qa(coverage_plan,fps,duration)
    if not coverage.get('pass'):
        gap=next(iter(coverage.get('visual_gaps') or []),{})
        t=float(gap.get('start_seconds',0));fi=int(round(t*float(fps)))
        previous=max((e for e in events if float(e.get('physical_end_seconds',e.get('end_seconds',0)))<=t),key=lambda e:float(e.get('physical_end_seconds',e.get('end_seconds',0))),default=None)
        upcoming=min((e for e in events if float(e.get('physical_start_seconds',e.get('start_seconds',0)))>t),key=lambda e:float(e.get('physical_start_seconds',e.get('start_seconds',0))),default=None)
        active_ids=[str(e.get('event_id')) for e in events if float(e.get('physical_start_seconds',e.get('start_seconds',0)))<=t<float(e.get('physical_end_seconds',e.get('end_seconds',0)))]
        raise SceneMediaError(f"VISUAL_TIMELINE_COVERAGE_GAP timestamp={t:.6f} frame={fi} visual_card_id={gap.get('visual_card_id')} previous_carrier={None if previous is None else previous.get('visual_carrier_id')} next_carrier={None if upcoming is None else upcoming.get('visual_carrier_id')} active_actor_ids={active_ids}")

    # Exact authored/canonical title copy is rendered above source imagery. Graphics are
    # still restricted to explicit package directives.
    text_events=list((text_plan or {}).get('events') or [])
    graphic_events=list((graphics_plan or {}).get('events') or [])

    # Cache authority includes the one public renderer implementation itself.
    # Event-plan equivalence alone is insufficient: a renderer correction must
    # never reuse a pre-correction MP4.  Hash the actual callable rather than
    # this complete module, so private forensic helpers do not masquerade as
    # production-renderer changes.
    try:
        renderer_source_sha256=hashlib.sha256(inspect.getsource(render_scene_media).encode('utf-8')).hexdigest()
        typography_source_sha256=hashlib.sha256(pathlib.Path(render_text_rgba.__code__.co_filename).read_bytes()).hexdigest()
        compositor_source_sha256=hashlib.sha256(pathlib.Path(_apply.__code__.co_filename).read_bytes()).hexdigest()
    except OSError:
        renderer_source_sha256='UNAVAILABLE';typography_source_sha256='UNAVAILABLE';compositor_source_sha256='UNAVAILABLE'
    # Cache signature is tied to the exact user preset authority, complete event
    # plan, and implementation that rasterizes it.
    sig_payload={
        'version':'HEXA_SCENE_MEDIA_V31_RENDERER_AUTHORITY_3_FOUNDATION_PARTITION_CHOREOGRAPHY',
        'renderer_source_sha256':renderer_source_sha256,
        'typography_source_sha256':typography_source_sha256,
        'compositor_source_sha256':compositor_source_sha256,
        'motion_dna':motion_plan.get('motion_dna_version'),'events':events,'cards':cards,'text_events':text_events,'graphic_events':graphic_events,
        'width':width,'height':height,'fps':fps,
        'preset_authority':motion_plan.get('preset_authority'),
        'hard_invariants':motion_plan.get('hard_invariants'),
    }
    sig=hashlib.sha256(json.dumps(sig_payload,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()
    media=pathlib.Path(cache)/'V31_0_26_FOUNDATION_PARTITION_STORY.mp4';meta=pathlib.Path(cache)/'V31_0_26_FOUNDATION_PARTITION_STORY.json'
    hit=False;cache_meta={}
    if media.is_file() and media.stat().st_size>4096 and meta.is_file():
        try: cache_meta=read_json(meta);hit=cache_meta.get('signature')==sig
        except Exception: hit=False

    if not hit:
        # Metadata runtime only.  Full-resolution RGBA canvases are loaded lazily while
        # active and released immediately after their final frame, so 49+ scene projects
        # do not retain hundreds of MB of masks in memory.
        rows=[]
        for e in events:
            src=e.get('source_path')
            if not src or not pathlib.Path(src).is_file():
                raise SceneMediaError(f"{e.get('event_id')}: missing render source {src}")
            typ=e.get('semantic_type') or e.get('kind') or ''
            z=4 if typ in ('MAIN_CHARACTER','SECONDARY_CHARACTER') or e.get('kind') in ('MAIN_NARRATOR','SECONDARY_CHARACTER') else (3 if str(e.get('attention_priority') or e.get('semantic_role')).upper()=='PRIMARY' else 2)
            sf=max(0,int(math.floor(float(e.get('physical_start_seconds',e.get('start_seconds',0)))*fps)))
            ef=min(total-1,max(sf,int(math.ceil(float(e.get('physical_end_seconds',e.get('end_seconds',0)))*fps))))
            rows.append({'e':e,'src':str(src),'sf':sf,'ef':ef,'z':z,'img':None})
        text_runtime=[(te,np.array(render_text_rgba(te,width,height).convert('RGBA'))) for te in text_events]
        starts=[[] for _ in range(total+1)]; ends=[[] for _ in range(total+1)]
        for i,r in enumerate(rows):
            starts[r['sf']].append(i)
            if r['ef']+1<=total:ends[r['ef']+1].append(i)

        tmp=pathlib.Path(cache)/'V31_0_26_FOUNDATION_PARTITION_STORY__tmp.mp4'
        ff=os.environ.get('HEXA_FFMPEG') or 'ffmpeg'
        # A previous interrupted render can leave the temporary MP4 in place.
        # Start from a new inode and keep x264 single-threaded on the certified
        # low-memory runtime: the Windows static FFmpeg build has otherwise
        # produced a zero-exit-code MP4 containing malformed length-prefixed
        # NAL packets under memory pressure.  Fast-start is applied by final
        # assembly, after the elementary stream has been decode-validated.
        if tmp.exists():
            tmp.unlink()
        cmd=[ff,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s:v',f'{width}x{height}','-r',str(float(fps)),'-i','pipe:0','-an','-c:v','libx264','-threads','1','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',str(tmp)]
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        active=set();expected_evidence=[];evidence_stride=max(1,int(round(float(fps)/6.0)))
        try:
            for fi in range(total):
                # End before start on a shared boundary: retired card objects are removed,
                # then the next card's preset entries become active.  No full-frame bridge.
                for i in ends[fi]:
                    active.discard(i);rows[i]['img']=None
                for i in starts[fi]:
                    if rows[i]['img'] is None:
                        full=_prescale(_load_rgba(rows[i]['src']),float(rows[i]['e'].get('base_fit_scale_percent',100.0))*float(rows[i]['e'].get('layout_scale_multiplier',1.0)),width)
                        # Render the actual isolated object crop, not a translated 1920x1080
                        # transparent canvas. Premiere Position presets are defined on clip/object
                        # centers; applying them to a full transparent canvas was a core source of
                        # P2 overshoot and visually wrong icon relationships.
                        a=full[:,:,3]
                        yy,xx=np.where(a>3)
                        if len(xx):
                            pad=max(3,int(round(min(full.shape[0],full.shape[1])*0.003)))
                            x0=max(0,int(xx.min())-pad);x1=min(full.shape[1],int(xx.max())+1+pad)
                            y0=max(0,int(yy.min())-pad);y1=min(full.shape[0],int(yy.max())+1+pad)
                            crop=full[y0:y1,x0:x1].copy()
                            canvas_left=(width-full.shape[1])/2.0;canvas_top=(height-full.shape[0])/2.0
                            rest=[canvas_left+(x0+x1)/2.0,canvas_top+(y0+y1)/2.0]
                        else:
                            crop=full;rest=[width/2.0,height/2.0]
                        er=dict(rows[i]['e']);er['preset_coordinate_mode']='ABSOLUTE_OBJECT_CENTER'
                        planned=er.get('card_rest_position_norm')
                        if isinstance(planned,(list,tuple)) and len(planned)>=2:
                            rest=[float(planned[0])*width,float(planned[1])*height]
                        er['object_rest_position_px']=rest;er['sequence_width']=width;er['sequence_height']=height
                        rows[i]['e']=er;rows[i]['img']=crop
                    active.add(i)
                t=fi/float(fps)
                card=next((c for c in cards if float(c.get('start_seconds',0))<=t<float(c.get('end_seconds',0))),None)
                if card is not None and not active:
                    previous=max((e for e in events if float(e.get('physical_end_seconds',e.get('end_seconds',0)))<=t),key=lambda e:float(e.get('physical_end_seconds',e.get('end_seconds',0))),default=None)
                    upcoming=min((e for e in events if float(e.get('physical_start_seconds',e.get('start_seconds',0)))>t),key=lambda e:float(e.get('physical_start_seconds',e.get('start_seconds',0))),default=None)
                    raise SceneMediaError(f"VISUAL_TIMELINE_COVERAGE_GAP timestamp={t:.6f} frame={fi} visual_card_id={card.get('card_id')} previous_carrier={None if previous is None else previous.get('visual_carrier_id')} next_carrier={None if upcoming is None else upcoming.get('visual_carrier_id')} active_actor_ids=[]")
                canvas=np.empty((height,width,3),dtype=np.uint8);canvas[:]=255
                expected_members=[]
                for i in sorted(active,key=lambda k:(rows[k]['z'],str(rows[k]['e'].get('event_id')))):
                    r=rows[i];state=_event_state(r['e'],t)
                    if not state:continue
                    pos,sc,op=state
                    # The exact user presets are the motion authority. V31 intentionally
                    # adds no synthetic blur/pulse/drift on top of them.
                    _apply(canvas,r['img'],pos,op,sc,width,height)
                    if op>.12:
                        ih,iw=r['img'].shape[:2];nw=max(1,int(round(iw*sc)));nh=max(1,int(round(ih*sc)))
                        cx=float(pos[0])*(width/1920.0);cy=float(pos[1])*(height/1080.0)
                        expected_members.append({'event_id':r['e'].get('event_id'),'render_mode':r['e'].get('render_mode'),
                                                 'bbox_px':[cx-nw/2,cy-nh/2,cx+nw/2,cy+nh/2]})
                if fi%evidence_stride==0:
                    expected_evidence.append(frame_survival_signature(canvas,fi,t,expected_members))
                for ge in graphic_events:_draw_graphic(canvas,ge,t)
                for te,ti in text_runtime:
                    ts=_text_state(te,t)
                    if ts:
                        op,sc,dx,dy=ts;x=int(round((float(te.get('x_norm',.1))+dx)*width));y=int(round((float(te.get('y_norm',.08))+dy)*height));_alpha_blend_top_left(canvas,ti,x,y,op,sc)
                proc.stdin.write(canvas.tobytes())
                if logger and fi and fi%(int(max(1,fps))*10)==0:
                    logger.log('INFO','CONTINUOUS_STORY_RENDER_PROGRESS',seconds=round(t,1),duration_seconds=round(duration,1),active_objects=len(active))
            proc.stdin.close();err=proc.stderr.read().decode('utf-8','replace');rc=proc.wait()
        except Exception:
            try:proc.kill()
            except Exception:pass
            raise
        if rc!=0 or not tmp.is_file() or tmp.stat().st_size<=4096:
            raise SceneMediaError('V31.0.25 continuous story render failed: '+(err[-1800:] if 'err' in locals() else 'unknown ffmpeg error'))
        verify=subprocess.run(
            [ff,'-v','error','-i',str(tmp),'-map','0:v:0','-f','null','-'],
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,
        )
        if verify.returncode!=0 or (verify.stderr or '').strip():
            raise SceneMediaError('Continuous story render decode validation failed: '+(verify.stderr or '')[-1800:])
        pixel_gap_qa=encoded_visual_gap_qa(tmp,coverage_plan,expected_evidence=expected_evidence)
        if not pixel_gap_qa.get('pass'):
            raise SceneMediaError('ENCODED_VISUAL_TIMELINE_COVERAGE_GAP: '+str(pixel_gap_qa.get('blank_runs')))
        tmp.replace(media)
        write_json(meta,{
            'schema':'HEXA_SCENE_MEDIA_CACHE_V31','version':'31.0.25','signature':sig,
            'frames':total,'duration_seconds':duration,'fps':fps,'width':width,'height':height,
            'motion_event_count':len(events),'text_event_count':len(text_events),'graphic_event_count':len(graphic_events),
            'visual_card_count':len(cards),'transition_execution':'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND',
            'path':str(media),'visual_timeline_coverage_qa':coverage,'encoded_visual_gap_qa':pixel_gap_qa,
            'expected_visual_survival_evidence':expected_evidence
        })
        if logger:logger.log('PASS','CONTINUOUS_STORY_TIMELINE_RENDERED',frames=total,motion_events=len(events),visual_cards=len(cards),transition='OBJECT_PRESETS_ONLY',resolution=f'{width}x{height}')
    else:
        if logger:logger.log('PASS','CONTINUOUS_STORY_TIMELINE_CACHE_HIT',frames=total,motion_events=len(events),visual_cards=len(cards),resolution=f'{width}x{height}')

    # Cache hits are delivery inputs too; decode and certify the exact file that
    # will be linked into this run rather than trusting historical metadata.
    expected_evidence=expected_evidence if not hit else list(cache_meta.get('expected_visual_survival_evidence') or [])
    pixel_gap_qa=encoded_visual_gap_qa(media,coverage_plan,expected_evidence=expected_evidence)
    if not pixel_gap_qa.get('pass'):
        raise SceneMediaError('ENCODED_VISUAL_TIMELINE_COVERAGE_GAP: '+str(pixel_gap_qa.get('blank_runs')))

    run_media=pathlib.Path(out)/'V31_0_25_GLOBAL_STORY__ANIMATED.mp4'
    if run_media.exists():run_media.unlink()
    try:os.link(media,run_media)
    except Exception:shutil.copy2(media,run_media)
    clip={
        'scene_id':'V31_0_25_GLOBAL_STORY','clip_display_name':'V31_0_25_GLOBAL_STORY__ANIMATED',
        'source_path':str(run_media.resolve()),'start_frame':0,'end_frame':total,
        'start_seconds':0.0,'end_seconds':total/float(fps),'duration_frames':total,'duration_seconds':total/float(fps),
        'premiere_track_index':0,'item_role':'ANIMATED_CONTINUOUS_STORY_MEDIA',
        'motion_event_count':len(events),'text_event_count':len(text_events),'graphic_event_count':len(graphic_events),
        'transition_mode':'OBJECT_PRESETS_ONLY','width':width,'height':height,'fps':fps,
        'visual_card_count':len(cards),
    }
    manifest={
        'schema':'HEXA_ANIMATED_SCENE_MEDIA_MANIFEST_V31','version':'31.0.25',
        'execution_authority':'USER_PRESET_CONTINUOUS_OBJECT_STORY_TIMELINE',
        'scene_count':1,'visual_card_count':len(cards),'clips':[clip],
        'visual_timeline_coverage_qa':coverage,'encoded_visual_gap_qa':pixel_gap_qa,
        'motion_event_count':len(events),'text_event_count':len(text_events),'graphic_event_count':len(graphic_events),
        'transition_modes':['OBJECT_PRESETS_ONLY__NO_FRAME_BLEND'],'width':width,'height':height,'fps':fps,
        'full_frame_crossfade_count':0,'mask_wipe_count':0,'white_dip_count':0,
    }
    write_json(pathlib.Path(out)/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json',manifest)
    if logger:logger.log('PASS','ANIMATED_SCENE_MEDIA_READY',scene_count=1,visual_cards=len(cards),motion_events=len(events),text_events=len(text_events),graphic_events=len(graphic_events),transition_modes=1,resolution=f'{width}x{height}')
    return manifest
