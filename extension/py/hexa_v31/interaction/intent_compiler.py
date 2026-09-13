from __future__ import annotations
from .contracts import (
    InteractionIntent, canonical_action, PHYSICAL_CAUSAL_ACTIONS, FOCUS_ACTIONS,
    MIN_SEMANTIC_CONFIDENCE, MIN_MAPPING_CONFIDENCE, MIN_PAIR_CONFIDENCE,
)

def _event_map(motion_plan:dict)->dict[str,dict]:
    return {str(e.get('event_id')):e for e in motion_plan.get('events') or [] if not e.get('suppressed_by_card_density')}

def _explicit_semantic_evidence(event:dict,action:str)->bool:
    fields=' '.join(str(event.get(k) or '') for k in ('canonical_clause','canonical_narration','visual_concept','semantic_intent','narrative_function','relationship')).upper()
    if not fields:return False
    signals={
        'TRANSFER':('TRANSFER','SEND','HANDOFF','MOVE','FLOW'),
        'CONNECT':('CONNECT','LINK','FLOW','RELATION'),
        'BLOCK':('BLOCK','STOP','PREVENT','DENY','LIMIT'),
        'REJECT':('REJECT','FAIL','ERROR','INVALID'),
        'ACCEPT':('ACCEPT','SUCCESS','CONFIRM','VALID','APPROVE'),
        'REACT':('REACT','REACTION','RESPOND'),
        'COMPARE':('COMPARE','COMPARISON','VERSUS','DIFFERENCE','MORE','LESS'),
        'READ':('READ','MEASURE','CHECK','INSPECT','SCAN'),
        'REVEAL':('REVEAL','SHOW','DISCOVER'),
        'INCREASE':('INCREASE','RISE','GROW','HIGHER'),
        'DECREASE':('DECREASE','DROP','REDUCE','LOWER'),
        'RESOLVE':('RESOLVE','RESULT','CONCLUDE','COMPLETE'),
    }.get(action,(action,))
    return any(x in fields for x in signals)

def _explicit_pairs(source_plan:dict)->dict[tuple[str,str,str],str]:
    pairs={}
    for scene in source_plan.get('scenes') or []:
        sid=str(scene.get('scene_id') or '')
        for row in scene.get('visual_progression') or []:
            if not isinstance(row,dict):continue
            targets=[str(x) for x in (row.get('targets') or []) if x]
            for a,b in zip(targets,targets[1:]):
                if a!=b:pairs[(sid,a,b)]='DECLARED_VISUAL_PROGRESSION'
        units={str(u.get('unit_id')):u for u in (scene.get('units') or []) if u.get('unit_id')}
        for uid,u in units.items():
            target=u.get('interaction_target') or u.get('target_unit_id') or u.get('relationship_target')
            if target and str(target) in units and str(target)!=uid:
                pairs[(sid,uid,str(target))]='EXPLICIT_INTERACTION_TARGET'
    return pairs

def _pair_authority(sentence:dict,subject:dict,obj:dict|None,explicit_pairs:dict)->tuple[str,float]:
    if not obj:return 'NO_OBJECT',0.0
    sid=str(sentence.get('scene_id') or subject.get('scene_id') or '')
    suid=str(subject.get('semantic_unit_id') or '')
    ouid=str(obj.get('semantic_unit_id') or '')
    if suid and ouid and suid==ouid:return 'SAME_SEMANTIC_UNIT',0.0
    package=explicit_pairs.get((sid,suid,ouid))
    if package:return package,1.0
    sentence_conf=float(sentence.get('confidence') or 0.0)
    sentence_explicit=bool(sentence.get('subject_event_id') and sentence.get('object_event_id') and sentence.get('physical_support'))
    same_card=str(subject.get('visual_card_id') or '')==str(obj.get('visual_card_id') or '')
    distinct_scope=str(subject.get('semantic_scope_id') or subject.get('event_id'))!=str(obj.get('semantic_scope_id') or obj.get('event_id'))
    distinct_semantic_unit=bool(suid and ouid and suid!=ouid)
    if sentence_explicit and same_card and distinct_scope and distinct_semantic_unit and sentence_conf>=MIN_PAIR_CONFIDENCE:
        return 'SEMANTIC_SENTENCE_EXPLICIT_PAIR',sentence_conf
    return 'INSUFFICIENT_PAIR_AUTHORITY',sentence_conf

