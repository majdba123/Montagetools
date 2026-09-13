from __future__ import annotations

"""Source-integrity normalization for non-semantic reconstruction residuals.

A RESIDUAL_SUPPORT layer exists only to preserve source pixels not owned by certified
actors. It is not an independent visual actor and must never become a density/focus
surrogate. Large sparse residuals (connectors, rings, shadows, context strokes) become
visually absurd when a generic support-slot solver magnifies or relocates them. This
finalizer keeps every source pixel and timing while bounding the residual transform.
"""

import copy
import math

from hexa_v31.composition_qa import composition_plan_qa

AUTHORITY='SOURCE_RECONSTRUCTION_RESIDUAL_CONTEXT_V2'


def _scale_rect(rect:list[float],factor:float)->list[float]:
    x,y,w,h=map(float,rect);cx=x+w/2.0;cy=y+h/2.0
    nw=w*factor;nh=h*factor
    return [round(cx-nw/2.0,6),round(cy-nh/2.0,6),round(nw,6),round(nh,6)]


def _recenter_rect(rect:list[float],center:list[float])->list[float]:
    x,y,w,h=map(float,rect)
    return [round(float(center[0])-w/2.0,6),round(float(center[1])-h/2.0,6),round(w,6),round(h,6)]


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


def _restore_event(target:dict,snapshot:dict,plan:dict)->None:
    target.clear();target.update(copy.deepcopy(snapshot));_sync_constraint_layout(plan,target)


def finalize_residual_source_integrity(plan:dict,fps:float=30.0)->dict:
    """Prevent reconstruction support from becoming an independent visual actor."""
    original=copy.deepcopy(plan)
    rows=[]
    for event in plan.get('events') or []:
        if event.get('suppressed_by_card_density') or str(event.get('render_mode') or '')!='RESIDUAL_SUPPORT':
            continue
        old_scale=max(1e-9,float(event.get('layout_scale_multiplier') or 1.0))
        old_center=list(event.get('card_rest_position_norm') or event.get('source_center_norm') or [.5,.5])
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

        # A reconstruction residual is safest at its source-relative center. Try
        # restoring that center after scale normalization; commit it only when the
        # exact full-plan composition remains certified. This avoids arbitrary
        # relocation of sparse rings/connectors without trading correctness for it.
        source_center=list(event.get('source_center_norm') or [])
        source_center_restored=False
        if len(source_center)>=2 and math.dist(tuple(map(float,base_center[:2])),tuple(map(float,source_center[:2])))>.025:
            scale_normalized_snapshot=copy.deepcopy(event)
            event['card_rest_position_norm']=[round(float(source_center[0]),6),round(float(source_center[1]),6)]
            if len(event.get('planned_rect_norm') or [])==4:
                centered=_recenter_rect(list(event['planned_rect_norm']),event['card_rest_position_norm'])
                event['planned_rect_norm']=centered;event['collision_envelope_rect_norm']=list(centered)
            for key in ('composition_states','composition_participant_states'):
                for state in event.get(key) or []:
                    state['center_norm']=list(event['card_rest_position_norm'])
                    state['position_envelope']=False
            _sync_constraint_layout(plan,event)
            if composition_plan_qa(plan).get('pass'):
                source_center_restored=True;changed=True
            else:
                _restore_event(event,scale_normalized_snapshot,plan)

        if changed:
            event['residual_context_authority']=AUTHORITY
            event['residual_independent_scale_cap']=1.0
            event['residual_independent_recomposition_forbidden']=True
            event['residual_source_center_restored']=source_center_restored
            _sync_constraint_layout(plan,event)
            rows.append({'event_id':event.get('event_id'),'visual_card_id':event.get('visual_card_id'),
                         'old_scale':round(old_scale,6),'new_scale':round(float(event.get('layout_scale_multiplier') or 1.0),6),
                         'old_center':[round(float(x),6) for x in old_center[:2]],
                         'new_center':[round(float(x),6) for x in (event.get('card_rest_position_norm') or old_center)[:2]],
                         'source_center_restored':source_center_restored,'bounded_state_count':bounded_states})
    qa=composition_plan_qa(plan)
    if not qa.get('pass'):
        plan.clear();plan.update(original)
        raise ValueError('RESIDUAL_SOURCE_INTEGRITY_FINALIZER_FAILED: '+str((qa.get('failures') or [])[:4]))
    return {'authority':AUTHORITY,'changed':bool(rows),'event_count':len(rows),'events':rows,'pass':True}
