from __future__ import annotations

"""Source-integrity normalization for non-semantic reconstruction residuals.

A RESIDUAL_SUPPORT layer exists only to preserve source pixels not owned by certified
actors. It is not an independent visual actor and must never become a density/focus
surrogate. Large sparse residuals (connectors, rings, shadows, context strokes) become
visually absurd when a generic support-slot solver magnifies them. This finalizer keeps
all residual pixels and timing, but caps their independent composition transform to the
source/camera scale and established center.
"""

import copy

from hexa_v31.composition_qa import composition_plan_qa

AUTHORITY='SOURCE_RECONSTRUCTION_RESIDUAL_CONTEXT_V1'


def _scale_rect(rect:list[float],factor:float)->list[float]:
    x,y,w,h=map(float,rect);cx=x+w/2.0;cy=y+h/2.0
    nw=w*factor;nh=h*factor
    return [round(cx-nw/2.0,6),round(cy-nh/2.0,6),round(nw,6),round(nh,6)]


def _sync_constraint_layout(plan:dict,event:dict)->None:
    cid=str(event.get('visual_card_id') or '');eid=str(event.get('event_id') or '')
    for card in (plan.get('visual_cards') or {}).get('cards') or []:
        if str(card.get('card_id') or '')!=cid:continue
        placement=((card.get('constraint_layout') or {}).get('placements') or {}).get(eid)
        if not placement:return
        placement['center_norm']=list(event.get('card_rest_position_norm') or [.5,.5])
        placement['scale']=float(event.get('layout_scale_multiplier') or 1.0)
        placement['rect_norm']=list(event.get('planned_rect_norm') or [])
        return


def finalize_residual_source_integrity(plan:dict,fps:float=30.0)->dict:
    """Prevent reconstruction support from being independently enlarged/recomposed."""
    original=copy.deepcopy(plan)
    rows=[]
    for event in plan.get('events') or []:
        if event.get('suppressed_by_card_density') or str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT':
            continue
        old_scale=max(1e-9,float(event.get('layout_scale_multiplier') or 1.0))
        new_scale=min(1.0,old_scale)
        rect=list(event.get('planned_rect_norm') or [])
        changed=False
        if len(rect)==4 and new_scale<old_scale-1e-9:
            new_rect=_scale_rect(rect,new_scale/old_scale)
            event['layout_scale_multiplier']=round(new_scale,6)
            event['planned_rect_norm']=new_rect
            event['collision_envelope_rect_norm']=list(new_rect)
            changed=True
        elif old_scale>1.0+1e-9:
            event['layout_scale_multiplier']=1.0
            changed=True
        base_center=list(event.get('card_rest_position_norm') or event.get('source_center_norm') or [.5,.5])
        bounded_states=0
        for key in ('composition_states','composition_participant_states'):
            for state in event.get(key) or []:
                state_changed=False
                if float(state.get('scale_multiplier',1.0))>1.0+1e-9:
                    state['scale_multiplier']=1.0;state_changed=True
                target=list(state.get('center_norm') or base_center)
                if len(target)>=2 and (abs(float(target[0])-float(base_center[0]))>1e-9 or abs(float(target[1])-float(base_center[1]))>1e-9):
                    state['center_norm']=list(base_center);state_changed=True
                if state.get('position_envelope'):
                    state['position_envelope']=False;state_changed=True
                if state_changed:
                    state['residual_context_authority']=AUTHORITY
                    bounded_states+=1;changed=True
        if changed:
            event['residual_context_authority']=AUTHORITY
            event['residual_independent_scale_cap']=1.0
            event['residual_independent_recomposition_forbidden']=True
            _sync_constraint_layout(plan,event)
            rows.append({'event_id':event.get('event_id'),'visual_card_id':event.get('visual_card_id'),
                         'old_scale':round(old_scale,6),'new_scale':round(float(event.get('layout_scale_multiplier') or 1.0),6),
                         'bounded_state_count':bounded_states})
    qa=composition_plan_qa(plan)
    if not qa.get('pass'):
        plan.clear();plan.update(original)
        raise ValueError('RESIDUAL_SOURCE_INTEGRITY_FINALIZER_FAILED: '+str((qa.get('failures') or [])[:4]))
    return {'authority':AUTHORITY,'changed':bool(rows),'event_count':len(rows),'events':rows,'pass':True}
