from __future__ import annotations
import math
from hexa_v31.preset_authority import duration,preset,preset_delta

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

def _required_operations(name:str)->set[str]:
    d=preset(name);ops=set();dx,dy=preset_delta(name)
    if abs(dx)>1e-6 or abs(dy)>1e-6:ops.add('TRANSLATE')
    for row in d.get('scale_keyframes') or []:
        try:
            if abs(float(row[1])-1.0)>.002:ops.add('SCALE');break
        except Exception:continue
    for row in d.get('opacity_keyframes') or []:
        try:
            if abs(float(row[1])-1.0)>.002:ops.add('REVEAL');break
        except Exception:continue
    if not ops:ops.add('STATIC')
    return ops

def _manifestation_safe(event:dict,name:str)->bool:
    if str(event.get('render_mode') or '')=='RESIDUAL_SUPPORT':return False
    ops=_required_operations(name)
    if 'TRANSLATE' in ops and not bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))):return False
    if 'SCALE' in ops and not bool(event.get('scale_safe',True)):return False
    if 'REVEAL' in ops and not bool(event.get('reveal_safe',True)):return False
    return True

def _safe_translation(event:dict)->bool:
    return bool(event.get('translation_safe_after_occlusion',event.get('animation_safe',True))) and str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT'

def _apply_preset_endpoint(point,name):
    if not name:return point
    d=preset(name);end=d.get('end_norm')
    if str(d.get('family') or '') in {'ENTRY_EXIT','WITHIN_FRAME'} and isinstance(end,(list,tuple)) and len(end)>=2:
        return [float(end[0]),float(end[1])]
    return point

def _point_through(event:dict,cutoff_seconds:float|None=None):
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

def _settled_point(event:dict):return _point_through(event,None)

def _entry_impact(event:dict,entry:dict,name:str)->float:
    st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name));fraction=.90 if name.startswith('ENTRY_') else .70
    return st+fraction*dd

def _aligned_entry_manifestation(event:dict,intent:dict,phase:str,fps:float):
    entry=event.get('preset_entry') or {};name=str(entry.get('name') or '')
    if not name or not _manifestation_safe(event,name):return None
    family=str(preset(name).get('family') or '')
    if family not in {'ENTRY_EXIT','APPEARANCE'}:return None
    st=float(entry.get('start_seconds',event.get('start_seconds',0.0)));dd=float(entry.get('duration_seconds') or duration(name));en=st+dd
    event_hit=float(event.get('perceptual_hit_seconds',_entry_impact(event,entry,name)));intent_hit=float(intent.get('semantic_hit_seconds',event_hit));impact=_entry_impact(event,entry,name);tolerance=max(6.0/max(1.0,fps),.20)
    if abs(impact-event_hit)>tolerance+1e-6:return None
    if phase=='ACTION' and abs(event_hit-intent_hit)>max(tolerance,.35)+1e-6:return None
    return {'event_id':str(event.get('event_id')),'preset':name,'start_seconds':round(st,6),'end_seconds':round(en,6),'duration_seconds':round(dd,6),'phase':phase,
            'semantic_role':'EXISTING_ENTRY_'+phase,'authority':'BASE_PRESET_ENTRY_SEMANTIC_ALIGNMENT','source_kind':'PRESET_ENTRY',
            'required_operations':sorted(_required_operations(name)),'perceptual_impact_seconds':round(impact,6),'event_hit_seconds':round(event_hit,6),
            'key':'|'.join((str(event.get('event_id')),name,f'{st:.6f}',phase))}

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
    return {'event_id':str(event.get('event_id')),'preset':name,'start_seconds':round(st,6),'end_seconds':round(en,6),'duration_seconds':round(en-st,6),'phase':'ACTION',
            'semantic_role':'BASE_AUTHORED_CAUSE','authority':str(action.get('authority') or 'BASE_RELATIONSHIP_AUTHORITY'),'source_kind':'PRESET_ACTION',
            'required_operations':sorted(_required_operations(name)),'original_relationship_evidence':action.get('relationship_evidence'),
            'key':'|'.join((str(event.get('event_id')),name,f'{st:.6f}',target_semantic or target_event))}

def _step(phase,event,preset_name,role,**extra):
    return {'phase':phase,'event_id':event['event_id'],'preset':preset_name,'duration_seconds':duration(preset_name),'semantic_role':role,'required_operations':sorted(_required_operations(preset_name)),**extra}

