from __future__ import annotations
from hexa_v31.preset_authority import preset,progress,scale

def _event_size(event:dict):
    rect=event.get('planned_rect_norm')
    if rect and len(rect)==4:return max(.01,float(rect[2])),max(.01,float(rect[3]))
    b=event.get('source_bbox_norm') or [0,0,.15,.15];s=float(event.get('layout_scale_multiplier') or 1.0)*float(event.get('reference_camera_scale') or 1.0)
    return max(.01,float(b[2])*s),max(.01,float(b[3])*s)

def _box_at(cx,cy,w,h):
    from shapely.geometry import box
    return box(cx-w/2,cy-h/2,cx+w/2,cy+h/2)

def _rest_center(event:dict):
    rect=event.get('planned_rect_norm')
    if rect and len(rect)==4:return float(rect[0])+float(rect[2])/2,float(rect[1])+float(rect[3])/2
    c=event.get('card_rest_position_norm') or [.5,.5];return float(c[0]),float(c[1])

def _event_center_at(event:dict,t:float):
    center=_rest_center(event)
    entry=event.get('preset_entry') or {};ename=str(entry.get('name') or '')
    if ename:
        definition=preset(ename);family=str(definition.get('family') or '')
        st=float(entry.get('start_seconds',event.get('start_seconds',0)));dur=max(1e-6,float(entry.get('duration_seconds') or definition.get('duration_seconds') or .8))
        if family in {'ENTRY_EXIT','WITHIN_FRAME'} and t>=st:
            a=definition.get('start_norm') or center;b=definition.get('end_norm') or center
            if t>=st+dur:center=(float(b[0]),float(b[1]))
            else:
                q=max(0.,min(1.,(t-st)/dur));pg=progress(ename,q);center=(float(a[0])+(float(b[0])-float(a[0]))*pg,float(a[1])+(float(b[1])-float(a[1]))*pg)
    for action in sorted(event.get('preset_actions') or [],key=lambda x:(float(x.get('start_seconds',0)),str(x.get('name') or ''))):
        name=str(action.get('name') or '');definition=preset(name)
        if str(definition.get('family') or '')!='WITHIN_FRAME':continue
        st=float(action.get('start_seconds',0));dur=max(1e-6,float(action.get('duration_seconds') or definition.get('duration_seconds') or .9))
        if t<st:continue
        a=definition.get('start_norm') or center;b=definition.get('end_norm') or center
        if t>=st+dur:center=(float(b[0]),float(b[1]));continue
        q=max(0.,min(1.,(t-st)/dur));pg=progress(name,q);center=(float(a[0])+(float(b[0])-float(a[0]))*pg,float(a[1])+(float(b[1])-float(a[1]))*pg)
    return center

def swept_path_report(event:dict,preset_name:str,start_seconds:float,end_seconds:float,all_events:list[dict])->dict:
    try:
        from shapely.ops import unary_union
    except Exception as exc:
        return {'pass':False,'reason':'SHAPELY_UNAVAILABLE','error':str(exc),'conflicts':[]}
    definition=preset(preset_name);family=str(definition.get('family') or '');a=definition.get('start_norm') or [.5,.5];b=definition.get('end_norm') or [.5,.5];w,h=_event_size(event);sample_count=17;samples=[];conflict_by_id={};eid=str(event.get('event_id'))
    for i in range(sample_count):
        q=i/float(sample_count-1);t=float(start_seconds)+(float(end_seconds)-float(start_seconds))*q;pg=progress(preset_name,q)
        if family in {'ENTRY_EXIT','WITHIN_FRAME'}:
            cx=float(a[0])+(float(b[0])-float(a[0]))*pg;cy=float(a[1])+(float(b[1])-float(a[1]))*pg;motion_scale=1.0
        else:
            cx,cy=_event_center_at(event,t);motion_scale=max(.01,float(scale(preset_name,q)))
        moving=_box_at(cx,cy,w*motion_scale,h*motion_scale);samples.append(moving)
        for other in all_events:
            oid=str(other.get('event_id'))
            if oid==eid or other.get('suppressed_by_card_density'):continue
            os=float(other.get('physical_start_seconds',other.get('start_seconds',0.0)));oe=float(other.get('physical_end_seconds',other.get('end_seconds',os)))
            if not (os-1e-6<=t<oe-1e-6):continue
            ow,oh=_event_size(other);ocx,ocy=_event_center_at(other,t);geom=_box_at(ocx,ocy,ow,oh);inter=moving.intersection(geom);ratio=float(inter.area)/max(1e-9,min(float(moving.area),float(geom.area)))
            if ratio>.035:
                prev=conflict_by_id.get(oid)
                if prev is None or ratio>prev['intersection_ratio']:
                    conflict_by_id[oid]={'event_id':oid,'intersection_ratio':round(ratio,6),'time_seconds':round(t,6)}
    swept=unary_union(samples);conflicts=[conflict_by_id[k] for k in sorted(conflict_by_id)]
    return {'pass':not conflicts,'reason':None if not conflicts else 'INTERACTION_PATH_COLLISION','preset':preset_name,'family':family,'sample_count':sample_count,'temporal_geometry':True,'swept_area_norm':round(float(swept.area),6),'conflicts':conflicts}
