from __future__ import annotations
from hexa_v31.preset_authority import authority
from .contracts import MIN_ACTIONABLE_EMBODIMENT_RATIO

SEMANTIC_PROMOTION_REASON='REACT_SOURCE_INTERVAL_FALLBACK_PROMOTED_TO_SEMANTIC_HIT'

def interaction_plan_qa(plan:dict)->dict:
    engine=plan.get('interaction_engine') or {};graph=engine.get('graph') or {};actions=list(engine.get('physical_actions') or []);events={str(e.get('event_id')):e for e in plan.get('events') or []};allowed=set((authority().get('preset_motion') or {}).keys());fail=[];warnings=[];by={};fps=float(plan.get('fps') or 30.0);intents={str(x.get('interaction_id')):x for x in (engine.get('intents') or [])}
    for row in actions:
        iid=str(row.get('interaction_id'));by.setdefault(iid,[]).append(row);e=events.get(str(row.get('event_id')))
        if not e:fail.append({'reason':'INTERACTION_EVENT_MISSING','action':row});continue
        if str(row.get('preset')) not in allowed:fail.append({'reason':'ILLEGAL_PRESET','action':row})
        st=float(row.get('start_seconds',0));en=float(row.get('end_seconds',st));ps=float(e.get('physical_start_seconds',e.get('start_seconds',0)));pe=float(e.get('physical_end_seconds',e.get('end_seconds',ps)))
        if st<ps-1e-6 or en>pe+1e-6:fail.append({'reason':'ACTION_OUTSIDE_PHYSICAL_LIFETIME','action':row})
        if not (row.get('swept_geometry') or {}).get('pass',True):fail.append({'reason':'INTERACTION_PATH_COLLISION','action':row})
        if row.get('retime_existing_entry'):
            if str(row.get('source_kind') or '')!='PRESET_ENTRY':fail.append({'reason':'RETIME_NON_ENTRY_FORBIDDEN','action':row})
            if 'TRANSLATE' in set(row.get('required_operations') or []):fail.append({'reason':'RETIME_TRANSLATION_FORBIDDEN','action':row})
            entry=e.get('preset_entry') or {};reason=str(row.get('retime_reason') or '')
            if str(entry.get('name') or '')!=str(row.get('preset') or '') or abs(float(entry.get('start_seconds',st))-st)>1e-5:fail.append({'reason':'RETIME_NOT_APPLIED_TO_RENDER_ENTRY','action':row,'entry':entry})
            original=float(row.get('original_start_seconds',st))
            if reason==SEMANTIC_PROMOTION_REASON:
                intent=intents.get(iid) or {};semantic_hit=float(intent.get('semantic_hit_seconds',row.get('perceptual_impact_seconds',st)))
                if str(row.get('phase') or '')!='REACTION' or str(row.get('semantic_action') or intent.get('semantic_action') or '')!='REACT':fail.append({'reason':'SEMANTIC_PROMOTION_ONLY_VALID_FOR_REACT_REACTION','action':row})
                if st<=original+1e-6:fail.append({'reason':'SEMANTIC_PROMOTION_DID_NOT_MOVE_REACTION_LATER','action':row})
                if str(entry.get('semantic_promotion_authority') or '')!=SEMANTIC_PROMOTION_REASON:fail.append({'reason':'SEMANTIC_PROMOTION_NOT_COMMITTED_TO_RENDER_ENTRY','action':row,'entry':entry})
                if abs(float(row.get('perceptual_impact_seconds',semantic_hit))-semantic_hit)*fps>6.0+1e-6:fail.append({'reason':'SEMANTIC_PROMOTION_MISSED_SEMANTIC_HIT','interaction_id':iid,'semantic_hit_seconds':semantic_hit,'perceptual_impact_seconds':row.get('perceptual_impact_seconds')})
            else:
                if original<=st+1e-6:fail.append({'reason':'CAUSAL_PREROLL_DID_NOT_MOVE_EARLIER','action':row})
    actionable=[x for x in intents.values() if x.get('actionable')]
    for iid,intent in intents.items():
        rows=sorted(by.get(iid,[]),key=lambda x:float(x.get('start_seconds',0)))
        if not intent.get('actionable'):continue
        if not rows:
            warnings.append({'reason':'ACTIONABLE_INTERACTION_DEGRADED_TO_SAFE_FALLBACK','interaction_id':iid,'semantic_action':intent.get('semantic_action')});continue
        phases=[str(x.get('phase')) for x in rows]
        if intent.get('requires_reaction'):
            if 'ACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_ACTION_PHASE','interaction_id':iid})
            if 'REACTION' not in phases:fail.append({'reason':'ACTION_WITHOUT_REACTION','interaction_id':iid})
            a=next((x for x in rows if x.get('phase')=='ACTION'),None);r=next((x for x in rows if x.get('phase')=='REACTION'),None)
            if a and r and float(r['start_seconds'])<float(a['end_seconds'])+1.0/max(1.0,fps)-1e-6:fail.append({'reason':'REACTION_BEFORE_CAUSAL_FRAME_GAP','interaction_id':iid,'action_end_seconds':a.get('end_seconds'),'reaction_start_seconds':r.get('start_seconds')})
            expected_cause=str(intent.get('causal_source_event_id') or intent.get('subject_event_id') or '');expected_reaction=str(intent.get('causal_target_event_id') or intent.get('object_event_id') or '')
            if a and expected_cause and str(a.get('event_id'))!=expected_cause:fail.append({'reason':'CAUSAL_ACTION_ACTOR_MISMATCH','interaction_id':iid,'expected_event_id':expected_cause,'actual_event_id':a.get('event_id'),'causal_direction':intent.get('causal_direction')})
            if r and expected_reaction and str(r.get('event_id'))!=expected_reaction:fail.append({'reason':'CAUSAL_REACTION_ACTOR_MISMATCH','interaction_id':iid,'expected_event_id':expected_reaction,'actual_event_id':r.get('event_id'),'causal_direction':intent.get('causal_direction')})
    actionable_count=len(actionable);embodied=int(engine.get('embodied_interaction_count') or 0);ratio=float(engine.get('embodiment_ratio') or 0.0)
    if actionable_count>0 and embodied==0:fail.append({'reason':'ZERO_ACTIONABLE_INTERACTION_EMBODIMENT','actionable_interaction_count':actionable_count})
    if actionable_count>=2 and ratio+1e-9<MIN_ACTIONABLE_EMBODIMENT_RATIO:fail.append({'reason':'ACTIONABLE_EMBODIMENT_RATIO_BELOW_MINIMUM','embodiment_ratio':round(ratio,6),'minimum':MIN_ACTIONABLE_EMBODIMENT_RATIO,'actionable_interaction_count':actionable_count,'embodied_interaction_count':embodied})
    orphan=[]
    for e in events.values():
        dep=e.get('interaction_relationship_dependency')
        if not dep:continue
        src=events.get(str(dep.get('source_event_id')));dst=events.get(str(dep.get('target_event_id')))
        if not src or not dst:continue
        es=float(e.get('physical_start_seconds',e.get('start_seconds',0)));ee=float(e.get('physical_end_seconds',e.get('end_seconds',es)));os=max(float(src.get('physical_start_seconds',src.get('start_seconds',0))),float(dst.get('physical_start_seconds',dst.get('start_seconds',0))));oe=min(float(src.get('physical_end_seconds',src.get('end_seconds',0))),float(dst.get('physical_end_seconds',dst.get('end_seconds',0))))
        if es<os-1e-6 or ee>oe+1e-6:orphan.append({'event_id':e.get('event_id'),'interval':[es,ee],'required_overlap':[os,oe]})
    for row in orphan:fail.append({'reason':'ORPHAN_RELATIONSHIP_VISUAL_INTERVAL',**row})
    return {'schema':'HEXA_INTERACTION_PLAN_QA_V3','version':'3.3_CAUSAL_PREROLL_AND_SEMANTIC_PROMOTION','pass':bool(graph.get('pass',True)) and not fail,'graph_pass':bool(graph.get('pass',True)),'logical_interaction_count':len(intents),'actionable_interaction_count':actionable_count,'physical_action_count':len(actions),'embodied_interaction_count':embodied,'embodiment_ratio':round(ratio,6),'verified_interaction_count':sum(1 for x in by.values() if x),'retimed_existing_motion_count':sum(bool(x.get('retime_existing_entry')) for x in actions),'semantic_promoted_reaction_count':sum(str(x.get('retime_reason') or '')==SEMANTIC_PROMOTION_REASON for x in actions),'orphan_relationship_visuals':orphan,'warnings':warnings,'failures':fail}
