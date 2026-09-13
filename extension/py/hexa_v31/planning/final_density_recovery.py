from __future__ import annotations

import copy

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.layout.reference_joint_fitter import _pair_layout_candidates
from hexa_v31.planning.recovery_integrity_contract import _recompile_motion_to_carrier
from hexa_v31.visual_density import build_visual_density_report

_AUTHORITY='FINAL_MEASURED_SOURCE_DENSITY_RECOVERY'
_HOLD_AUTHORITY='FINAL_DENSITY_VISIBLE_OVERLAP_HOLD'
_PAIR_AUTHORITY='FINAL_DENSITY_BOUNDED_PAIR_STATE_FIT'
_ENTRY_AUTHORITY='FINAL_DENSITY_BOUNDED_ENTRY_ADVANCE'
_MAX_ENTRY_ADVANCE_FRAMES=6
_MAX_HOLD_FRAMES=12
_PAIR_FACTORS=(1.0,.95,.90,.85,.80,.75,.70)


def _replace_plan(target:dict, source:dict)->None:
    target.clear();target.update(source)


def _metric(plan:dict, card_id:str)->dict:
    return next((row for row in build_visual_density_report(plan).get('cards') or []
                 if str(row.get('card_id') or '')==str(card_id)),{})


def _pair_states(event:dict, event_a:str, event_b:str)->list[dict]:
    required={str(event_a),str(event_b)};rows=[]
    for key in ('composition_states','composition_participant_states'):
        for state in event.get(key) or []:
            participants={str(value) for value in state.get('participating_event_ids') or []}
            if required.issubset(participants):rows.append(state)
    return rows


def _advance_incoming_entry(plan:dict, incoming_id:str, frames:int, fps:float)->bool:
    """Advance only an existing entry inside its already-certified physical carrier.

    Voice-owned semantic hits retain the existing six-frame sync envelope. Source-
    interval fallback entries may use the full bounded carrier slack because they are
    not exact narration anchors. No source is created, suppressed or moved outside
    its physical lifetime.
    """
    by_id={str(event.get('event_id') or ''):event for event in plan.get('events') or []}
    incoming=by_id.get(str(incoming_id))
    if incoming is None or not incoming.get('preset_entry') or str(incoming.get('render_mode') or 'ROOT_ATOMIC')!='ROOT_ATOMIC':return False
    entry=incoming['preset_entry'];step=1.0/max(1.0,float(fps));old_start=float(entry.get('start_seconds',incoming.get('start_seconds',0.0)))
    physical_start=float(incoming.get('physical_start_seconds',incoming.get('start_seconds',old_start)))
    new_start=max(physical_start,old_start-float(frames)*step)
    if new_start>=old_start-1e-6:return False
    name=str(entry.get('name') or 'APPEAR_HIGH_SCALE');duration=float(entry.get('duration_seconds') or .8)
    from hexa_v31.planning.preset_story_planner import _entry_fraction
    impact=new_start+float(_entry_fraction({'preset_entry':{'name':name}}))*duration
    anchor=float(incoming.get('perceptual_hit_seconds',impact))
    if str(incoming.get('perceptual_hit_source') or '').upper()=='VOICE_TRIGGER' and abs(impact-anchor)*float(fps)>6.0+1e-6:return False
    delta=old_start-new_start
    entry['start_seconds']=round(new_start,6);entry['authority']=_ENTRY_AUTHORITY
    incoming['start_seconds']=round(min(float(incoming.get('start_seconds',old_start)),new_start),6)
    settle=float(incoming.get('settle_seconds',old_start+duration))
    if abs(settle-(old_start+duration))<=max(.08,step*2.5):incoming['settle_seconds']=round(max(new_start,settle-delta),6)
    incoming['final_density_recovery']='BOUNDED_ENTRY_ADVANCE'
    incoming['final_density_overlap_advance_requested_frames']=int(frames)
    incoming['final_density_overlap_advance_seconds']=round(delta,6)
    incoming['final_density_overlap_advance_frames']=round(delta*float(fps),3)
    return True


def _candidate_passes_final_state(plan:dict, card_id:str, fps:float)->bool:
    """Accept density recovery only after cheap QA *and* exact final certification."""
    if _metric(plan,card_id).get('hard_under_density'):
        return False
    if not composition_plan_qa(plan).get('pass'):
        return False
    from hexa_v31.interaction.director import finalize_interaction_motion_plan
    try:
        finalize_interaction_motion_plan(plan,fps=fps)
    except (ValueError,RuntimeError):
        return False
    metric=_metric(plan,card_id)
    return not metric.get('hard_under_density') and composition_plan_qa(plan).get('pass')


