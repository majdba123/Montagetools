from __future__ import annotations
import copy,collections
from hexa_v31.preset_authority import duration
from hexa_v31.composition_qa import card_motion_conflicts,composition_plan_qa
from .contracts import INTERACTION_ENGINE_VERSION,RELATIONSHIP_VISUAL_TYPES
from .intent_compiler import compile_interaction_intents
from .graph import build_interaction_graph
from .choreography import build_choreography_candidate
from .constraint_solver import solve_interaction_schedule
from .swept_geometry import swept_path_report
from .qa import interaction_plan_qa

def _relationship_visual_guard(intent:dict,event_by_id:dict[str,dict],fps:float)->list[dict]:
    subject=event_by_id.get(str(intent.get('subject_event_id') or ''));target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject or not target:return []
    os=max(float(subject.get('physical_start_seconds',subject.get('start_seconds',0))),float(target.get('physical_start_seconds',target.get('start_seconds',0))))
    oe=min(float(subject.get('physical_end_seconds',subject.get('end_seconds',0))),float(target.get('physical_end_seconds',target.get('end_seconds',0))))
    if oe<=os+2/fps:return []
    changed=[]
    for e in event_by_id.values():
        if str(e.get('scene_id'))!=str(intent.get('scene_id')) or str(e.get('event_id')) in {str(subject.get('event_id')),str(target.get('event_id'))}:continue
        typ=str(e.get('semantic_type') or '').upper()
        if typ not in RELATIONSHIP_VISUAL_TYPES:continue
        hit=float(e.get('perceptual_hit_seconds',-999))
        if not (os-1e-6<=hit<=oe+1e-6):continue
        if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:continue
        old=[float(e.get('physical_start_seconds',e.get('start_seconds',0))),float(e.get('physical_end_seconds',e.get('end_seconds',0)))]
        ns=max(old[0],os);ne=min(old[1],oe)
        if ne<=ns+2/fps:continue
        e['physical_start_seconds']=round(ns,6);e['physical_end_seconds']=round(ne,6);e['visibility_interval_seconds']=[round(ns,6),round(ne,6)]
        e['interaction_relationship_dependency']={'interaction_id':intent['interaction_id'],'source_event_id':subject['event_id'],'target_event_id':target['event_id']}
        e['interaction_orphan_guard']='SOURCE_AND_TARGET_OVERLAP'
        px=e.get('preset_exit') or {}
        if float(px.get('start_seconds',ne))>=ne:
            dd=duration('DISAPPEAR_DOWN_SCALE');xs=max(ns,ne-dd*.60)
            e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':round(xs,6),'duration_seconds':dd,'authority':'HEXA_INTERACTION_ORPHAN_GUARD'}
        changed.append({'event_id':e['event_id'],'old_interval':old,'new_interval':[round(ns,6),round(ne,6)]})
    return changed

