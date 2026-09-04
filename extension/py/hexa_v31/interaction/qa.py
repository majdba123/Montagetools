from __future__ import annotations
from hexa_v31.preset_authority import authority

def interaction_plan_qa(plan:dict)->dict:
    engine=plan.get('interaction_engine') or {};graph=engine.get('graph') or {};actions=list(engine.get('physical_actions') or [])
    events={str(e.get('event_id')):e for e in plan.get('events') or []}
    allowed=set((authority().get('preset_motion') or {}).keys());fail=[]
    by={}
    for row in actions:
        by.setdefault(str(row.get('interaction_id')),[]).append(row)
        e=events.get(str(row.get('event_id')))
        if not e:fail.append({'reason':'INTERACTION_EVENT_MISSING','action':row});continue
        if str(row.get('preset')) not in allowed:fail.append({'reason':'ILLEGAL_PRESET','action':row})
        st=float(row.get('start_seconds',0));en=float(row.get('end_seconds',st))
        ps=float(e.get('physical_start_seconds',e.get('start_seconds',0)));pe=float(e.get('physical_end_seconds',e.get('end_seconds',ps)))
        if st<ps-1e-6 or en>pe+1e-6:fail.append({'reason':'ACTION_OUTSIDE_PHYSICAL_LIFETIME','action':row})
        if not (row.get('swept_geometry') or {}).get('pass',True):fail.append({'reason':'INTERACTION_PATH_COLLISION','action':row})
    intents={str(x.get('interaction_id')):x for x in (engine.get('intents') or [])}
    for iid,intent in intents.items():
        rows=sorted(by.get(iid,[]),key=lambda x:float(x.get('start_seconds',0)))
        if intent.get('requires_reaction') and rows:
            phases=[str(x.get('phase')) for x in rows]
            if 'ACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_ACTION_PHASE','interaction_id':iid})
            if 'REACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_REACTION','interaction_id':iid})
            a=next((x for x in rows if x.get('phase')=='ACTION'),None);r=next((x for x in rows if x.get('phase')=='REACTION'),None)
            if a and r and float(r['start_seconds'])<float(a['end_seconds'])-1e-6:
                fail.append({'reason':'REACTION_BEFORE_CAUSE','interaction_id':iid})
    orphan=[]
    for e in events.values():
        dep=e.get('interaction_relationship_dependency')
        if not dep:continue
        src=events.get(str(dep.get('source_event_id')));dst=events.get(str(dep.get('target_event_id')))
        if not src or not dst:continue
        es=float(e.get('physical_start_seconds',e.get('start_seconds',0)));ee=float(e.get('physical_end_seconds',e.get('end_seconds',es)))
        os=max(float(src.get('physical_start_seconds',src.get('start_seconds',0))),float(dst.get('physical_start_seconds',dst.get('start_seconds',0))))
        oe=min(float(src.get('physical_end_seconds',src.get('end_seconds',0))),float(dst.get('physical_end_seconds',dst.get('end_seconds',0))))
        if es<os-1e-6 or ee>oe+1e-6:
            orphan.append({'event_id':e.get('event_id'),'interval':[es,ee],'required_overlap':[os,oe]})
    for row in orphan:fail.append({'reason':'ORPHAN_RELATIONSHIP_VISUAL_INTERVAL',**row})
    return {'schema':'HEXA_INTERACTION_PLAN_QA_V2','version':'2.0','pass':bool(graph.get('pass',True)) and not fail,
            'graph_pass':bool(graph.get('pass',True)),'physical_action_count':len(actions),
            'verified_interaction_count':sum(1 for x in by.values() if x),'orphan_relationship_visuals':orphan,
            'failures':fail}
