from __future__ import annotations
import math
from hexa_v31.preset_authority import duration,preset

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

def _apply_preset_endpoint(point,name):
    if not name:return point
    d=preset(name);end=d.get('end_norm')
    if str(d.get('family') or '') in {'ENTRY_EXIT','WITHIN_FRAME'} and isinstance(end,(list,tuple)) and len(end)>=2:
        return [float(end[0]),float(end[1])]
    return point

def _point_through(event:dict,cutoff_seconds:float|None=None):
    """Rendered object position after authored transforms completed by ``cutoff``.

    Layout rest is only a placement hint. Entry and within-frame preset endpoints are
    the actual rendered state. A cutoff is used for authority bridging so a reaction
    chains from the state that exists after the already-authored cause, not from a
    later unrelated action on the same event.
    """
    point=list(event.get('card_rest_position_norm') or [.5,.5]);cutoff=float('inf') if cutoff_seconds is None else float(cutoff_seconds)
    entry=event.get('preset_entry') or {};name=str(entry.get('name') or '')
    if name:
        st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name))
        if st+dd<=cutoff+1e-6:point=_apply_preset_endpoint(point,name)
    for action in sorted((event.get('preset_actions') or []),key=lambda x:(float(x.get('start_seconds',0)),str(x.get('name') or ''))):
        name=str(action.get('name') or '')
        if not name:continue
        st=float(action.get('start_seconds',0.0));dd=float(action.get('duration_seconds') or duration(name))
        if st+dd<=cutoff+1e-6:point=_apply_preset_endpoint(point,name)
    return point

def _settled_point(event:dict):
    return _point_through(event,None)

def _matching_existing_relationship_action(event:dict,intent:dict,target:dict|None):
    if not target:return None
    target_semantic=str(target.get('semantic_unit_id') or '')
    target_event=str(target.get('event_id') or '')
    hit=float(intent.get('semantic_hit_seconds',event.get('perceptual_hit_seconds',0.0)))
    rows=[]
    for action in event.get('preset_actions') or []:
        if str(action.get('action_type') or '').upper() not in {'SEMANTIC_RELATIONSHIP','INTERACTION_DIRECTOR'}:continue
        action_target_semantic=str(action.get('target_semantic_unit_id') or '')
        action_target_event=str(action.get('target_event_id') or '')
        if action_target_semantic and target_semantic and action_target_semantic!=target_semantic:continue
        if action_target_event and target_event and action_target_event!=target_event:continue
        if not action_target_semantic and not action_target_event:continue
        name=str(action.get('name') or '')
        if not name:continue
        st=float(action.get('start_seconds',0.0));dd=float(action.get('duration_seconds') or duration(name));en=st+dd
        rows.append((abs(st-hit),st,name,en,action))
    if not rows:return None
    _,st,name,en,action=sorted(rows,key=lambda x:(x[0],x[1],x[2]))[0]
    return {'event_id':str(event.get('event_id')),'preset':name,'start_seconds':round(st,6),'end_seconds':round(en,6),
            'duration_seconds':round(en-st,6),'phase':'ACTION','semantic_role':'BASE_AUTHORED_CAUSE',
            'authority':str(action.get('authority') or 'BASE_RELATIONSHIP_AUTHORITY'),
            'original_relationship_evidence':action.get('relationship_evidence'),
            'key':'|'.join((str(event.get('event_id')),name,f'{st:.6f}',target_semantic or target_event))}

def _safe_translation(event:dict)->bool:
    return bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))) and str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT'

def _step(phase,event,preset_name,role,**extra):
    return {'phase':phase,'event_id':event['event_id'],'preset':preset_name,'duration_seconds':duration(preset_name),'semantic_role':role,**extra}

def _reaction_step(target,target_state,source_end_point,not_before):
    if target_state=='RIGHT':name='WITHIN_RIGHT_TO_MIDDLE'
    elif target_state=='LEFT':name='WITHIN_LEFT_TO_MIDDLE'
    elif target_state=='MIDDLE':
        sx=float(source_end_point[0]);sy=float(source_end_point[1])
        if sx<.46:name='WITHIN_MIDDLE_TO_RIGHT'
        elif sx>.54:name='WITHIN_MIDDLE_TO_LEFT'
        elif sy<.42:name='WITHIN_MIDDLE_TO_DOWN'
        else:name='WITHIN_MIDDLE_TO_UP'
    else:return None
    return _step('REACTION',target,name,'TARGET_REACTS_TO_AUTHORED_CAUSE',not_before_seconds=round(float(not_before),6))

