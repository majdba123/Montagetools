from __future__ import annotations

import copy

from hexa_v31.visual_density import build_visual_density_report


def _restore_event(live: dict, snapshot: dict) -> None:
    live.clear()
    live.update(copy.deepcopy(snapshot))


def _recompile_event_motion(event: dict) -> None:
    from hexa_v31.planning import preset_story_planner as planner

    intervals, motion_start, motion_end = planner._compile_final_motion_intervals(event)
    event['motion_intervals'] = intervals
    event['motion_start_seconds'] = round(float(motion_start), 6)
    event['motion_end_seconds'] = round(float(motion_end), 6)


def _card_hard_under_density(plan: dict, card_id: str) -> bool:
    report = build_visual_density_report(plan)
    row = next(
        (item for item in report.get('cards') or [] if str(item.get('card_id') or '') == str(card_id)),
        None,
    )
    return bool(row and row.get('hard_under_density'))


def _try_bounded_source_overlap(plan: dict, card: dict, outgoing: dict, incoming: dict, fps: float) -> dict | None:
    """Advance one existing incoming reveal just enough to restore readable overlap.

    The actor already exists in the package and no geometry/threshold is changed.
    Search is bounded to the same six-frame perceptual sync budget used by final
    cross-scene recovery. Every candidate must keep unchanged global composition
    QA green and remove the measured hard-under-density state.
    """
    entry = incoming.get('preset_entry')
    exit_row = outgoing.get('preset_exit')
    if not entry or not exit_row:
        return None
    if str(outgoing.get('scene_id') or '') == str(incoming.get('scene_id') or ''):
        return None
    if incoming.get('partition_group_id') or str(incoming.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
        return None

    from hexa_v31.composition_qa import composition_plan_qa

    card_start = float(card.get('start_seconds', incoming.get('start_seconds', 0.0)))
    original_entry_start = float(entry.get('start_seconds', incoming.get('start_seconds', card_start)))
    original_start = float(incoming.get('start_seconds', original_entry_start))
    original_physical_start = float(incoming.get('physical_start_seconds', original_start))
    duration = float(entry.get('duration_seconds') or 0.8)
    snapshot = copy.deepcopy(incoming)

    for advance_frames in range(1, 7):
        _restore_event(incoming, snapshot)
        entry = incoming.get('preset_entry') or {}
        target = max(card_start, original_entry_start - advance_frames / max(1.0, float(fps)))
        if target >= original_entry_start - 1e-6:
            continue

        entry['start_seconds'] = round(target, 6)
        entry['authority'] = 'FINAL_DENSITY_BOUNDED_SOURCE_OVERLAP'
        incoming['start_seconds'] = round(min(original_start, target), 6)
        incoming['physical_start_seconds'] = round(min(original_physical_start, target), 6)
        incoming['visibility_interval_seconds'] = [
            float(incoming['physical_start_seconds']),
            float(incoming.get('physical_end_seconds', incoming.get('end_seconds', target))),
        ]
        incoming['settle_seconds'] = round(target + duration, 6)
        incoming['final_density_recovery'] = 'BOUNDED_SOURCE_OVERLAP'
        incoming['final_density_overlap_required'] = True
        incoming['final_density_overlap_advance_frames'] = int(advance_frames)
        _recompile_event_motion(incoming)

        if not composition_plan_qa(plan).get('pass'):
            continue
        if _card_hard_under_density(plan, str(card.get('card_id') or '')):
            continue

        return {
            'card_id': str(card.get('card_id') or ''),
            'outgoing_event_id': str(outgoing.get('event_id') or ''),
            'incoming_event_id': str(incoming.get('event_id') or ''),
            'advance_frames': int(advance_frames),
            'original_entry_start_seconds': round(original_entry_start, 6),
            'final_entry_start_seconds': round(target, 6),
            'authority': 'FINAL_DENSITY_BOUNDED_SOURCE_OVERLAP',
        }

    _restore_event(incoming, snapshot)
    return None


def recover_final_density(plan: dict, fps: float = 30.0) -> dict:
    """Repair only final measured readability troughs using existing source actors."""
    events=[e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density')]
    cards=(plan.get('visual_cards') or {}).get('cards') or []
    before=build_visual_density_report(plan);rows={str(r.get('card_id')):r for r in before.get('cards') or []}
    repaired=[];overlap_repairs=[]
    for card in cards:
        cid=str(card.get('card_id'));metric=rows.get(cid) or {}
        local=sorted([e for e in events if str(e.get('visual_card_id'))==cid],key=lambda e:(float(e.get('start_seconds',0)),str(e.get('event_id'))))
        if not local:continue
        if float(metric.get('near_blank_duration_seconds') or 0)>.35:
            card_start=float(card.get('start_seconds',0));first_start=min(float(e.get('physical_start_seconds',e.get('start_seconds',0))) for e in local)
            cohort=[e for e in local if float(e.get('physical_start_seconds',e.get('start_seconds',0)))<=first_start+1e-5]
            candidate=next((e for e in cohort if e.get('preset_entry')),cohort[0])
            entry=candidate.get('preset_entry')
            if entry and float(entry.get('start_seconds',card_start))>card_start+1e-5:
                duration=float(entry.get('duration_seconds') or .8);entry['start_seconds']=round(card_start,6);entry['authority']='FINAL_DENSITY_CARD_LEADING_SOURCE_REVEAL';candidate['start_seconds']=round(card_start,6);candidate['settle_seconds']=round(card_start+duration,6)
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
                    continue
            repaired.append(str(candidate.get('event_id')))
        if metric.get('hard_under_density'):
            for outgoing,incoming in zip(local,local[1:]):
                repair=_try_bounded_source_overlap(plan,card,outgoing,incoming,fps)
                if repair:
                    overlap_repairs.append(repair);repaired.append(str(incoming.get('event_id')));break
    after=build_visual_density_report(plan)
    return {
        'authority':'FINAL_MEASURED_SOURCE_DENSITY_RECOVERY',
        'repaired_event_ids':sorted(set(repaired)),
        'bounded_source_overlap_repairs':overlap_repairs,
        'before_hard_under_density_cards':before.get('hard_under_density_cards') or [],
        'after_hard_under_density_cards':after.get('hard_under_density_cards') or [],
        'before_near_blank_duration_seconds':before.get('near_blank_duration_seconds'),
        'after_near_blank_duration_seconds':after.get('near_blank_duration_seconds'),
    }