def _physically_addressable(event:dict|None)->bool:
    if not event:return False
    if event.get('suppressed_by_card_density'):return False
    ps=float(event.get('physical_start_seconds',event.get('start_seconds',0.0)));pe=float(event.get('physical_end_seconds',event.get('end_seconds',ps)))
    if pe<=ps+1e-6:return False
    return bool(event.get('source_path') or event.get('source_layer_path') or event.get('render_mode'))

def _ambiguous_partition_focus(subject:dict,events:dict[str,dict])->bool:
    mode=str(subject.get('render_mode') or '').upper()
    if mode not in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:return False
    sid=str(subject.get('scene_id') or '');cid=str(subject.get('visual_card_id') or '');semantic_unit_id=str(subject.get('semantic_unit_id') or '');partition_root_id=str(subject.get('partition_root_id') or subject.get('root_id') or '')
    if not semantic_unit_id:return True
    cohort=[]
    for event in events.values():
        if str(event.get('render_mode') or '').upper() not in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:continue
        if str(event.get('scene_id') or '')!=sid or str(event.get('visual_card_id') or '')!=cid:continue
        if str(event.get('semantic_unit_id') or '')!=semantic_unit_id:continue
        other_root=str(event.get('partition_root_id') or event.get('root_id') or '')
        if partition_root_id and other_root and other_root!=partition_root_id:continue
        cohort.append(event)
    return len(cohort)>1

def _causal_direction(action:str,subject:dict,obj:dict|None)->tuple[str|None,str|None,str]:
    subject_id=str(subject.get('event_id')) if subject else None;object_id=str(obj.get('event_id')) if obj else None
    # SemanticVisualSentenceCompiler resolves REACT from the subject's own canonical
    # semantics. The subject is therefore the reactor; the paired object is the
    # stimulus/cause. Other causal verbs remain subject -> object.
    if action=='REACT' and object_id:return object_id,subject_id,'OBJECT_CAUSES_SUBJECT_REACTION'
    return subject_id,object_id,'SUBJECT_CAUSES_OBJECT_REACTION'

