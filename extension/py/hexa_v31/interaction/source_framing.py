from __future__ import annotations
import copy,hashlib,pathlib
import numpy as np
from PIL import Image

VERSION='HEXA_VISIBLE_INK_SOURCE_FRAMING_V1_2_ATOMIC_ONLY'

def _ink_bbox(arr:np.ndarray):
    rgb=arr[:,:,:3].astype(np.int16);alpha=arr[:,:,3]
    delta=255-rgb.min(axis=2);spread=rgb.max(axis=2)-rgb.min(axis=2)
    ink=(alpha>8)&((delta>=7)|(spread>=5))
    yy,xx=np.where(ink)
    if len(xx)<32:return None
    return int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1

def _safe_crop(arr:np.ndarray,bbox):
    h,w=arr.shape[:2];x0,y0,x1,y1=bbox
    pad=max(4,int(round(min(w,h)*.018)));x0=max(0,x0-pad);y0=max(0,y0-pad);x1=min(w,x1+pad);y1=min(h,y1+pad)
    if x0<=1 or y0<=1 or x1>=w-1 or y1>=h-1:return None
    crop_w=x1-x0;crop_h=y1-y0
    if crop_w<24 or crop_h<24:return None
    retained=(crop_w*crop_h)/max(1,w*h)
    if retained>.82:return None
    return x0,y0,x1,y1

def _planned_fit_percent(event:dict,crop_w:int,crop_h:int)->float|None:
    rect=event.get('planned_rect_norm')
    if not isinstance(rect,(list,tuple)) or len(rect)!=4:return None
    desired_w=max(24.0,float(rect[2])*1920.0);desired_h=max(24.0,float(rect[3])*1080.0)
    layout_scale=max(.05,float(event.get('layout_scale_multiplier') or 1.0))
    factor=min(desired_w/max(1.0,crop_w),desired_h/max(1.0,crop_h))/layout_scale
    return max(35.0,min(420.0,factor*100.0))

def normalize_render_sources(render_edit_map:dict,cache_dir,logger=None)->tuple[dict,dict]:
    out=copy.deepcopy(render_edit_map);root=pathlib.Path(cache_dir)/'interaction_source_framing';root.mkdir(parents=True,exist_ok=True)
    rows=[];changed=0
    for event in out.get('events') or []:
        mode=str(event.get('render_mode') or '').upper()
        if event.get('suppressed_by_card_density') or mode in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            if mode in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
                rows.append({'event_id':event.get('event_id'),'decision':'PRESERVE_SOURCE','reason':'FOUNDATION_PARTITION_AUTHORITY'})
            continue
        src=event.get('source_path') or event.get('source_layer_path')
        if not src:continue
        p=pathlib.Path(src)
        if not p.is_file():continue
        try:arr=np.array(Image.open(p).convert('RGBA'))
        except Exception as exc:
            rows.append({'event_id':event.get('event_id'),'decision':'SOURCE_READ_FAILED','detail':str(exc)});continue
        bbox=_ink_bbox(arr);safe=_safe_crop(arr,bbox) if bbox else None
        if safe is None:
            rows.append({'event_id':event.get('event_id'),'decision':'PRESERVE_SOURCE','reason':'NO_CONFIDENT_OUTER_WHITE_PADDING'});continue
        x0,y0,x1,y1=safe;fit=_planned_fit_percent(event,x1-x0,y1-y0)
        if fit is None:
            rows.append({'event_id':event.get('event_id'),'decision':'PRESERVE_SOURCE','reason':'NO_PLANNED_RECT'});continue
        key=hashlib.sha256((str(p.resolve())+'|'+str(p.stat().st_size)+'|'+str(p.stat().st_mtime_ns)+'|'+str(safe)).encode('utf-8')).hexdigest()[:20]
        dst=root/(key+'.png')
        if not dst.is_file():Image.fromarray(arr[y0:y1,x0:x1]).save(dst)
        old_scale=float(event.get('base_fit_scale_percent') or 100.0)
        event['source_path']=str(dst)
        if event.get('source_layer_path'):event['source_layer_path']=str(dst)
        event['base_fit_scale_percent']=round(fit,6)
        event['visible_ink_source_framing']={'version':VERSION,'original_source_path':str(p),'crop_box_px':[x0,y0,x1,y1],'original_size_px':[arr.shape[1],arr.shape[0]],'cropped_size_px':[x1-x0,y1-y0],'old_base_fit_scale_percent':old_scale,'new_base_fit_scale_percent':round(fit,6),'layout_scale_multiplier':float(event.get('layout_scale_multiplier') or 1.0),'policy':'OUTER_WHITE_PADDING_ONLY__NO_BACKGROUND_REMOVAL__NO_FOUNDATION_PARTITIONS'}
        rows.append({'event_id':event.get('event_id'),'decision':'CROP_AND_REFIT_VISIBLE_INK','crop_box_px':[x0,y0,x1,y1],'old_scale':old_scale,'new_scale':round(fit,6)});changed+=1
    report={'schema':'HEXA_VISIBLE_INK_SOURCE_FRAMING_V1','version':VERSION,'pass':True,'event_count':len(out.get('events') or []),'changed_event_count':changed,'rows':rows}
    if logger:logger.log('PASS','VISIBLE_INK_SOURCE_FRAMING',changed_events=changed,total_events=len(out.get('events') or []))
    return out,report