def _apply_hold(plan:dict, outgoing_id:str, card_id:str, frames:int, fps:float)->bool:
    by_id={str(event.get('event_id') or ''):event for event in plan.get('events') or []}
    outgoing=by_id.get(str(outgoing_id));card=next((c for c in (plan.get('visual_cards') or {}).get('cards') or [] if str(c.get('card_id') or '')==str(card_id)),None)
    if outgoing is None or card is None:return False
    exit_row=outgoing.get('preset_exit')
    if not exit_row:return False
    step=1.0/max(1.0,float(fps));shift=float(frames)*step
    old_physical_end=float(outgoing.get('physical_end_seconds',outgoing.get('end_seconds',0.0)))
    new_physical_end=min(float(card.get('end_seconds',old_physical_end)),old_physical_end+shift)
    if new_physical_end<=old_physical_end+1e-6:return False
    exit_row['start_seconds']=round(float(exit_row.get('start_seconds',old_physical_end))+shift,6)
    exit_row['authority']=_HOLD_AUTHORITY
    outgoing['physical_end_seconds']=round(new_physical_end,6)
    outgoing['end_seconds']=round(max(float(outgoing.get('end_seconds',new_physical_end)),new_physical_end),6)
    outgoing['visibility_interval_seconds']=[float(outgoing.get('physical_start_seconds',outgoing.get('start_seconds',0.0))),round(new_physical_end,6)]
    outgoing['final_density_recovery']='BOUNDED_VISIBLE_OVERLAP_HOLD'
    _recompile_motion_to_carrier(__import__('hexa_v31.planning.preset_story_planner',fromlist=['x']),outgoing,new_physical_end)
    return True


def _fit_authored_pair_states(plan:dict, outgoing_id:str, incoming_id:str)->bool:
    by_id={str(event.get('event_id') or ''):event for event in plan.get('events') or []}
    outgoing=by_id.get(str(outgoing_id));incoming=by_id.get(str(incoming_id))
    if outgoing is None or incoming is None:return False
    if not _pair_states(outgoing,outgoing_id,incoming_id) or not _pair_states(incoming,outgoing_id,incoming_id):return False
    for factor in _PAIR_FACTORS:
        for outgoing_center,incoming_center in _pair_layout_candidates(plan,outgoing,incoming,factor,factor):
            candidate=copy.deepcopy(plan);cby={str(event.get('event_id') or ''):event for event in candidate.get('events') or []}
            cout=cby[str(outgoing_id)];cin=cby[str(incoming_id)]
            for state in _pair_states(cout,outgoing_id,incoming_id):
                state['center_norm']=[round(float(outgoing_center[0]),6),round(float(outgoing_center[1]),6)]
                state['scale_multiplier']=float(factor);state['final_density_pair_fit']=_PAIR_AUTHORITY
            for state in _pair_states(cin,outgoing_id,incoming_id):
                state['center_norm']=[round(float(incoming_center[0]),6),round(float(incoming_center[1]),6)]
                state['scale_multiplier']=float(factor);state['final_density_pair_fit']=_PAIR_AUTHORITY
            if composition_plan_qa(candidate).get('pass'):
                _replace_plan(plan,candidate);return True
    return False


def _recover_hard_card(plan:dict, card_id:str, fps:float)->dict|None:
    events=[event for event in plan.get('events') or [] if not event.get('suppressed_by_card_density') and str(event.get('visual_card_id') or '')==str(card_id)]
    events.sort(key=lambda event:(float(event.get('start_seconds',0.0)),str(event.get('event_id') or '')))
    for outgoing,incoming in zip(events,events[1:]):
        if str(outgoing.get('scene_id') or '')==str(incoming.get('scene_id') or ''):continue
        outgoing_id=str(outgoing.get('event_id') or '');incoming_id=str(incoming.get('event_id') or '')
        for frames in range(1,_MAX_ENTRY_ADVANCE_FRAMES+1):
            candidate=copy.deepcopy(plan)
            if not _advance_incoming_entry(candidate,incoming_id,frames,fps):continue
            if _candidate_passes_final_state(candidate,card_id,fps):
                _replace_plan(plan,candidate)
                accepted=next(event for event in plan.get('events') or [] if str(event.get('event_id') or '')==incoming_id)
                return {'card_id':str(card_id),'outgoing_event_id':outgoing_id,'incoming_event_id':incoming_id,'strategy':'BOUNDED_ENTRY_ADVANCE','advance_frames':accepted.get('final_density_overlap_advance_frames'),'advance_seconds':accepted.get('final_density_overlap_advance_seconds'),'requested_frames':int(frames),'hold_frames':0,'pair_fit':False}
        for frames in range(1,_MAX_HOLD_FRAMES+1):
            raw_candidate=copy.deepcopy(plan)
            if not _apply_hold(raw_candidate,outgoing_id,card_id,frames,fps):continue
            candidate=copy.deepcopy(raw_candidate)
            if _candidate_passes_final_state(candidate,card_id,fps):
                _replace_plan(plan,candidate)
                return {'card_id':str(card_id),'outgoing_event_id':outgoing_id,'incoming_event_id':incoming_id,'strategy':'BOUNDED_OUTGOING_HOLD','advance_frames':0,'hold_frames':int(frames),'pair_fit':False}
            fitted=copy.deepcopy(raw_candidate)
            if _fit_authored_pair_states(fitted,outgoing_id,incoming_id) and _candidate_passes_final_state(fitted,card_id,fps):
                _replace_plan(plan,fitted)
                return {'card_id':str(card_id),'outgoing_event_id':outgoing_id,'incoming_event_id':incoming_id,'strategy':'BOUNDED_OUTGOING_HOLD_WITH_PAIR_FIT','advance_frames':0,'hold_frames':int(frames),'pair_fit':True}
    return None


