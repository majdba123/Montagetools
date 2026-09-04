from __future__ import annotations
import math
from hexa_v31.preset_authority import duration,preset,preset_delta

_CENTER=(.487,.493);_LEFT=(.183,.493);_RIGHT=(.833,.493)

def _near(point,target,tol=.075):return math.hypot(float(point[0])-target[0],float(point[1])-target[1])<=tol

def _state(point):
    if _near(point,_CENTER,.115):return 'MIDDLE'
    if _near(point,_LEFT,.145):return 'LEFT'
    if _near(point,_RIGHT,.145):return 'RIGHT'
    x=float(point[0]);y=float(point[1])
    if .38<=x<=.62 and .14<=y<=.38:return 'UP'
    if .38<=x<=.62 and .62<=y<=.86:return 'DOWN'
    return 'OTHER'

def _required_operations(name:str)->set[str]:
    d=preset(name);ops=set();dx,dy=preset_delta(name)
    if abs(dx)>1e-6 or abs(dy)>1e-6:ops.add('TRANSLATE')
    for row in d.get('scale_keyframes') or []:
        try:
            if abs(float(row[1])-1.0)>.002:ops.add('SCALE');break
        except Exception:continue
    for row in d.get('opacity_keyframes') or []:
        try:
            if abs(float(row[1])-1.0)>.002:ops.add('OPACITY_APPEARANCE');break
        except Exception:continue
    if not ops:ops.add('STATIC')
    return ops

def _manifestation_safe(event:dict,name:str)->bool:
    if str(event.get('render_mode') or '')=='RESIDUAL_SUPPORT':return False
    ops=_required_operations(name)
    if 'TRANSLATE' in ops and not bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))):return False
    if 'SCALE' in ops and not bool(event.get('scale_safe',True)):return False
    # Opacity on an APPEARANCE preset does not translate the crop or expose pixels
    # outside its physical carrier. Foundation reveal_safe refers to subobject/mask
    # reveal authority and is deliberately not overloaded here.
    return True

def _safe_translation(event:dict)->bool:return bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))) and str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT'

def _apply_preset_endpoint(point,name):
    if not name:return point
    d=preset(name);end=d.get('end_norm')
    if str(d.get('family') or '') in {'ENTRY_EXIT','WITHIN_FRAME'} and isinstance(end,(list,tuple)) and len(end)>=2:return [float(end[0]),float(end[1])]
    return point

def _point_through(event:dict,cutoff_seconds:float|None=None):
    point=list(event.get('card_rest_position_norm') or [.5,.5]);cutoff=float('inf') if cutoff_seconds is None else float(cutoff_seconds);entry=event.get('preset_entry') or {};name=str(entry.get('name') or '')
    if name:
        st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name))
        if st+dd<=cutoff+1e-6:point=_apply_preset_endpoint(point,name)
    for action in sorted((event.get('preset_actions') or []),key=lambda x:(float(x.get('start_seconds',0)),str(x.get('name') or ''))):
        name=str(action.get('name') or '')
        if not name:continue
        st=float(action.get('start_seconds',0.0));dd=float(action.get('duration_seconds') or duration(name))
        if st+dd<=cutoff+1e-6:point=_apply_preset_endpoint(point,name)
    return point

def _settled_point(event:dict):return _point_through(event,None)

def _entry_impact(event:dict,entry:dict,name:str)->float:
    st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name));fraction=.90 if name.startswith('ENTRY_') else .70
    return st+fraction*dd