def compile_interaction_intents(motion_plan:dict,source_plan:dict|None=None)->dict:
    events=_event_map(motion_plan);source_plan=source_plan or {};explicit_pairs=_explicit_pairs(source_plan);sentences=((motion_plan.get('semantic_visual_sentence_compiler') or {}).get('sentences') or []);rows=[];skipped=[]
    for sentence in sorted(sentences,key=lambda x:(str(x.get('visual_card_id')),str(x.get('sentence_id')))):
        action=canonical_action(sentence.get('action'))
        if action not in PHYSICAL_CAUSAL_ACTIONS|FOCUS_ACTIONS:continue
        subject=events.get(str(sentence.get('subject_event_id') or ''));obj=events.get(str(sentence.get('object_event_id') or ''));result=events.get(str(sentence.get('result_event_id') or ''))
        if not subject:
            skipped.append({'sentence_id':sentence.get('sentence_id'),'reason':'SUBJECT_NOT_PHYSICAL'});continue
        confidence=float(sentence.get('confidence') or 0.0);subject_mapping=float(subject.get('semantic_mapping_confidence') or 0.0);object_mapping=float((obj or {}).get('semantic_mapping_confidence') or 0.0);semantic_explicit=_explicit_semantic_evidence(subject,action);pair_authority,pair_confidence=_pair_authority(sentence,subject,obj,explicit_pairs);pair_addressable=_physically_addressable(subject) and _physically_addressable(obj);mapping_ok=subject_mapping>=MIN_MAPPING_CONFIDENCE and (obj is None or object_mapping>=MIN_MAPPING_CONFIDENCE);causal=action in PHYSICAL_CAUSAL_ACTIONS;focus=action in FOCUS_ACTIONS;partition_focus_ambiguous=bool(focus and _ambiguous_partition_focus(subject,events));physical_pair_allowed=bool(causal and obj and confidence>=MIN_SEMANTIC_CONFIDENCE and mapping_ok and semantic_explicit and pair_addressable and pair_confidence>=MIN_PAIR_CONFIDENCE);focus_allowed=bool(focus and confidence>=MIN_SEMANTIC_CONFIDENCE and subject_mapping>=MIN_MAPPING_CONFIDENCE and _physically_addressable(subject) and not partition_focus_ambiguous);actionable=bool(physical_pair_allowed or focus_allowed);reason=None
        if not actionable:
            if confidence<MIN_SEMANTIC_CONFIDENCE:reason='LOW_SEMANTIC_CONFIDENCE'
            elif partition_focus_ambiguous:reason='PARTITION_SEMANTIC_AMBIGUITY'
            elif not mapping_ok:reason='LOW_MAPPING_CONFIDENCE'
            elif causal and not obj:reason='MISSING_OBJECT'
            elif causal and not semantic_explicit:reason='NO_EXPLICIT_SEMANTIC_ACTION'
            elif causal and pair_confidence<MIN_PAIR_CONFIDENCE:reason='INSUFFICIENT_PAIR_AUTHORITY'
            elif causal and not pair_addressable:reason='PAIR_NOT_PHYSICALLY_ADDRESSABLE'
            else:reason='NO_SAFE_ACTIONABLE_MANIFESTATION'
        evidence=pair_authority+'__'+action if actionable else (pair_authority+'__'+(reason or 'NON_ACTIONABLE'));hit=float(subject.get('perceptual_hit_seconds',subject.get('start_seconds',0.0)));intent=InteractionIntent(interaction_id='INT::'+str(sentence.get('sentence_id')),sentence_id=str(sentence.get('sentence_id')),scene_id=str(sentence.get('scene_id') or subject.get('scene_id') or ''),visual_card_id=str(sentence.get('visual_card_id') or subject.get('visual_card_id') or ''),semantic_action=action,subject_event_id=str(subject.get('event_id')),object_event_id=str(obj.get('event_id')) if obj else None,result_event_id=str(result.get('event_id')) if result and result is not subject and result is not obj else None,semantic_hit_seconds=hit,confidence=confidence,evidence=evidence,pair_authority=pair_authority,pair_confidence=round(pair_confidence,3),physical_pair_allowed=physical_pair_allowed,actionable=actionable,non_actionable_reason=reason,requires_reaction=causal)
        row=intent.to_dict();cause,reaction,direction=_causal_direction(action,subject,obj);row['causal_source_event_id']=cause;row['causal_target_event_id']=reaction;row['causal_direction']=direction;rows.append(row)
    return {'schema':'HEXA_INTERACTION_INTENT_SET_V3','version':'3.2_EXPLICIT_CAUSAL_DIRECTION','intents':rows,'skipped':skipped,'explicit_pair_count':len(explicit_pairs),'intent_count':len(rows),'actionable_intent_count':sum(bool(x['actionable']) for x in rows),'physical_pair_candidate_count':sum(bool(x['physical_pair_allowed']) for x in rows),'pair_authority_counts':{k:sum(x['pair_authority']==k for x in rows) for k in sorted(set(x['pair_authority'] for x in rows))},'partition_semantic_ambiguity_count':sum(x.get('non_actionable_reason')=='PARTITION_SEMANTIC_AMBIGUITY' for x in rows),'react_reverse_direction_count':sum(x.get('causal_direction')=='OBJECT_CAUSES_SUBJECT_REACTION' for x in rows)}
