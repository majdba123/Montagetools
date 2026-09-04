from __future__ import annotations
import copy

def _visible_interval(event:dict)->tuple[float,float]:
    start=float(event.get('physical_start_seconds',event.get('start_seconds',0.0)))
    end=float(event.get('physical_end_seconds',event.get('end_seconds',start)))
    readable=float(event.get('semantic_readable_not_before_seconds',start) or start)
    start=max(start,readable)
    px=event.get('preset_exit') or {}
    if px:
        xs=float(px.get('start_seconds',end));dur=max(0.0,float(px.get('duration_seconds') or 0.0))
        end=min(end,xs+dur*.60)
    return start,max(start,end)

def _merged(intervals:list[tuple[float,float]])->list[tuple[float,float]]:
    rows=sorted((a,b) for a,b in intervals if b>a+1e-6);out=[]
    for a,b in rows:
        if not out or a>out[-1][1]+1e-6:out.append([a,b])
        else:out[-1][1]=max(out[-1][1],b)
    return [(float(a),float(b)) for a,b in out]

def _semantic_intervals(motion_plan:dict,scene_id:str,semantic_unit_id:str)->list[tuple[float,float]]:
    return _merged([_visible_interval(e) for e in motion_plan.get('events') or [] if not e.get('suppressed_by_card_density') and str(e.get('scene_id'))==str(scene_id) and str(e.get('semantic_unit_id') or '')==str(semantic_unit_id)])

def _best_overlap(a_rows,b_rows,requested):
    rs,re=requested;best=None
    for a0,a1 in a_rows:
        for b0,b1 in b_rows:
            s=max(rs,a0,b0);e=min(re,a1,b1)
            if e<=s+1e-6:continue
            score=e-s
            if best is None or score>best[0]:best=(score,s,e)
    return None if best is None else (best[1],best[2])

def guard_relationship_graphics(graphics_plan:dict,motion_plan:dict,fps:float=30.0)->dict:
    plan=copy.deepcopy(graphics_plan);kept=[];rows=[];min_duration=max(.18,4.0/max(1.0,float(fps)))
    for event in plan.get('events') or []:
        if str(event.get('kind') or '').upper()!='ARROW' or not event.get('source_semantic_unit_id') or not event.get('target_semantic_unit_id'):
            kept.append(event);continue
        sid=str(event.get('scene_id') or '');src=str(event.get('source_semantic_unit_id'));tgt=str(event.get('target_semantic_unit_id'));old=(float(event.get('start_seconds',0)),float(event.get('end_seconds',0)))
        src_rows=_semantic_intervals(motion_plan,sid,src);tgt_rows=_semantic_intervals(motion_plan,sid,tgt);overlap=_best_overlap(src_rows,tgt_rows,old)
        if overlap is None or overlap[1]-overlap[0]<min_duration:
            rows.append({'graphic_id':event.get('graphic_id'),'scene_id':sid,'source_semantic_unit_id':src,'target_semantic_unit_id':tgt,'old_interval':list(old),'new_interval':None,'decision':'SUPPRESSED_NO_VISIBLE_SOURCE_TARGET_OVERLAP'});continue
        s,e=overlap;event['start_seconds']=round(s,6);event['end_seconds']=round(e,6);event['interaction_orphan_guard']='SOURCE_AND_TARGET_VISIBLE_OVERLAP';event['original_interval_seconds']=[round(old[0],6),round(old[1],6)];kept.append(event);rows.append({'graphic_id':event.get('graphic_id'),'scene_id':sid,'source_semantic_unit_id':src,'target_semantic_unit_id':tgt,'old_interval':[round(old[0],6),round(old[1],6)],'new_interval':[round(s,6),round(e,6)],'decision':'CLAMPED_TO_VISIBLE_SOURCE_TARGET_OVERLAP'})
    plan['events']=kept;plan['event_count']=len(kept);report={'schema':'HEXA_INTERACTION_GRAPHICS_GUARD_V1','version':'1.0','pass':True,'relationship_graphic_count':len(rows),'suppressed_count':sum(x['new_interval'] is None for x in rows),'clamped_count':sum(x['new_interval'] is not None and x['old_interval']!=x['new_interval'] for x in rows),'rows':rows};plan['interaction_graphics_guard']=report;return plan