def _aligned_entry_manifestation(event:dict,intent:dict,phase:str,fps:float,anchor_to_intent:bool|None=None):
    entry=event.get('preset_entry') or {};name=str(entry.get('name') or '')
    if not name or not _manifestation_safe(event,name):return None
    family=str(preset(name).get('family') or '')
    if family not in {'ENTRY_EXIT','APPEARANCE'}:return None
    st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name));en=st+dd;event_hit=float(event.get('perceptual_hit_seconds',_entry_impact(event,entry,name)));intent_hit=float(intent.get('semantic_hit_seconds',event_hit));impact=_entry_impact(event,entry,name);tolerance=max(6.0/max(1.0,fps),.20)
    if abs(impact-event_hit)>tolerance+1e-6:return None
    if anchor_to_intent is None:anchor_to_intent=(phase=='ACTION')
    if anchor_to_intent and abs(event_hit-intent_hit)>max(tolerance,.35)+1e-6:return None
    return {'event_id':str(event.get('event_id')),'preset':name,'start_seconds':round(st,6),'end_seconds':round(en,6),'duration_seconds':round(dd,6),'phase':phase,'semantic_role':'EXISTING_ENTRY_'+phase,'authority':'BASE_PRESET_ENTRY_SEMANTIC_ALIGNMENT','source_kind':'PRESET_ENTRY','required_operations':sorted(_required_operations(name)),'perceptual_impact_seconds':round(impact,6),'event_hit_seconds':round(event_hit,6),'semantic_anchor_match':bool(anchor_to_intent),'key':'|'.join((str(event.get('event_id')),name,f'{st:.6f}',phase))}

def _matching_existing_relationship_action(event:dict,intent:dict,target:dict|None):
    if not target:return None
    target_semantic=str(target.get('semantic_unit_id') or '');target_event=str(target.get('event_id') or '');hit=float(intent.get('semantic_hit_seconds',event.get('perceptual_hit_seconds',0.0)));rows=[]
    for action in event.get('preset_actions') or []:
        if str(action.get('action_type') or '').upper() not in {'SEMANTIC_RELATIONSHIP','INTERACTION_DIRECTOR'}:continue
        ats=str(action.get('target_semantic_unit_id') or '');ate=str(action.get('target_event_id') or '')
        if ats and target_semantic and ats!=target_semantic:continue
        if ate and target_event and ate!=target_event:continue
        if not ats and not ate:continue
        name=str(action.get('name') or '')
        if not name or not _manifestation_safe(event,name):continue
        st=float(action.get('start_seconds',0.0));dd=float(action.get('duration_seconds') or duration(name));en=st+dd;rows.append((abs(st-hit),st,name,en,action))
    if not rows:return None
    _,st,name,en,action=sorted(rows,key=lambda x:(x[0],x[1],x[2]))[0]
    return {'event_id':str(event.get('event_id')),'preset':name,'start_seconds':round(st,6),'end_seconds':round(en,6),'duration_seconds':round(en-st,6),'phase':'ACTION','semantic_role':'BASE_AUTHORED_CAUSE','authority':str(action.get('authority') or 'BASE_RELATIONSHIP_AUTHORITY'),'source_kind':'PRESET_ACTION','required_operations':sorted(_required_operations(name)),'original_relationship_evidence':action.get('relationship_evidence'),'key':'|'.join((str(event.get('event_id')),name,f'{st:.6f}',target_semantic or target_event))}

def _step(phase,event,preset_name,role,**extra):return {'phase':phase,'event_id':event['event_id'],'preset':preset_name,'duration_seconds':duration(preset_name),'semantic_role':role,'required_operations':sorted(_required_operations(preset_name)),**extra}

def _reaction_step(target,target_state,source_end_point,not_before):
    if target_state=='RIGHT':name='WITHIN_RIGHT_TO_MIDDLE'
    elif target_state=='LEFT':name='WITHIN_LEFT_TO_MIDDLE'
    elif target_state=='MIDDLE':
        sx=float(source_end_point[0]);sy=float(source_end_point[1]);name='WITHIN_MIDDLE_TO_RIGHT' if sx<.46 else ('WITHIN_MIDDLE_TO_LEFT' if sx>.54 else ('WITHIN_MIDDLE_TO_DOWN' if sy<.42 else 'WITHIN_MIDDLE_TO_UP'))
    else:return None
    if not _manifestation_safe(target,name):return None
    return _step('REACTION',target,name,'TARGET_REACTS_TO_CAUSE',not_before_seconds=round(float(not_before),6))

