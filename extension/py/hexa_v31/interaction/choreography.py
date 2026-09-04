from __future__ import annotations
import math
from hexa_v31.preset_authority import duration

_CENTER=(.487,.493);_LEFT=(.183,.493);_RIGHT=(.833,.493)

def _near(point,target,tol=.075):
    return math.hypot(float(point[0])-target[0],float(point[1])-target[1])<=tol

def _state(point):
    if _near(point,_CENTER,.115):return 'MIDDLE'
    if _near(point,_LEFT,.145):return 'LEFT'
    if _near(point,_RIGHT,.145):return 'RIGHT'
    x=float(point[0]);y=float(point[1])
    if .38<=x<=.62 and .14<=y<=.38:return 'UP'
    if .38<=x<=.62 and .62<=y<=.86:return 'DOWN'
    return 'OTHER'

def _has_existing_interaction_action(event:dict)->bool:
    return any(str(a.get('action_type') or '').upper() in {'SEMANTIC_RELATIONSHIP','INTERACTION_DIRECTOR'} for a in (event.get('preset_actions') or []))

def _safe_translation(event:dict)->bool:
    return bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))) and str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT'

def _step(phase,event,preset_name,role):
    return {'phase':phase,'event_id':event['event_id'],'preset':preset_name,'duration_seconds':duration(preset_name),'semantic_role':role}

def _pair_steps(subject,target,subject_state,target_state,action):
    # These templates use only calibrated user-preset endpoints and never teleport an
    # actor from an incompatible start state.  The pair separates or hands focus over
    # rather than converging two objects onto the same center at the same time.
    if subject_state=='MIDDLE' and target_state=='RIGHT':
        return [_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_YIELDS_SPACE'),_step('REACTION',target,'WITHIN_RIGHT_TO_MIDDLE','TARGET_RECEIVES_FOCUS')],'CENTER_RIGHT_HANDOFF'
    if subject_state=='MIDDLE' and target_state=='LEFT':
        return [_step('ACTION',subject,'WITHIN_MIDDLE_TO_RIGHT','SOURCE_YIELDS_SPACE'),_step('REACTION',target,'WITHIN_LEFT_TO_MIDDLE','TARGET_RECEIVES_FOCUS')],'CENTER_LEFT_HANDOFF'
    if subject_state=='LEFT' and target_state=='MIDDLE':
        return [_step('ACTION',subject,'WITHIN_LEFT_TO_MIDDLE','SOURCE_APPROACHES_FOCUS'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_YIELDS_AND_REACTS')],'LEFT_CENTER_EXCHANGE'
    if subject_state=='RIGHT' and target_state=='MIDDLE':
        return [_step('ACTION',subject,'WITHIN_RIGHT_TO_MIDDLE','SOURCE_APPROACHES_FOCUS'),_step('REACTION',target,'WITHIN_MIDDLE_TO_LEFT','TARGET_YIELDS_AND_REACTS')],'RIGHT_CENTER_EXCHANGE'
    if subject_state=='MIDDLE' and target_state=='MIDDLE':
        if action in {'COMPARE','BLOCK','REJECT'}:
            return [_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_ESTABLISHES_CONTRAST'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_ESTABLISHES_COUNTERSTATE')],'CENTER_PAIR_DIVERGENCE'
        return [_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_CREATES_RESULT_SPACE'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_REACTS_IN_RESULT_SPACE')],'CENTER_CAUSAL_DIVERGENCE'
    return [],None

def _focus_steps(subject,state,action):
    if state!='MIDDLE' or not _safe_translation(subject):return [],None
    name='WITHIN_MIDDLE_TO_UP' if action in {'REVEAL','READ','INCREASE'} else 'WITHIN_MIDDLE_TO_DOWN'
    return [_step('ACTION',subject,name,'SEMANTIC_FOCUS_MANIFESTATION')],'CENTER_FOCUS_PUNCTUATION'

def build_choreography_candidate(intent:dict,event_by_id:dict[str,dict],fps:float)->dict:
    subject=event_by_id.get(str(intent['subject_event_id']));target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject:return {'mode':'SAFE_STATIC_FALLBACK','reason':'MISSING_SUBJECT','steps':[]}
    if _has_existing_interaction_action(subject):return {'mode':'BASE_RELATIONSHIP_AUTHORITY','reason':'BASE_PLAN_ALREADY_AUTHORED_RELATIONSHIP_ACTION','steps':[]}
    if not intent.get('actionable'):
        return {'mode':'NON_ACTIONABLE','reason':intent.get('non_actionable_reason') or 'INTENT_NOT_ACTIONABLE','steps':[]}
    subject_state=_state(subject.get('card_rest_position_norm') or [.5,.5]);action=str(intent.get('semantic_action') or '')
    if intent.get('physical_pair_allowed') and target:
        if not _safe_translation(subject):return {'mode':'SAFE_STATIC_FALLBACK','reason':'SUBJECT_TRANSLATION_UNSAFE','steps':[]}
        if not _safe_translation(target):return {'mode':'SAFE_STATIC_FALLBACK','reason':'TARGET_TRANSLATION_UNSAFE','steps':[]}
        target_state=_state(target.get('card_rest_position_norm') or [.5,.5]);steps,template=_pair_steps(subject,target,subject_state,target_state,action)
        if steps:return {'mode':'CAUSAL_PAIR_CHOREOGRAPHY','reason':None,'template':template,'subject_state':subject_state,'target_state':target_state,'steps':steps}
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_PRESET_TEMPLATE_FOR_ACTUAL_PAIR_STATE','subject_state':subject_state,'target_state':target_state,'steps':[]}
    steps,template=_focus_steps(subject,subject_state,action)
    if steps:return {'mode':'FOCUS_MANIFESTATION','reason':None,'template':template,'subject_state':subject_state,'steps':steps}
    return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_SAFE_PRESET_MANIFESTATION_FOR_ACTUAL_STATE','subject_state':subject_state,'steps':[]}
