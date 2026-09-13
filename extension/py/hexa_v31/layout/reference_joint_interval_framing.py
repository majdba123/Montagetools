from __future__ import annotations

"""Temporary coordinated density framing for already-simultaneous source actors.

This pass exists between permanent geometry fitting and P4 semantic sequencing.  It
never changes card_rest_position_norm, never retimes a P2 preset, and never scales a
partition child.  When two or three legitimate ROOT_ATOMIC actors are already visible
together during a sustained sparse interval, it may temporarily scale that whole
semantic cohort at its established centers, then restore 1.0 before the next reveal or
handoff.  DENSITY_FRAME is an independent envelope track and therefore composes with
SEMANTIC_SEQUENCE rather than overwriting it.
"""

import copy
import math

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.layout.position_authority import has_actual_center_travel
from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe, _density_not_worse
from hexa_v31.layout.reference_quality_finalizer import _card_quality
from hexa_v31.layout.reference_residual_closure import (
    _active_roots,
    _card_events,
    _card_id,
    _event_id,
    _semantic_pair_allowed,
    _worst_interval,
)
from hexa_v31.layout.reference_staggered_sequence import _safe_envelope_cap
from hexa_v31.visual_density import build_visual_density_report

AUTHORITY='REFERENCE_JOINT_TEMPORARY_DENSITY_FRAME_V1'
_MAX_COMMITS=8
_MIN_INTERVAL=.70
_MIN_MEAN_GAIN=.012
_MIN_UNDERFILL_GAIN=.35


def _entry_settled(event:dict)->float:
    entry=event.get('preset_entry') or {}
    return max(
        float(event.get('physical_start_seconds',event.get('start_seconds',0))),
        float(event.get('settle_seconds',event.get('start_seconds',0))),
        float(entry.get('start_seconds',event.get('start_seconds',0)))+float(entry.get('duration_seconds') or 0),
    )


def _event_deadline(event:dict, fallback:float)->float:
    return min(
        fallback,
        float(event.get('physical_end_seconds',event.get('end_seconds',fallback))),
        float(event.get('motion_end_seconds',event.get('end_seconds',fallback))),
        float((event.get('preset_exit') or {}).get('start_seconds',fallback)),
    )


def _semantic_cohort(card:dict, roots:list[dict])->list[dict]:
    if len(roots)<2:return []
    roots=sorted(roots,key=lambda e:(0 if str(e.get('attention_priority') or '').upper()=='PRIMARY' else 1,
                                     -float(e.get('visible_ink_fraction') or 0),_event_id(e)))
    owner=roots[0]
    cohort=[owner]
    for event in roots[1:]:
        if _semantic_pair_allowed(card,owner,event):
            cohort.append(event)
        if len(cohort)>=3:break
    return cohort if len(cohort)>=2 else []


def _next_handoff(plan:dict,card:dict,cohort:list[dict],start:float,end:float)->float:
    ids={_event_id(e) for e in cohort}
    deadline=end
    for other in _card_events(plan,card):
        if _event_id(other) in ids or other.get('suppressed_by_card_density'):continue
        entry=other.get('preset_entry') or {}
        onset=max(float(other.get('physical_start_seconds',other.get('start_seconds',0))),
                  float(entry.get('start_seconds',other.get('start_seconds',0))))
        if start+.35<onset<deadline:
            deadline=onset
    return deadline


def _append_scale_envelope(event:dict,card:dict,start:float,end:float,transition:float,factor:float,ids:list[str])->None:
    center=list(event.get('card_rest_position_norm') or [.5,.5])
    base=f"{_event_id(event)}::JOINT_DENSITY_FRAME::{round(start,6)}"
    common=dict(authority=AUTHORITY,sequence_envelope=True,envelope_track='DENSITY_FRAME',
                position_envelope=True,card_id=_card_id(card),visibility=1.0,
                center_norm=center,owner_event_id=_event_id(event),participating_event_ids=list(ids))
    states=event.setdefault('composition_participant_states',[])
    states.extend([
        dict(common,state_id=base,start_seconds=round(start,6),transition_duration_seconds=round(transition,6),
             scale_multiplier=round(factor,6),semantic_beat='SIMULTANEOUS_COHORT_DENSITY_FRAME'),
        dict(common,state_id=base+'::RESTORE',previous_state_id=base,start_seconds=round(end-transition,6),
             transition_duration_seconds=round(transition,6),scale_multiplier=1.0,
             semantic_beat='RESTORE_BEFORE_SEMANTIC_HANDOFF'),
    ])


def _candidate_factors(quality:dict)->list[float]:
    mean=max(.04,float(quality.get('mean_ink') or 0.0))
    target=.25 if mean<.18 else .235
    desired=min(1.25,max(1.06,math.sqrt(target/mean)))
    values=[desired,1.20,1.15,1.10,1.07]
    out=[]
    for value in values:
        value=round(min(1.25,max(1.0,float(value))),6)
        if value<=1.035 or value in out:continue
        out.append(value)
    return out


def _snapshot_cohort(cohort:list[dict])->tuple[list[str],dict[str,dict]]:
    ids=[_event_id(event) for event in cohort]
    if any(not event_id for event_id in ids) or len(set(ids))!=len(ids):
        raise ValueError('REFERENCE_JOINT_INTERVAL_FRAMING_INVALID_COHORT_EVENT_ID')
    return ids,{event_id:copy.deepcopy(event) for event_id,event in zip(ids,cohort)}