def _pair_steps(cause,reaction,cause_state,reaction_state,action):
    rows=None;template=None
    if cause_state=='MIDDLE' and reaction_state=='RIGHT':rows=[_step('ACTION',cause,'WITHIN_MIDDLE_TO_LEFT','CAUSE_YIELDS_SPACE'),_step('REACTION',reaction,'WITHIN_RIGHT_TO_MIDDLE','REACTION_RECEIVES_FOCUS')];template='CENTER_RIGHT_HANDOFF'
    elif cause_state=='MIDDLE' and reaction_state=='LEFT':rows=[_step('ACTION',cause,'WITHIN_MIDDLE_TO_RIGHT','CAUSE_YIELDS_SPACE'),_step('REACTION',reaction,'WITHIN_LEFT_TO_MIDDLE','REACTION_RECEIVES_FOCUS')];template='CENTER_LEFT_HANDOFF'
    elif cause_state=='LEFT' and reaction_state=='MIDDLE':rows=[_step('ACTION',cause,'WITHIN_LEFT_TO_MIDDLE','CAUSE_APPROACHES_FOCUS'),_step('REACTION',reaction,'WITHIN_MIDDLE_TO_RIGHT','REACTION_YIELDS_AND_RESPONDS')];template='LEFT_CENTER_EXCHANGE'
    elif cause_state=='RIGHT' and reaction_state=='MIDDLE':rows=[_step('ACTION',cause,'WITHIN_RIGHT_TO_MIDDLE','CAUSE_APPROACHES_FOCUS'),_step('REACTION',reaction,'WITHIN_MIDDLE_TO_LEFT','REACTION_YIELDS_AND_RESPONDS')];template='RIGHT_CENTER_EXCHANGE'
    elif cause_state=='MIDDLE' and reaction_state=='MIDDLE':
        if action in {'COMPARE','BLOCK','REJECT'}:rows=[_step('ACTION',cause,'WITHIN_MIDDLE_TO_LEFT','CAUSE_ESTABLISHES_CONTRAST'),_step('REACTION',reaction,'WITHIN_MIDDLE_TO_RIGHT','REACTION_ESTABLISHES_COUNTERSTATE')];template='CENTER_PAIR_DIVERGENCE'
        else:rows=[_step('ACTION',cause,'WITHIN_MIDDLE_TO_LEFT','CAUSE_CREATES_RESULT_SPACE'),_step('REACTION',reaction,'WITHIN_MIDDLE_TO_RIGHT','REACTION_RESPONDS_IN_RESULT_SPACE')];template='CENTER_CAUSAL_DIVERGENCE'
    if not rows:return [],None
    if not all(_manifestation_safe(cause if r['phase']=='ACTION' else reaction,str(r['preset'])) for r in rows):return [],None
    return rows,template