def recover_final_density(plan:dict,fps:float=30.0)->dict:
    """Repair final measured density troughs using only existing source actors.

    Hard multi-object serialization is repaired by bounded existing-source timing.
    Every accepted candidate must survive the exact final lifetime/certification
    pass; thresholds are never relaxed and no package-specific IDs are used.
    """
    before=build_visual_density_report(plan)
    repaired=[];hard_repairs=[];unresolved=[]
    events=[e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density')]
    cards=(plan.get('visual_cards') or {}).get('cards') or []
    rows={str(r.get('card_id')):r for r in before.get('cards') or []}
    for card in cards:
        cid=str(card.get('card_id'));metric=rows.get(cid) or {}
        local=sorted([e for e in events if str(e.get('visual_card_id'))==cid],key=lambda e:(float(e.get('start_seconds',0)),str(e.get('event_id'))))
        if not local:continue
        if float(metric.get('near_blank_duration_seconds') or 0)>.35:
            card_start=float(card.get('start_seconds',0));first_start=min(float(e.get('physical_start_seconds',e.get('start_seconds',0))) for e in local)
            cohort=[e for e in local if float(e.get('physical_start_seconds',e.get('start_seconds',0)))<=first_start+1e-5]
            candidate=next((e for e in cohort if e.get('preset_entry')),cohort[0]);entry=candidate.get('preset_entry')
            if entry and float(entry.get('start_seconds',card_start))>card_start+1e-5:
                duration=float(entry.get('duration_seconds') or .8);entry['start_seconds']=round(card_start,6);entry['authority']='FINAL_DENSITY_CARD_LEADING_SOURCE_REVEAL';candidate['start_seconds']=round(card_start,6);candidate['settle_seconds']=round(card_start+duration,6);repaired.append(str(candidate.get('event_id')))
            else:
                predecessors=[e for e in events if str(e.get('visual_card_id'))!=cid and float(e.get('physical_end_seconds',e.get('end_seconds',0)))<=card_start+.11]
                if predecessors:
                    outgoing=max(predecessors,key=lambda e:float(e.get('physical_end_seconds',e.get('end_seconds',0))))
                    target=min(float(card.get('end_seconds',candidate.get('settle_seconds',card_start))),float(candidate.get('settle_seconds',card_start)))
                    outgoing['end_seconds']=round(target,6);outgoing['physical_end_seconds']=round(target,6);outgoing['visibility_interval_seconds']=[float(outgoing.get('physical_start_seconds',outgoing.get('start_seconds',0))),round(target,6)]
                    exit_row=outgoing.get('preset_exit')
                    if exit_row:
                        dd=float(exit_row.get('duration_seconds') or .6);exit_row['start_seconds']=round(max(float(outgoing.get('start_seconds',0)),target-dd*.6),6);exit_row['authority']='FINAL_DENSITY_CARD_LEADING_SOURCE_HOLD'
                    outgoing['final_density_recovery']='CARD_LEADING_READABLE_SOURCE_HOLD';repaired.append(str(outgoing.get('event_id')))
    hard_cards=list(build_visual_density_report(plan).get('hard_under_density_cards') or [])
    for cid in hard_cards:
        if not _metric(plan,str(cid)).get('hard_under_density'):
            continue
        result=_recover_hard_card(plan,str(cid),fps)
        if result:
            hard_repairs.append(result);repaired.extend([result['outgoing_event_id'],result['incoming_event_id']])
        else:unresolved.append(str(cid))
    after=build_visual_density_report(plan)
    return {
        'authority':_AUTHORITY,
        'repaired_event_ids':sorted(set(repaired)),
        'hard_density_repairs':hard_repairs,
        'unresolved_hard_under_density_cards':unresolved,
        'before_hard_under_density_cards':before.get('hard_under_density_cards') or [],
        'after_hard_under_density_cards':after.get('hard_under_density_cards') or [],
        'before_near_blank_duration_seconds':before.get('near_blank_duration_seconds'),
        'after_near_blank_duration_seconds':after.get('near_blank_duration_seconds'),
        'pass':not unresolved and not (after.get('hard_under_density_cards') or []),
    }
