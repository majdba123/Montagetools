from __future__ import annotations
from hexa_v31.preset_authority import authority
from .contracts import MIN_ACTIONABLE_EMBODIMENT_RATIO

def interaction_plan_qa(plan:dict)->dict:
    engine=plan.get('interaction_engine') or {};graph=engine.get('graph') or {};actions=list(engine.get('physical_actions') or [])
    events={str(e.get('event_id')):e for e in plan.get('events') or []};allowed=set((authority().get('preset_motion') or {}).keys());fail=[];warnings=[];by={}
    for row in actions:
        by.setdefault(str(row.get('interaction_id')),[]).append(row)
        e=events.get(str(row.get('event_id')))
        if not e:fail.append({'reason':'INTERACTION_EVENT_MISSING','action':row});continue
        if str(row.get('preset')) not in allowed:fail.append({'reason':'ILLEGAL_PRESET','action':row})
        st=float(row.get('start_seconds',0));en=float(row.get('end_seconds',st));ps=float(e.get('physical_start_seconds',e.get('start_seconds',0)));pe=float(e.get('physical_end_seconds',e.get('end_seconds',ps)))
        if st<ps-1e-6 or en>pe+1e-6:fail.append({'reason':'ACTION_OUTSIDE_PHYSICAL_LIFETIME','action':row})
        if not (row.get('swept_geometry') or {}).get('pass',True):fail.append({'reason':'INTERACTION_PATH_COLLISION','action':row})
    intents={str(x.get('interaction_id')):x for x in (engine.get('intents') or [])};actionable=[x for x in intents.values() if x.get('actionable')]
    for iid,intent in intents.items():
        rows=sorted(by.get(iid,[]),key=lambda x:float(x.get('start_seconds',0)))
        if not intent.get('actionable'):continue
        if not rows:
            warnings.append({'reason':'ACTIONABLE_INTERACTION_DEGRADED_TO_SAFE_FALLBACK','interaction_id':iid,'semantic_action':intent.get('semantic_action')})
            continue
        phases=[str(x.get('phase')) for x in rows]
        if intent.get('requires_reaction'):
            if 'ACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_ACTION_PHASE','interaction_id':iid})
            if 'REACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_REACTION','interaction_id':iid})
            a=next((x for x in rows if x.get('phase')=='ACTION'),None);r=next((x for x in rows if x.get('phase')=='REACTION'),None)
            if a and r and float(r['start_seconds'])<float(a['end_seconds'])-1e-6:fail.append({'reason':'REACTION_BEFORE_CAUSE','interaction_id':iid})
    actionable_count=len(actionable);embodied=int(engine.get('embodied_interaction_count') or 0);ratio=float(engine.get('embodiment_ratio') or 0.0)
    if actionable_count>0 and embodied==0:fail.append({'reason':'ZERO_ACTIONABLE_INTERACTION_EMBODIMENT','actionable_interaction_count':actionable_count})
    if actionable_count>=2 and ratio+1e-9<MIN_ACTIONABLE_EMBODIMENT_RATIO:
        fail.append({'reason':'ACTIONABLE_EMBODIMENT_RATIO_BELOW_MINIMUM','embodiment_ratio':round(ratio,6),'minimum':MIN_ACTIONABLE_EMBODIMENT_RATIO,'actionable_interaction_count':actionable_count,'embodied_interaction_count':embodied})
    orphan=[]
    for e in events.values():
        dep=e.get('interaction_relationship_dependency')
        if not dep:continue
        src=events.get(str(dep.get('source_event_id')));dst=events.get(str(dep.get('target_event_id')))
        if not src or not dst:continue
        es=float(e.get('physical_start_seconds',e.get('start_seconds',0)));ee=float(e.get('physical_end_seconds',e.get('end_seconds',es)))
        os=max(float(src.get('physical_start_seconds',src.get('start_seconds',0))),float(dst.get('physical_start_seconds',dst.get('start_seconds',0))))
        oe=min(float(src.get('physical_end_seconds',src.get('end_seconds',0))),float(dst.get('physical_end_seconds',dst.get('end_seconds',0))))
        if es<os-1e-6 or ee>oe+1e-6:orphan.append({'event_id':e.get('event_id'),'interval':[es,ee],'required_overlap':[os,oe]})
    for row in orphan:fail.append({'reason':'ORPHAN_RELATIONSHIP_VISUAL_INTERVAL',**row})
    return {'schema':'HEXA_INTERACTION_PLAN_QA_V3','version':'3.0_NO_VACUOUS_GREEN','pass':bool(graph.get('pass',True)) and not fail,
            'graph_pass':bool(graph.get('pass',True)),'logical_interaction_count':len(intents),'actionable_interaction_count':actionable_count,
            'physical_action_count':len(actions),'embodied_interaction_count':embodied,'embodiment_ratio':round(ratio,6),
            'verified_interaction_count':sum(1 for x in by.values() if x),'orphan_relationship_visuals':orphan,
            'warnings':warnings,'failures':fail}