def _reaction_step(target,target_state,source_end_point,not_before):
    if target_state=='RIGHT':name='WITHIN_RIGHT_TO_MIDDLE'
    elif target_state=='LEFT':name='WITHIN_LEFT_TO_MIDDLE'
    elif target_state=='MIDDLE':
        sx=float(source_end_point[0]);sy=float(source_end_point[1]);name='WITHIN_MIDDLE_TO_RIGHT' if sx<.46 else ('WITHIN_MIDDLE_TO_LEFT' if sx>.54 else ('WITHIN_MIDDLE_TO_DOWN' if sy<.42 else 'WITHIN_MIDDLE_TO_UP'))
    else:return None
    if not _manifestation_safe(target,name):return None
    return _step('REACTION',target,name,'TARGET_REACTS_TO_CAUSE',not_before_seconds=round(float(not_before),6))

def _pair_steps(subject,target,subject_state,target_state,action):
    rows=None;template=None
    if subject_state=='MIDDLE' and target_state=='RIGHT':rows=[_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_YIELDS_SPACE'),_step('REACTION',target,'WITHIN_RIGHT_TO_MIDDLE','TARGET_RECEIVES_FOCUS')];template='CENTER_RIGHT_HANDOFF'
    elif subject_state=='MIDDLE' and target_state=='LEFT':rows=[_step('ACTION',subject,'WITHIN_MIDDLE_TO_RIGHT','SOURCE_YIELDS_SPACE'),_step('REACTION',target,'WITHIN_LEFT_TO_MIDDLE','TARGET_RECEIVES_FOCUS')];template='CENTER_LEFT_HANDOFF'
    elif subject_state=='LEFT' and target_state=='MIDDLE':rows=[_step('ACTION',subject,'WITHIN_LEFT_TO_MIDDLE','SOURCE_APPROACHES_FOCUS'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_YIELDS_AND_REACTS')];template='LEFT_CENTER_EXCHANGE'
    elif subject_state=='RIGHT' and target_state=='MIDDLE':rows=[_step('ACTION',subject,'WITHIN_RIGHT_TO_MIDDLE','SOURCE_APPROACHES_FOCUS'),_step('REACTION',target,'WITHIN_MIDDLE_TO_LEFT','TARGET_YIELDS_AND_REACTS')];template='RIGHT_CENTER_EXCHANGE'
    elif subject_state=='MIDDLE' and target_state=='MIDDLE':
        if action in {'COMPARE','BLOCK','REJECT'}:rows=[_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_ESTABLISHES_CONTRAST'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_ESTABLISHES_COUNTERSTATE')];template='CENTER_PAIR_DIVERGENCE'
        else:rows=[_step('ACTION',subject,'WITHIN_MIDDLE_TO_LEFT','SOURCE_CREATES_RESULT_SPACE'),_step('REACTION',target,'WITHIN_MIDDLE_TO_RIGHT','TARGET_REACTS_IN_RESULT_SPACE')];template='CENTER_CAUSAL_DIVERGENCE'
    if not rows:return [],None
    if not all(_manifestation_safe(subject if r['phase']=='ACTION' else target,str(r['preset'])) for r in rows):return [],None
    return rows,template

def _focus_steps(subject,state,action):
    if not _safe_translation(subject):return [],None
    if state=='LEFT':return [_step('ACTION',subject,'WITHIN_LEFT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'LEFT_TO_FOCUS'
    if state=='RIGHT':return [_step('ACTION',subject,'WITHIN_RIGHT_TO_MIDDLE','SEMANTIC_FOCUS_ACQUIRE')],'RIGHT_TO_FOCUS'
    if state=='MIDDLE':
        name='WITHIN_MIDDLE_TO_UP' if action in {'REVEAL','READ','INCREASE'} else 'WITHIN_MIDDLE_TO_DOWN';return [_step('ACTION',subject,name,'SEMANTIC_FOCUS_PUNCTUATION')],'CENTER_FOCUS_PUNCTUATION'
    return [],None

def _fixed_pair_from_entries(subject,target,intent,fps):
    action=_aligned_entry_manifestation(subject,intent,'ACTION',fps);reaction=_aligned_entry_manifestation(target,intent,'REACTION',fps)
    if not action or not reaction:return None
    if float(reaction['start_seconds'])<float(action['end_seconds'])+1.0/max(1.0,fps)-1e-6:return None
    return action,reaction

def build_choreography_candidate(intent:dict,event_by_id:dict[str,dict],fps:float)->dict:
    subject=event_by_id.get(str(intent['subject_event_id']));target=event_by_id.get(str(intent.get('object_event_id') or ''))
    if not subject:return {'mode':'SAFE_STATIC_FALLBACK','reason':'MISSING_SUBJECT','steps':[]}
    if not intent.get('actionable'):return {'mode':'NON_ACTIONABLE','reason':intent.get('non_actionable_reason') or 'INTENT_NOT_ACTIONABLE','steps':[]}
    action=str(intent.get('semantic_action') or '')
    if intent.get('physical_pair_allowed') and target:
        fixed=_fixed_pair_from_entries(subject,target,intent,fps)
        if fixed:
            return {'mode':'FIXED_EXISTING_PAIR','reason':None,'template':'SEMANTICALLY_ALIGNED_CAPABILITY_SAFE_ENTRY_PAIR','adopted_actions':list(fixed),'steps':[],
                    'subject_translation_safe':_safe_translation(subject),'target_translation_safe':_safe_translation(target)}
        authored=_matching_existing_relationship_action(subject,intent,target)
        adopted=authored or _aligned_entry_manifestation(subject,intent,'ACTION',fps)
        if adopted:
            cause_end=float(adopted['end_seconds']);source_end=_apply_preset_endpoint(_point_through(subject,float(adopted['start_seconds'])-1e-6),str(adopted['preset']));target_cutoff=max(cause_end,float(target.get('settle_seconds',target.get('start_seconds',0.0))));target_point=_point_through(target,target_cutoff);target_state=_state(target_point);reaction=_reaction_step(target,target_state,source_end,cause_end+1.0/max(1.0,fps))
            if reaction:
                return {'mode':'BASE_ACTION_PLUS_REACTION' if authored else 'ADOPTED_ENTRY_PLUS_REACTION','reason':None,'template':'AUTHORITY_BRIDGE_REACTION' if authored else 'CAPABILITY_SAFE_ENTRY_BRIDGE','adopted_action':adopted,
                        'subject_state':_state(source_end),'target_state':target_state,'subject_point':source_end,'target_point':target_point,'steps':[reaction],
                        'subject_translation_safe':_safe_translation(subject),'target_translation_safe':_safe_translation(target)}
        subject_point=_settled_point(subject);subject_state=_state(subject_point);target_point=_settled_point(target);target_state=_state(target_point);steps,template=_pair_steps(subject,target,subject_state,target_state,action)
        if steps:
            return {'mode':'CAUSAL_PAIR_CHOREOGRAPHY','reason':None,'template':template,'subject_state':subject_state,'target_state':target_state,'subject_point':subject_point,'target_point':target_point,'steps':steps,
                    'subject_translation_safe':_safe_translation(subject),'target_translation_safe':_safe_translation(target)}
        unsafe=[]
        if not _safe_translation(subject):unsafe.append('SUBJECT_TRANSLATION_UNSAFE')
        if not _safe_translation(target):unsafe.append('TARGET_TRANSLATION_UNSAFE')
        return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_CAPABILITY_SAFE_PAIR_MANIFESTATION','blocked_capabilities':unsafe,'subject_state':subject_state,'target_state':target_state,'subject_point':subject_point,'target_point':target_point,'steps':[]}
    adopted=_aligned_entry_manifestation(subject,intent,'ACTION',fps)
    if adopted:return {'mode':'FIXED_EXISTING_FOCUS','reason':None,'template':'SEMANTICALLY_ALIGNED_CAPABILITY_SAFE_ENTRY_FOCUS','adopted_actions':[adopted],'steps':[]}
    subject_point=_settled_point(subject);subject_state=_state(subject_point);steps,template=_focus_steps(subject,subject_state,action)
    if steps:return {'mode':'FOCUS_MANIFESTATION','reason':None,'template':template,'subject_state':subject_state,'subject_point':subject_point,'steps':steps}
    return {'mode':'SAFE_STATIC_FALLBACK','reason':'NO_SAFE_PRESET_MANIFESTATION_FOR_RENDERED_STATE','subject_state':subject_state,'subject_point':subject_point,'steps':[]}