def _commit_actions(plan:dict,intent:dict,schedule:dict)->tuple[list[dict],list[dict]]:
    event_by_id={str(e.get('event_id')):e for e in plan.get('events') or []};committed=[];rejected=[]
    target_event=event_by_id.get(str(intent.get('object_event_id') or ''));target_semantic_unit_id=(target_event or {}).get('semantic_unit_id')
    card_id=str(intent.get('visual_card_id'));card=next((c for c in (plan.get('visual_cards') or {}).get('cards',[]) if str(c.get('card_id'))==card_id),None)
    local=[e for e in event_by_id.values() if str(e.get('visual_card_id'))==card_id and not e.get('suppressed_by_card_density')]
    snapshots={str(e.get('event_id')):copy.deepcopy(e) for e in local}
    for step in schedule.get('steps') or []:
        e=event_by_id.get(str(step['event_id']))
        if not e:continue
        geo=swept_path_report(e,str(step['preset']),float(step['start_seconds']),float(step['end_seconds']),local)
        if not geo.get('pass'):
            rejected.append({'interaction_id':intent['interaction_id'],'phase':step['phase'],'reason':geo.get('reason'),'geometry':geo})
            for live in local:
                snap=snapshots[str(live.get('event_id'))];live.clear();live.update(copy.deepcopy(snap))
            return [],rejected
        action={'name':step['preset'],'start_seconds':float(step['start_seconds']),'duration_seconds':float(step['duration_seconds']),
                'authority':'HEXA_INTERACTION_DIRECTOR_V3','action_type':'SEMANTIC_RELATIONSHIP','interaction_id':intent['interaction_id'],
                'interaction_phase':step['phase'],'semantic_action':intent['semantic_action'],'source_event_id':intent['subject_event_id'],
                'target_event_id':intent.get('object_event_id'),'target_semantic_unit_id':target_semantic_unit_id,
                'relationship_evidence':intent.get('evidence'),'relationship_confidence':1.0}
        e.setdefault('preset_actions',[]).append(action);e['preset_actions'].sort(key=lambda x:(float(x.get('start_seconds',0)),str(x.get('name'))))
        action_end=float(step['end_seconds']);e['motion_end_seconds']=round(max(float(e.get('motion_end_seconds',0)),action_end),6)
        e.setdefault('motion_intervals',[]).append({'kind':'ACTION',**action})
        committed.append({**step,'interaction_id':intent['interaction_id'],'semantic_action':intent['semantic_action'],
                          'source_event_id':intent['subject_event_id'],'target_event_id':intent.get('object_event_id'),'swept_geometry':geo})
    if card:
        conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),float(plan.get('fps') or 30))
        if conflicts:
            for live in local:
                snap=snapshots[str(live.get('event_id'))];live.clear();live.update(copy.deepcopy(snap))
            return [],[{'interaction_id':intent['interaction_id'],'reason':'POST_COMMIT_CARD_MOTION_CONFLICT','conflicts':conflicts[:4]}]
    return committed,rejected

def _adopt_existing_manifestation(plan:dict,intent:dict,row:dict)->tuple[dict|None,dict|None]:
    events={str(e.get('event_id')):e for e in plan.get('events') or []};event=events.get(str(row.get('event_id')))
    if not event:return None,{'interaction_id':intent['interaction_id'],'reason':'ADOPTED_MANIFESTATION_EVENT_MISSING'}
    card_id=str(intent.get('visual_card_id') or event.get('visual_card_id') or '')
    local=[e for e in events.values() if str(e.get('visual_card_id'))==card_id and not e.get('suppressed_by_card_density')]
    geo=swept_path_report(event,str(row.get('preset')),float(row.get('start_seconds',0)),float(row.get('end_seconds',0)),local)
    if not geo.get('pass'):
        return None,{'interaction_id':intent['interaction_id'],'reason':'ADOPTED_MANIFESTATION_PATH_COLLISION','phase':row.get('phase'),'geometry':geo}
    target=events.get(str(intent.get('object_event_id') or ''));target_semantic_unit_id=(target or {}).get('semantic_unit_id')
    source_kind=str(row.get('source_kind') or '')
    if source_kind=='PRESET_ACTION':
        for action in event.get('preset_actions') or []:
            if str(action.get('name') or '')==str(row.get('preset') or '') and abs(float(action.get('start_seconds',0))-float(row.get('start_seconds',0)))<=1e-6:
                action['interaction_id']=intent['interaction_id'];action['interaction_phase']=row.get('phase');action['semantic_action']=intent.get('semantic_action')
                action['source_event_id']=intent.get('subject_event_id');action['target_event_id']=intent.get('object_event_id')
                if target_semantic_unit_id:action['target_semantic_unit_id']=target_semantic_unit_id
                action['authority_bridge']='EXISTING_MOTION_TO_INTERACTION_V3';break
    elif source_kind=='PRESET_ENTRY':
        entry=event.get('preset_entry') or {}
        entry['interaction_id']=intent['interaction_id'];entry['interaction_phase']=row.get('phase');entry['semantic_action']=intent.get('semantic_action')
        entry['interaction_authority_bridge']='SEMANTICALLY_ALIGNED_EXISTING_ENTRY'
    return {**row,'interaction_id':intent['interaction_id'],'semantic_action':intent.get('semantic_action'),
            'source_event_id':intent.get('subject_event_id'),'target_event_id':intent.get('object_event_id'),
            'swept_geometry':geo,'adopted_existing_motion':True},None

