from __future__ import annotations
import math

def _available_frames(event:dict,fps:float)->tuple[int,int]:
    start=max(float(event.get('physical_start_seconds',event.get('start_seconds',0.0))),float(event.get('settle_seconds',event.get('start_seconds',0.0)))) + 2.0/fps
    end=float(event.get('physical_end_seconds',event.get('end_seconds',start)));px=event.get('preset_exit') or {}
    if px:end=min(end,float(px.get('start_seconds',end))-2.0/fps)
    return int(math.ceil(start*fps-1e-9)),int(math.floor(end*fps+1e-9))

def _reserved_intervals(event:dict,fps:float)->list[tuple[int,int]]:
    rows=[];entry=event.get('preset_entry') or {};name=str(entry.get('name') or '')
    if name:
        st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or 0.0)
        if dd>0:rows.append((int(math.floor(st*fps+1e-9)),int(math.ceil((st+dd)*fps-1e-9))))
    for action in event.get('preset_actions') or []:
        st=float(action.get('start_seconds',0.0));dd=float(action.get('duration_seconds') or 0.0)
        if dd>0:rows.append((int(math.floor(st*fps+1e-9)),int(math.ceil((st+dd)*fps-1e-9))))
    px=event.get('preset_exit') or {};name=str(px.get('name') or '')
    if name:
        st=float(px.get('start_seconds',event.get('end_seconds',0.0)));dd=float(px.get('duration_seconds') or 0.0)
        if dd>0:rows.append((int(math.floor(st*fps+1e-9)),int(math.ceil((st+dd)*fps-1e-9))))
    return rows

def solve_interaction_schedule(intent:dict,candidate:dict,event_by_id:dict[str,dict],fps:float)->dict:
    steps=list(candidate.get('steps') or [])
    if not steps:return {'status':'NO_PHYSICAL_STEPS','solver':'ORTOOLS_CP_SAT','steps':[],'deterministic':True}
    try:from ortools.sat.python import cp_model
    except Exception as exc:return {'status':'SAFE_FALLBACK_DEPENDENCY_UNAVAILABLE','solver':'ORTOOLS_CP_SAT','reason':str(exc),'steps':[],'deterministic':True}
    model=cp_model.CpModel();vars_=[];semantic_hit=float(intent.get('semantic_hit_seconds',0.0));desired=int(round(semantic_hit*fps))
    for index,step in enumerate(steps):
        event=event_by_id.get(str(step['event_id']))
        if not event:return {'status':'SAFE_FALLBACK_EVENT_MISSING','solver':'ORTOOLS_CP_SAT','steps':[],'deterministic':True}
        lo,hi=_available_frames(event,fps);dur=max(1,int(round(float(step['duration_seconds'])*fps)))
        if step.get('not_before_seconds') is not None:lo=max(lo,int(math.ceil(float(step['not_before_seconds'])*fps-1e-9)))
        hi_start=hi-dur
        if hi_start<lo:return {'status':'SAFE_FALLBACK_NO_EVENT_WINDOW','solver':'ORTOOLS_CP_SAT','steps':[],'deterministic':True}
        v=model.NewIntVar(lo,hi_start,'s'+str(index));vars_.append((v,dur,lo,hi_start,event))
        for r0,r1 in _reserved_intervals(event,fps):
            if r1<=lo or r0>=hi_start+dur:continue
            before=model.NewBoolVar(f'before_{index}_{r0}_{r1}');model.Add(v+dur<=r0).OnlyEnforceIf(before);model.Add(v>=r1+1).OnlyEnforceIf(before.Not())
    for (a,adur,_,_,_),(b,_,_,_,_) in zip(vars_,vars_[1:]):model.Add(b>=a+adur+1)
    deviations=[]
    for index,(v,dur,lo,hi,_) in enumerate(vars_):
        explicit=steps[index].get('preferred_start_seconds')
        preferred=int(round(float(explicit)*fps)) if explicit is not None else desired
        preferred=max(preferred,int(math.ceil(float(steps[index].get('not_before_seconds') or 0.0)*fps-1e-9)));target=max(lo,min(hi,preferred));d=model.NewIntVar(0,max(abs(lo-target),abs(hi-target)),'d'+str(index));model.AddAbsEquality(d,v-target);deviations.append(d)
    model.Minimize(sum(d*1000 for d in deviations)+sum(v*(i+1) for i,(v,_,_,_,_) in enumerate(vars_)))
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=0;solver.parameters.max_time_in_seconds=.20;status=solver.Solve(model)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):return {'status':'SAFE_FALLBACK_NO_FEASIBLE_SCHEDULE','solver':'ORTOOLS_CP_SAT','steps':[],'deterministic':True}
    out=[]
    for step,(v,dur,_,_,_) in zip(steps,vars_):
        sf=int(solver.Value(v));ef=sf+dur;out.append({**step,'start_frame':sf,'end_frame':ef,'start_seconds':round(sf/fps,6),'end_seconds':round(ef/fps,6),'duration_frames':dur})
    return {'status':'COMMITTED','solver':'ORTOOLS_CP_SAT','steps':out,'deterministic':True,'random_seed':0,'num_search_workers':1,'objective_value':solver.ObjectiveValue()}