def _restore_cohort(cohort:list[dict],ids:list[str],snapshots:dict[str,dict])->None:
    for event,event_id in zip(cohort,ids):
        event.clear()
        event.update(copy.deepcopy(snapshots[event_id]))


def finalize_reference_joint_interval_framing(plan:dict,fps:float=30.0)->dict:
    original=copy.deepcopy(plan)
    cards=list((plan.get('visual_cards') or {}).get('cards') or [])
    step=max(.08,min(.12,3.0/max(1.0,float(fps))))
    before_density=build_visual_density_report(plan)
    stats={
        'authority':AUTHORITY,'changed':False,'commits':0,'cards_considered':0,
        'candidates_evaluated':0,'event_ids':[],'mutations':[],'rejections':{},
    }
    for card in cards:
        if stats['commits']>=_MAX_COMMITS:break
        quality=_card_quality(plan,card,step)
        interval=_worst_interval(plan,card,step,quality)
        if not interval:continue
        roots=[e for e in _active_roots(plan,card,interval)
               if str(e.get('render_mode') or 'ROOT_ATOMIC')=='ROOT_ATOMIC'
               and not has_actual_center_travel(e)
               and not any(s.get('envelope_track')=='DENSITY_FRAME'
                           for key in ('composition_states','composition_participant_states')
                           for s in e.get(key) or [])]
        cohort=_semantic_cohort(card,roots)
        if len(cohort)<2:
            stats['rejections']['NO_SIMULTANEOUS_SEMANTIC_COHORT']=stats['rejections'].get('NO_SIMULTANEOUS_SEMANTIC_COHORT',0)+1
            continue
        stats['cards_considered']+=1
        start=max(float(interval.get('start_seconds') or card.get('start_seconds',0)),*[_entry_settled(e) for e in cohort])
        end=min(float(interval.get('end_seconds') or card.get('end_seconds',start)),*[_event_deadline(e,float(card.get('end_seconds',start))) for e in cohort])
        end=_next_handoff(plan,card,cohort,start,end)
        if end-start<_MIN_INTERVAL:
            stats['rejections']['INSUFFICIENT_SETTLED_INTERVAL']=stats['rejections'].get('INSUFFICIENT_SETTLED_INTERVAL',0)+1
            continue
        transition=min(.38,max(.22,(end-start)*.18))
        ids,snapshots=_snapshot_cohort(cohort)
        pre_quality=copy.deepcopy(quality)
        pre_density=build_visual_density_report(plan)
        committed=False
        for requested in _candidate_factors(pre_quality):
            stats['candidates_evaluated']+=1
            _restore_cohort(cohort,ids,snapshots)
            actual=[]
            for event in cohort:
                cap=max(1.0,float(_safe_envelope_cap(event,fps)))
                factor=min(requested,cap)
                actual.append(factor)
                if factor>1.035:
                    _append_scale_envelope(event,card,start,end,transition,factor,ids)
            if sum(f>1.035 for f in actual)<2:
                stats['rejections']['INSUFFICIENT_SHARED_SCALE_HEADROOM']=stats['rejections'].get('INSUFFICIENT_SHARED_SCALE_HEADROOM',0)+1
                continue
            if not _candidate_safe(plan,cohort,fps) or not bool(composition_plan_qa(plan).get('pass')):
                stats['rejections']['COLLISION_OR_COMPOSITION_QA']=stats['rejections'].get('COLLISION_OR_COMPOSITION_QA',0)+1
                continue
            after=_card_quality(plan,card,step)
            post_density=build_visual_density_report(plan)
            mean_gain=float(after.get('mean_ink') or 0)-float(pre_quality.get('mean_ink') or 0)
            under_gain=float(pre_quality.get('underfilled_seconds') or 0)-float(after.get('underfilled_seconds') or 0)
            severe_ok=float(after.get('severe_underfilled_seconds') or 0)<=float(pre_quality.get('severe_underfilled_seconds') or 0)+1e-6
            material=(mean_gain>=_MIN_MEAN_GAIN or (under_gain>=_MIN_UNDERFILL_GAIN and mean_gain>=0))
            if not material or not severe_ok or not _density_not_worse(pre_density,post_density):
                stats['rejections']['NO_MATERIAL_SAFE_DENSITY_GAIN']=stats['rejections'].get('NO_MATERIAL_SAFE_DENSITY_GAIN',0)+1
                continue
            for event,factor in zip(cohort,actual):
                event['reference_joint_interval_framing_authority']=AUTHORITY
                event['reference_joint_interval_framing_peak_scale']=round(float(factor),6)
                event['reference_joint_interval_framing_interval']=[round(start,6),round(end,6)]
            stats['commits']+=1;stats['event_ids'].extend(ids)
            stats['mutations'].append({'card_id':_card_id(card),'event_ids':ids,'interval':[round(start,6),round(end,6)],
                                      'peak_scales':[round(float(v),6) for v in actual],
                                      'before_quality':pre_quality,'after_quality':after})
            committed=True
            break
        if not committed:
            _restore_cohort(cohort,ids,snapshots)
    after_density=build_visual_density_report(plan)
    stats['event_ids']=sorted(set(stats['event_ids']))
    stats['changed']=bool(stats['commits'])
    stats['pass']=_density_not_worse(before_density,after_density) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        plan.clear();plan.update(original)
        raise ValueError('REFERENCE_JOINT_INTERVAL_FRAMING_FAILED')
    return stats
