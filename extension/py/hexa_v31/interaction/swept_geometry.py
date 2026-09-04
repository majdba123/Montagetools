from __future__ import annotations
from hexa_v31.preset_authority import preset,progress

def _event_size(event:dict):
    rect=event.get('planned_rect_norm')
    if rect and len(rect)==4:return max(.01,float(rect[2])),max(.01,float(rect[3]))
    b=event.get('source_bbox_norm') or [0,0,.15,.15]
    scale=float(event.get('layout_scale_multiplier') or 1.0)*float(event.get('reference_camera_scale') or 1.0)
    return max(.01,float(b[2])*scale),max(.01,float(b[3])*scale)

def _box_at(cx,cy,w,h):
    from shapely.geometry import box
    return box(cx-w/2,cy-h/2,cx+w/2,cy+h/2)

def _static_box(event:dict):
    rect=event.get('planned_rect_norm')
    if rect and len(rect)==4:
        return _box_at(float(rect[0])+float(rect[2])/2,float(rect[1])+float(rect[3])/2,float(rect[2]),float(rect[3]))
    c=event.get('card_rest_position_norm') or [.5,.5];w,h=_event_size(event);return _box_at(float(c[0]),float(c[1]),w,h)

def swept_path_report(event:dict,preset_name:str,start_seconds:float,end_seconds:float,all_events:list[dict])->dict:
    try:
        from shapely.ops import unary_union
    except Exception as exc:
        return {'pass':False,'reason':'SHAPELY_UNAVAILABLE','error':str(exc),'conflicts':[]}
    p=preset(preset_name);a=p.get('start_norm') or [.5,.5];b=p.get('end_norm') or [.5,.5];w,h=_event_size(event)
    samples=[]
    for i in range(13):
        q=i/12.0;pg=progress(preset_name,q);cx=float(a[0])+(float(b[0])-float(a[0]))*pg;cy=float(a[1])+(float(b[1])-float(a[1]))*pg
        samples.append(_box_at(cx,cy,w,h))
    swept=unary_union(samples);conflicts=[]
    eid=str(event.get('event_id'))
    for other in all_events:
        if str(other.get('event_id'))==eid or other.get('suppressed_by_card_density'):continue
        os=float(other.get('physical_start_seconds',other.get('start_seconds',0.0)));oe=float(other.get('physical_end_seconds',other.get('end_seconds',os)))
        if oe<=start_seconds+1e-6 or os>=end_seconds-1e-6:continue
        geom=_static_box(other);inter=swept.intersection(geom)
        ratio=float(inter.area)/max(1e-9,min(float(swept.area),float(geom.area)))
        if ratio>.035:
            conflicts.append({'event_id':str(other.get('event_id')),'intersection_ratio':round(ratio,6)})
    return {'pass':not conflicts,'reason':None if not conflicts else 'INTERACTION_PATH_COLLISION',
            'preset':preset_name,'sample_count':len(samples),'swept_area_norm':round(float(swept.area),6),'conflicts':conflicts}
