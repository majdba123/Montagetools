from __future__ import annotations
from .contracts import InteractionIntent,canonical_action,PHYSICAL_CAUSAL_ACTIONS,FOCUS_ACTIONS

def _event_map(motion_plan:dict)->dict[str,dict]:
    return {str(e.get('event_id')):e for e in motion_plan.get('events') or [] if not e.get('suppressed_by_card_density')}

def _explicit_semantic_evidence(event:dict,action:str)->bool:
    fields=' '.join(str(event.get(k) or '') for k in ('semantic_intent','narrative_function','relationship')).upper()
    if not fields:return False
    signals={
        'TRANSFER':('TRANSFER','SEND','HANDOFF','MOVE'),
        'CONNECT':('CONNECT','LINK','FLOW','RELATION'),
        'BLOCK':('BLOCK','STOP','PREVENT','DENY','LIMIT'),
        'REJECT':('REJECT','FAIL','ERROR','INVALID'),
        'ACCEPT':('ACCEPT','SUCCESS','CONFIRM','VALID','APPROVE'),
        'REACT':('REACT','REACTION','RESPOND'),
    }.get(action,(action,))
    return any(x in fields for x in signals)

def compile_interaction_intents(motion_plan:dict)->dict:
    events=_event_map(motion_plan)
    sentences=((motion_plan.get('semantic_visual_sentence_compiler') or {}).get('sentences') or [])
    rows=[];skipped=[]
    for sentence in sorted(sentences,key=lambda x:(str(x.get('visual_card_id')),str(x.get('sentence_id')))):
        action=canonical_action(sentence.get('action'))
        if action not in PHYSICAL_CAUSAL_ACTIONS|FOCUS_ACTIONS:
            continue
        subject=events.get(str(sentence.get('subject_event_id') or ''))
        obj=events.get(str(sentence.get('object_event_id') or ''))
        result=events.get(str(sentence.get('result_event_id') or ''))
        if not subject:
            skipped.append({'sentence_id':sentence.get('sentence_id'),'reason':'SUBJECT_NOT_PHYSICAL'})
            continue
        confidence=float(sentence.get('confidence') or 0.0)
        mapping_ok=float(subject.get('semantic_mapping_confidence') or 0.0)>=.85
        object_mapping_ok=bool(obj and float(obj.get('semantic_mapping_confidence') or 0.0)>=.85)
        explicit=_explicit_semantic_evidence(subject,action)
        physical_pair_allowed=bool(action in PHYSICAL_CAUSAL_ACTIONS and obj and confidence>=.72 and mapping_ok and object_mapping_ok and explicit)
        evidence='EXPLICIT_FINAL_PACKAGE_SEMANTIC_INTENT' if explicit else 'CANONICAL_CLAUSE_SEMANTIC_SENTENCE'
        hit=float(subject.get('perceptual_hit_seconds',subject.get('start_seconds',0.0)))
        intent=InteractionIntent(
            interaction_id='INT::'+str(sentence.get('sentence_id')),
            sentence_id=str(sentence.get('sentence_id')),
            scene_id=str(sentence.get('scene_id') or subject.get('scene_id') or ''),
            visual_card_id=str(sentence.get('visual_card_id') or subject.get('visual_card_id') or ''),
            semantic_action=action,
            subject_event_id=str(subject.get('event_id')),
            object_event_id=str(obj.get('event_id')) if obj else None,
            result_event_id=str(result.get('event_id')) if result and result is not subject and result is not obj else None,
            semantic_hit_seconds=hit,confidence=confidence,evidence=evidence,
            physical_pair_allowed=physical_pair_allowed,
            requires_reaction=action in PHYSICAL_CAUSAL_ACTIONS,
        )
        rows.append(intent.to_dict())
    return {'schema':'HEXA_INTERACTION_INTENT_SET_V2','version':'2.0','intents':rows,'skipped':skipped,
            'intent_count':len(rows),'physical_pair_candidate_count':sum(bool(x['physical_pair_allowed']) for x in rows)}