def _fallback_summary(fallbacks:list[dict])->dict:
    counts=collections.Counter(str(x.get('reason') or 'UNKNOWN') for x in fallbacks)
    return {'count':len(fallbacks),'reason_counts':dict(sorted(counts.items())),'examples':fallbacks[:12]}

def apply_interaction_director(base_plan:dict,source_plan:dict,alignment:dict,fps:float=30.0,logger=None)->dict:
    plan=base_plan;compiled=compile_interaction_intents(plan,source_plan);intents=compiled['intents'];graph=build_interaction_graph(intents)
    event_by_id={str(e.get('event_id')):e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density')}
    physical=[];schedules=[];fallbacks=[];orphan_guards=[];adopted_count=0
    for intent in intents:
        orphan_guards.extend(_relationship_visual_guard(intent,event_by_id,fps))
        candidate=build_choreography_candidate(intent,event_by_id,fps)
        adopted_rows=list(candidate.get('adopted_actions') or [])
        if adopted_rows:
            adopted=[];failed=None
            for row in adopted_rows:
                live,err=_adopt_existing_manifestation(plan,intent,row)
                if err:failed=err;break
                adopted.append(live)
            schedule={'status':'ADOPTED_EXISTING_MOTION' if not failed else 'SAFE_FALLBACK_ADOPTION_FAILED','solver':'FIXED_EXISTING_MOTION','steps':[],
                      'interaction_id':intent['interaction_id'],'candidate_mode':candidate.get('mode'),'candidate_reason':candidate.get('reason'),'candidate_template':candidate.get('template')}
            schedules.append(schedule)
            if failed:fallbacks.append(failed)
            else:physical.extend(adopted);adopted_count+=len(adopted)
            continue
        schedule=solve_interaction_schedule(intent,candidate,event_by_id,fps)
        schedule['interaction_id']=intent['interaction_id'];schedule['candidate_mode']=candidate.get('mode');schedule['candidate_reason']=candidate.get('reason');schedule['candidate_template']=candidate.get('template')
        schedules.append(schedule)
        if schedule.get('status')=='COMMITTED':
            committed,rejected=_commit_actions(plan,intent,schedule)
            if committed:
                adopted=None;adopt_rejection=None
                if candidate.get('adopted_action'):
                    adopted,adopt_rejection=_adopt_existing_manifestation(plan,intent,candidate['adopted_action'])
                if adopt_rejection:fallbacks.append(adopt_rejection)
                elif candidate.get('adopted_action') and not adopted:fallbacks.append({'interaction_id':intent['interaction_id'],'reason':'AUTHORED_CAUSE_ADOPTION_FAILED'})
                else:
                    if adopted:physical.append(adopted);adopted_count+=1
                    physical.extend(committed)
            else:fallbacks.extend(rejected or [{'interaction_id':intent['interaction_id'],'reason':'NO_SAFE_COMMIT'}])
        elif intent.get('actionable'):
            reason=candidate.get('reason') or schedule.get('status') or 'NO_PHYSICAL_STEPS'
            fallbacks.append({'interaction_id':intent['interaction_id'],'reason':reason,'candidate_mode':candidate.get('mode'),
                              'solver_status':schedule.get('status'),'semantic_action':intent.get('semantic_action'),
                              'subject_event_id':intent.get('subject_event_id'),'object_event_id':intent.get('object_event_id')})
    physical_ids=set(str(x['interaction_id']) for x in physical);actionable=[x for x in intents if x.get('actionable')];actionable_ids=set(str(x['interaction_id']) for x in actionable);embodied_ids=physical_ids & actionable_ids
    embodiment_ratio=len(embodied_ids)/max(1,len(actionable_ids));fallback_report=_fallback_summary(fallbacks)
    engine={'schema':'HEXA_INTERACTION_ENGINE_V3','version':INTERACTION_ENGINE_VERSION,'intent_compiler':compiled,'intents':intents,'graph':graph,
            'schedules':schedules,'physical_actions':physical,'safe_fallbacks':fallbacks,'fallback_report':fallback_report,'relationship_orphan_guards':orphan_guards,
            'logical_interaction_count':len(intents),'actionable_interaction_count':len(actionable),'physical_interaction_count':len(physical_ids),
            'embodied_interaction_count':len(embodied_ids),'embodiment_ratio':round(embodiment_ratio,6),'physical_action_count':len(physical),
            'adopted_existing_motion_count':adopted_count,'unembodied_actionable_interaction_ids':sorted(actionable_ids-embodied_ids),
            'ortools_required':True,'shapely_required':True,'deterministic_solver_contract':{'num_search_workers':1,'random_seed':0,'bounded_seconds_per_interaction':.20}}
    plan['interaction_engine']=engine;qa=interaction_plan_qa(plan);plan['interaction_plan_qa']=qa
    plan['final_semantic_timing_composition_qa']=composition_plan_qa({'events':plan.get('events') or [],'visual_cards':plan.get('visual_cards') or {},'fps':fps})
    plan['motion_dna_version']=str(plan.get('motion_dna_version') or 'HEXA_MOTION_DNA_V31')+'__INTERACTION_V3_SHORT_CARD_EMBODIMENT'
    plan.setdefault('hard_invariants',{})['interaction_execution_authority_required']=True;plan['hard_invariants']['interaction_encoded_pixel_verification_required']=True
    plan.setdefault('budget_summary',{})['interaction_logical_count']=engine['logical_interaction_count'];plan['budget_summary']['interaction_actionable_count']=engine['actionable_interaction_count'];plan['budget_summary']['interaction_physical_action_count']=engine['physical_action_count'];plan['budget_summary']['interaction_embodiment_ratio']=engine['embodiment_ratio'];plan['budget_summary']['interaction_adopted_existing_motion_count']=adopted_count
    if logger:
        logger.log('INFO','INTERACTION_EXECUTION_DIAGNOSTICS',logical=engine['logical_interaction_count'],actionable=engine['actionable_interaction_count'],physical_interactions=engine['physical_interaction_count'],physical_actions=engine['physical_action_count'],embodiment_ratio=engine['embodiment_ratio'],adopted_existing_motion=adopted_count,fallbacks=fallback_report['count'],fallback_reasons=fallback_report['reason_counts'])
    if not qa.get('pass'):raise ValueError('INTERACTION_PLAN_QA_FAILED: '+str(qa.get('failures')[:8])+' FALLBACKS='+str(fallback_report))
    if logger:logger.log('PASS','INTERACTION_DIRECTOR_COMPILED',logical=engine['logical_interaction_count'],actionable=engine['actionable_interaction_count'],physical_interactions=engine['physical_interaction_count'],physical_actions=engine['physical_action_count'],embodiment_ratio=engine['embodiment_ratio'],adopted_existing_motion=adopted_count,fallbacks=len(fallbacks))
    return plan

def build_interaction_motion_plan(plan:dict,alignment:dict,vision_results:list[dict],rules_path,reference_path,*,fps:float=30.0,logger=None,calibration:dict|None=None):
    from hexa_v31.motion.motion import build_motion_plan as base_build_motion_plan
    base=base_build_motion_plan(plan,alignment,vision_results,rules_path,reference_path,fps=fps,logger=logger,calibration=calibration)
    return apply_interaction_director(base,plan,alignment,fps=fps,logger=logger)
