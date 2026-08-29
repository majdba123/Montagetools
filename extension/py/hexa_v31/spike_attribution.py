from __future__ import annotations
from .util import write_json


def _candidate_events(motion_plan:dict):
    rows=[]
    for s in motion_plan.get('scenes') or []:
        sid=str(s.get('scene_id'));st=float(s.get('start_seconds',0));en=float(s.get('end_seconds',st))
        rows.append((st,sid,'SCENE_START',str((s.get('transition') or {}).get('mode') or '')))
        rows.append((en,sid,'SCENE_END',''))
    for e in motion_plan.get('events') or []:
        sid=str(e.get('scene_id'));eid=str(e.get('event_id'))
        rows.extend([
            (float(e.get('start_seconds',0)),sid,'ELEMENT_APPEAR_START',eid),
            (float(e.get('settle_seconds',0)),sid,'ELEMENT_APPEAR_SETTLE',eid),
            (float(e.get('exit_start_seconds',0)),sid,'ELEMENT_EXIT_START',eid),
        ])
        for a in e.get('story_actions') or []:
            rows.append((float(a.get('start_seconds',0)),sid,'STORY_ACTION_START',eid+':'+str(a.get('kind'))))
            rows.append((float(a.get('end_seconds',0)),sid,'STORY_ACTION_END',eid+':'+str(a.get('kind'))))
    return rows


def attribute_spikes(metrics:dict,motion_plan:dict,out_json=None,window_seconds:float=0.12)->dict:
    """Attribute physical severe-frame spikes to the nearest planned boundary/action.

    This is diagnostic only; it never changes the current render. It closes V26's blind
    spike counter by telling the next review exactly whether a spike came from a scene
    boundary, element appearance, exit, or story-action boundary.
    """
    candidates=_candidate_events(motion_plan);rows=[]
    for t in metrics.get('severe_isolated_motion_spike_times_seconds') or []:
        best=None
        for ct,sid,kind,detail in candidates:
            d=abs(float(t)-float(ct))
            if best is None or d<best[0]:best=(d,ct,sid,kind,detail)
        if best and best[0]<=window_seconds:
            rows.append({'time_seconds':float(t),'attributed':True,'delta_seconds':round(best[0],6),'planned_time_seconds':round(best[1],6),'scene_id':best[2],'cause_class':best[3],'detail':best[4]})
        else:
            rows.append({'time_seconds':float(t),'attributed':False,'cause_class':'UNATTRIBUTED_INTERNAL_RENDER_CHANGE'})
    by={}
    for r in rows:by[r['cause_class']]=by.get(r['cause_class'],0)+1
    result={'schema':'HEXA_V31_SPIKE_ATTRIBUTION','version':'1.0','severe_spike_count':len(rows),'attributed_count':sum(1 for r in rows if r.get('attributed')),'by_cause_class':by,'rows':rows,'window_seconds':window_seconds,'authority':'ACTUAL_FINAL_MP4_PLUS_SINGLE_MOTION_PLAN','metric_autotuning':False}
    if out_json:write_json(out_json,result)
    return result
