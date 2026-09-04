from __future__ import annotations
import math
from hexa_v31.preset_authority import duration

_CENTER=(.487,.493)
_LEFT=(.183,.493)
_RIGHT=(.833,.493)

def _near(point,target,tol=.075):
    return math.hypot(float(point[0])-target[0],float(point[1])-target[1])<=tol

def _side(point):
    if _near(point,_LEFT,.10):return 'LEFT'
    if _near(point,_RIGHT,.10):return 'RIGHT'
    return None

def _has_existing_interaction_action(event:dict)->bool:
    return any(str(a.get('action_type') or '').upper() in {'SEMANTIC_RELATIONSHIP','INTERACTION_DIRECTOR'}
               for a in (event.get('preset_actions') or []))

def build_choreography_candidate(intent:dict,event_by_id:dict[str,dict],fps:float)->dict:
    subject=event_by_id.get(str(intent['subject_event_id']))
    target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject:
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'MISSING_SUBJECT','steps':[]}
    if _has_existing_interaction_action(subject):
        return {'mode':'BASE_RELATIONSHIP_AUTHORITY','reason':'BASE_PLAN_ALREADY_AUTHORED_RELATIONSHIP_ACTION','steps':[]}
    if not intent.get('physical_pair_allowed') or not target:
        return {'mode':'SEMANTIC_FOCUS_ONLY','reason':'NO_EXPLICIT_SAFE_PHYSICAL_PAIR','steps':[]}
    if not bool(subject.get('translation_safe_after_occlusion',subject.get('animation_safe',True))):
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'SUBJECT_TRANSLATION_UNSAFE','steps':[]}
    if not bool(target.get('translation_safe_after_occlusion',target.get('animation_safe',True))):
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'TARGET_TRANSLATION_UNSAFE','steps':[]}
    sp=subject.get('card_rest_position_norm') or [.5,.5]
    tp=target.get('card_rest_position_norm') or [.5,.5]
    if not _near(sp,_CENTER,.075):
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'SUBJECT_NOT_IN_AUTHORIZED_MIDDLE_STATE','steps':[]}
    side=_side(tp)
    if not side:
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'TARGET_NOT_IN_AUTHORIZED_SIDE_STATE','steps':[]}
    if side=='RIGHT':
        source_name='WITHIN_MIDDLE_TO_LEFT';target_name='WITHIN_RIGHT_TO_MIDDLE'
    else:
        source_name='WITHIN_MIDDLE_TO_RIGHT';target_name='WITHIN_LEFT_TO_MIDDLE'
    steps=[
        {'phase':'ACTION','event_id':subject['event_id'],'preset':source_name,
         'duration_seconds':duration(source_name),'semantic_role':'SOURCE_YIELDS_SPACE'},
        {'phase':'REACTION','event_id':target['event_id'],'preset':target_name,
         'duration_seconds':duration(target_name),'semantic_role':'TARGET_RECEIVES_FOCUS'},
    ]
    return {'mode':'YIELD_AND_FOCUS_TRANSFER','reason':None,'target_side':side,'steps':steps}