def _pair_steps(subject,target,subject_state,target_state,action):
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
    if not _safe_translation(subject):return [],None
    if state=='LEFT':return [_step('ACTION',subject,'WITHIN_LEFT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'LEFT_TO_FOCUS'
    if state=='RIGHT':return [_step('ACTION',subject,'WITHIN_RIGHT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'RIGHT_TO_FOCUS'
    if state=='MIDDLE':
        name='WITHIN_MIDDLE_TO_UP' if action in {'REVEAL','READ','INCREASE'} else 'WITHIN_MIDDLE_TO_DOWN'
        return [_step('ACTION',subject,name,'SEMANTIC_FOCUS_PUNCTUATION')],'CENTER_FOCUS_PUNCTUATION'
    return [],None

def build_choreography_candidate(intent:dict,event_by_id:dict[str,dict],fps:float)->dict:
    subject=event_by_id.get(str(intent['subject_event_id']));target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject:return {'mode':'SAFE_STATIC_FALLBACK','reason':'MISSING_SUBJECT','steps':[]}
    if not intent.get('actionable'):return {'mode':'NON_ACTIONABLE','reason':intent.get('non_actionable_reason') or 'INTENT_NOT_ACTIONABLE','steps':[]}
    action=str(intent.get('semantic_action') or '')
    if intent.get('physical_pair_allowed') and target:
        if not _safe_translation(subject):return {'mode':'SAFE_STATIC_FALLBACK','reason':'SUBJECT_TRANSLATION_UNSAFE','steps':[]}
        if not _safe_translation(target):return {'mode':'SAFE_STATIC_FALLBACK','reason':'TARGET_TRANSLATION_UNSAFE','steps':[]}
        adopted=_matching_existing_relationship_action(subject,intent,target)
        if adopted:
            cause_end=float(adopted['end_seconds']);source_end=_apply_preset_endpoint(_point_through(subject,float(adopted['start_seconds'])-1e-6),str(adopted['preset']))
            target_cutoff=max(cause_end,float(target.get('settle_seconds',target.get('start_seconds',0.0))))
            target_point=_point_through(target,target_cutoff);target_state=_state(target_point)
            reaction=_reaction_step(target,target_state,source_end,cause_end+1.0/max(1.0,fps))
            if reaction:
                return {'mode':'BASE_ACTION_PLUS_REACTION','reason':None,'template':'AUTHORITY_BRIDGE_REACTION','adopted_action':adopted,
                        'subject_state':_state(source_end),'target_state':target_state,'subject_point':source_end,'target_point':target_point,'steps':[reaction]}
            return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_REACTION_PRESET_FOR_RENDERED_TARGET_STATE','adopted_action':adopted,
                    'subject_state':_state(source_end),'target_state':target_state,'subject_point':source_end,'target_point':target_point,'steps':[]}
        subject_point=_settled_point(subject);subject_state=_state(subject_point);target_point=_settled_point(target);target_state=_state(target_point)
        steps,template=_pair_steps(subject,target,subject_state,target_state,action)
        if steps:return {'mode':'CAUSAL_PAIR_CHOREOGRAPHY','reason':None,'template':template,'subject_state':subject_state,'target_state':target_state,'subject_point':subject_point,'target_point':target_point,'steps':steps}
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_PRESET_TEMPLATE_FOR_RENDERED_PAIR_STATE','subject_state':subject_state,'target_state':target_state,'subject_point':subject_point,'target_point':target_point,'steps':[]}
    subject_point=_settled_point(subject);subject_state=_state(subject_point);steps,template=_focus_steps(subject,subject_state,action)
    if steps:return {'mode':'FOCUS_MANIFESTATION','reason':None,'template':template,'subject_state':subject_state,'subject_point':subject_point,'steps':steps}
    return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_SAFE_PRESET_MANIFESTATION_FOR_RENDERED_STATE','subject_state':subject_state,'subject_point':subject_point,'steps':[]}