def _focus_steps(subject,state,action):
    if not _safe_translation(subject):return [],None
    if state=='LEFT':return [_step('ACTION',subject,'WITHIN_LEFT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'LEFT_TO_FOCUS'
    if state=='RIGHT':return [_step('ACTION',subject,'WITHIN_RIGHT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'RIGHT_TO_FOCUS'
    if state=='MIDDLE':
        name='WITHIN_MIDDLE_TO_UP' if action in {'REVEAL','READ','INCREASE'} else 'WITHIN_MIDDLE_TO_DOWN';return [_step('ACTION',subject,name,'SEMANTIC_FOCUS_PUNCTUATION')],'CENTER_FOCUS_PUNCTUATION'
    return [],None

def _fixed_pair_from_entries(cause,reaction,intent,fps):
    semantic_subject=str(intent.get('subject_event_id') or '');cause_is_subject=str(cause.get('event_id'))==semantic_subject;reaction_is_subject=str(reaction.get('event_id'))==semantic_subject
    action=_aligned_entry_manifestation(cause,intent,'ACTION',fps,anchor_to_intent=cause_is_subject);reply=_aligned_entry_manifestation(reaction,intent,'REACTION',fps,anchor_to_intent=reaction_is_subject)
    if not action or not reply:return None
    if float(reply['start_seconds'])<float(action['end_seconds'])+1.0/max(1.0,fps)-1e-6:return None
    return action,reply

def build_choreography_candidate(intent:dict,event_by_id:dict[str,dict],fps:float)->dict:
    subject=event_by_id.get(str(intent['subject_event_id']));target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject:return {'mode':'SAFE_STATIC_FALLBACK','reason':'MISSING_SUBJECT','steps':[]}
    if not intent.get('actionable'):return {'mode':'NON_ACTIONABLE','reason':intent.get('non_actionable_reason') or 'INTENT_NOT_ACTIONABLE','steps':[]}
    action=str(intent.get('semantic_action') or '')
    if intent.get('physical_pair_allowed') and target:
        cause=event_by_id.get(str(intent.get('causal_source_event_id') or subject.get('event_id'))) or subject;reaction=event_by_id.get(str(intent.get('causal_target_event_id') or target.get('event_id'))) or target;direction={'causal_source_event_id':cause.get('event_id'),'causal_target_event_id':reaction.get('event_id'),'causal_direction':intent.get('causal_direction')}
        fixed=_fixed_pair_from_entries(cause,reaction,intent,fps)
        if fixed:return {'mode':'FIXED_EXISTING_PAIR','reason':None,'template':'SEMANTICALLY_ALIGNED_CAPABILITY_SAFE_ENTRY_PAIR','adopted_actions':list(fixed),'steps':[],'cause_translation_safe':_safe_translation(cause),'reaction_translation_safe':_safe_translation(reaction),**direction}
        authored=_matching_existing_relationship_action(cause,intent,reaction);cause_anchor=str(cause.get('event_id'))==str(intent.get('subject_event_id'));adopted=authored or _aligned_entry_manifestation(cause,intent,'ACTION',fps,anchor_to_intent=cause_anchor)
        if adopted:
            cause_end=float(adopted['end_seconds']);source_end=_apply_preset_endpoint(_point_through(cause,float(adopted['start_seconds'])-1e-6),str(adopted['preset']));reaction_cutoff=max(cause_end,float(reaction.get('settle_seconds',reaction.get('start_seconds',0.0))));reaction_point=_point_through(reaction,reaction_cutoff);reaction_state=_state(reaction_point);reply=_reaction_step(reaction,reaction_state,source_end,cause_end+1.0/max(1.0,fps))
            if reply:return {'mode':'BASE_ACTION_PLUS_REACTION' if authored else 'ADOPTED_ENTRY_PLUS_REACTION','reason':None,'template':'AUTHORITY_BRIDGE_REACTION' if authored else 'CAPABILITY_SAFE_ENTRY_BRIDGE','adopted_action':adopted,'cause_state':_state(source_end),'reaction_state':reaction_state,'cause_point':source_end,'reaction_point':reaction_point,'steps':[reply],'cause_translation_safe':_safe_translation(cause),'reaction_translation_safe':_safe_translation(reaction),**direction}
        cause_point=_settled_point(cause);cause_state=_state(cause_point);reaction_point=_settled_point(reaction);reaction_state=_state(reaction_point);steps,template=_pair_steps(cause,reaction,cause_state,reaction_state,action)
        if steps:return {'mode':'CAUSAL_PAIR_CHOREOGRAPHY','reason':None,'template':template,'cause_state':cause_state,'reaction_state':reaction_state,'cause_point':cause_point,'reaction_point':reaction_point,'steps':steps,'cause_translation_safe':_safe_translation(cause),'reaction_translation_safe':_safe_translation(reaction),**direction}
        unsafe=[]
        if not _safe_translation(cause):unsafe.append('CAUSAL_SOURCE_TRANSLATION_UNSAFE')
        if not _safe_translation(reaction):unsafe.append('CAUSAL_TARGET_TRANSLATION_UNSAFE')
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_CAPABILITY_SAFE_PAIR_MANIFESTATION','blocked_capabilities':unsafe,'cause_state':cause_state,'reaction_state':reaction_state,'cause_point':cause_point,'reaction_point':reaction_point,'steps':[],**direction}
    adopted=_aligned_entry_manifestation(subject,intent,'ACTION',fps,anchor_to_intent=True)
    if adopted:return {'mode':'FIXED_EXISTING_FOCUS','reason':None,'template':'SEMANTICALLY_ALIGNED_CAPABILITY_SAFE_ENTRY_FOCUS','adopted_actions':[adopted],'steps':[]}
    subject_point=_settled_point(subject);subject_state=_state(subject_point);steps,template=_focus_steps(subject,subject_state,action)
    if steps:return {'mode':'FOCUS_MANIFESTATION','reason':None,'template':template,'subject_state':subject_state,'subject_point':subject_point,'steps':steps}
    return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_SAFE_PRESET_MANIFESTATION_FOR_RENDERED_STATE','subject_state':subject_state,'subject_point':subject_point,'steps':[]}
