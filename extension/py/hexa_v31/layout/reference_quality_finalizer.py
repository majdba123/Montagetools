from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import _state, card_motion_conflicts, composition_plan_qa
from hexa_v31.composition_solver import SAFE_X, SAFE_Y
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel
from hexa_v31.visual_density import build_visual_density_report


_INK_MODEL = ProjectedVisibleInkModel()
_SAFE_AREA = (SAFE_X[1] - SAFE_X[0]) * (SAFE_Y[1] - SAFE_Y[0])
_REFERENCE_PROJECTED_INK_FLOOR = 0.20
_MIN_UNDERFILLED_SECONDS = 0.55
_MAX_COMMITS = 24
_PARTITION_MODES = {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'}


def _physical_interval(event: dict) -> tuple[float, float]:
    return (
        float(event.get('physical_start_seconds', event.get('start_seconds', 0.0))),
        float(event.get('physical_end_seconds', event.get('end_seconds', 0.0))),
    )


def _card_events(plan: dict, card: dict) -> list[dict]:
    card_id = str(card.get('card_id') or '')
    return [
        event for event in (plan.get('events') or [])
        if not event.get('suppressed_by_card_density')
        and str(event.get('visual_card_id') or '') == card_id
    ]


def _projected_ink_at(event: dict, t: float) -> float:
    state = _state(event, t)
    if not state or float(state[2]) <= 0.08:
        return 0.0
    rect = state[3]
    value = _INK_MODEL.project(
        event,
        rect,
        float(state[2]),
        clip_rect=(
            SAFE_X[0],
            SAFE_Y[0],
            SAFE_X[1] - SAFE_X[0],
            SAFE_Y[1] - SAFE_Y[0],
        ),
    )
    # Match encoded occupancy's full-frame denominator. Safe-frame-normalized
    # ink previously called a ~13.4%-occupied frame "20% populated".
    return max(0.0, float(value))


def _card_samples(plan: dict, card: dict, step: float) -> list[tuple[float, float, int]]:
    events = _card_events(plan, card)
    cs = float(card.get('start_seconds', 0.0))
    ce = float(card.get('end_seconds', cs))
    rows = []
    t = cs
    while t < ce - 1e-9:
        ink = 0.0
        population = 0
        for event in events:
            state = _state(event, t)
            if not state or float(state[2]) <= 0.08:
                continue
            ink += _projected_ink_at(event, t)
            if float(state[2]) > 0.22:
                population += 1
        rows.append((t, ink, population))
        t += step
    return rows


def _card_quality(plan: dict, card: dict, step: float) -> dict:
    rows = _card_samples(plan, card, step)
    if not rows:
        return {'mean_ink': 0.0, 'underfilled_seconds': 0.0, 'mean_population': 0.0}
    mean_ink = sum(row[1] for row in rows) / len(rows)
    mean_population = sum(row[2] for row in rows) / len(rows)
    underfilled_seconds = sum(step for _, ink, _ in rows if ink < _REFERENCE_PROJECTED_INK_FLOOR)
    duration = max(0.0, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))
    return {
        'mean_ink': round(mean_ink, 6),
        'underfilled_seconds': round(min(duration, underfilled_seconds), 6),
        'mean_population': round(mean_population, 6),
    }


def _underfilled_intervals(plan: dict, card: dict, step: float) -> list[dict]:
    rows = _card_samples(plan, card, step)
    if not rows:
        return []
    ce = float(card.get('end_seconds', 0.0))
    start = None
    ink_values: list[float] = []
    intervals = []
    for t, ink, population in rows:
        low = ink < _REFERENCE_PROJECTED_INK_FLOOR
        if low and start is None:
            start = t
            ink_values = [ink]
        elif low:
            ink_values.append(ink)
        elif start is not None:
            end = t
            if end - start >= _MIN_UNDERFILLED_SECONDS - step * 0.5:
                intervals.append({
                    'card_id': str(card.get('card_id') or ''),
                    'start_seconds': start,
                    'end_seconds': end,
                    'duration_seconds': end - start,
                    'mean_projected_ink': sum(ink_values) / max(1, len(ink_values)),
                })
            start = None
            ink_values = []
    if start is not None and ce - start >= _MIN_UNDERFILLED_SECONDS - step * 0.5:
        intervals.append({
            'card_id': str(card.get('card_id') or ''),
            'start_seconds': start,
            'end_seconds': ce,
            'duration_seconds': ce - start,
            'mean_projected_ink': sum(ink_values) / max(1, len(ink_values)),
        })
    return intervals


def _cohort_key(event: dict) -> tuple:
    render_mode = str(event.get('render_mode') or 'ROOT_ATOMIC')
    if render_mode in _PARTITION_MODES:
        return (
            'PARTITION',
            str(event.get('visual_card_id') or ''),
            str(event.get('scene_id') or ''),
            str(event.get('partition_group_id') or event.get('partition_root_id') or 'ROOT_COMPOSITE'),
        )
    return ('EVENT', str(event.get('event_id') or ''))


def _cohorts(events: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for event in events:
        grouped.setdefault(_cohort_key(event), []).append(event)
    return [grouped[key] for key in sorted(grouped, key=str)]


def _cohort_rest_ink(cohort: list[dict]) -> float:
    total = 0.0
    for event in cohort:
        bbox = event.get('source_bbox_norm') or [0.0, 0.0, 0.3, 0.3]
        try:
            area = max(0.0, float(bbox[2])) * max(0.0, float(bbox[3]))
        except (TypeError, ValueError, IndexError):
            area = 0.09
        camera = max(0.0, float(event.get('reference_camera_scale') or 1.0))
        scale = max(0.0, float(event.get('layout_scale_multiplier') or 1.0))
        visible = _INK_MODEL.visible_fraction(event)
        total += area * camera * camera * scale * scale * max(0.0, min(1.0, float(visible)))
    return total


def _candidate_predecessor_cohorts(plan: dict, card: dict, gap_start: float, step: float, gap_end: float | None = None) -> list[list[dict]]:
    candidates = []
    for cohort in _cohorts(_card_events(plan, card)):
        starts = [float(event.get('start_seconds', 0.0)) for event in cohort]
        ends = [float(event.get('end_seconds', 0.0)) for event in cohort]
        if not starts or not ends:
            continue
        cohort_end = max(ends)
        # A continuously sparse interval may start while its predecessor is
        # still visible. Consider its retirement inside that interval too.
        if cohort_end >= float(gap_end if gap_end is not None else gap_start + step) - step * .5:
            continue
        if gap_start - cohort_end > 1.60:
            continue
        if any(end <= start + step * 0.5 for start, end in zip(starts, ends)):
            continue
        ids={str(event.get('event_id')) for event in cohort}
        phases=(card.get('story_phase_plan') or {}).get('phases') or []
        successors=[event for event in _card_events(plan,card)
                    if str(event.get('event_id')) not in ids
                    and float(event.get('perceptual_hit_seconds',event.get('start_seconds',0))) >= max(float(x.get('perceptual_hit_seconds',x.get('start_seconds',0))) for x in cohort)
                    and float(event.get('end_seconds',0))>cohort_end+step
                    and float(event.get('start_seconds',0))<=cohort_end+1.60]
        # Source-scene continuity or an already-authored shared semantic phase
        # is required; mere temporal adjacency cannot retain an obsolete actor.
        if not any(any(str(next_event.get('scene_id'))==str(prior.get('scene_id')) for prior in cohort)
                   or any(str(next_event.get('event_id')) in phase.get('event_ids',[]) and ids.intersection(map(str,phase.get('event_ids',[]))) for phase in phases)
                   for next_event in successors):
            continue
        candidates.append(cohort)
    candidates.sort(key=lambda cohort: (
        0 if any(str(event.get('attention_priority') or '').upper() != 'PRIMARY' for event in cohort) else 1,
        -_cohort_rest_ink(cohort),
        -max(float(event.get('end_seconds', 0.0)) for event in cohort),
        str(_cohort_key(cohort[0])),
    ))
    return candidates


def _refresh_motion_intervals(event: dict) -> None:
    from hexa_v31.planning.preset_story_planner import _compile_final_motion_intervals

    intervals, motion_start, motion_end = _compile_final_motion_intervals(event)
    event['motion_intervals'] = intervals
    event['motion_start_seconds'] = round(motion_start, 6)
    event['motion_end_seconds'] = round(motion_end, 6)


def _extend_cohort(cohort: list[dict], new_end: float, gap_start: float) -> None:
    for event in cohort:
        old_end = float(event.get('end_seconds', 0.0))
        if new_end <= old_end + 1e-6:
            continue
        extension = new_end - old_end
        event['end_seconds'] = round(new_end, 6)
        event['physical_end_seconds'] = round(new_end, 6)
        physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
        event['visibility_interval_seconds'] = [round(physical_start, 6), round(new_end, 6)]
        if event.get('partition_carrier_end_seconds') is not None:
            event['partition_carrier_end_seconds'] = round(new_end, 6)
        exit_row = event.get('preset_exit')
        if exit_row:
            # Retention extends a readable pose, not the old post-exit tail.
            # Preserve the authored exit shape/duration and retire it exactly
            # at the newly committed physical boundary.
            duration = max(0.0, float(exit_row.get('duration_seconds') or .6))
            exit_row['start_seconds'] = round(new_end - duration, 6)
        event['reference_density_hold_authority'] = 'SOURCE_BACKED_PREDECESSOR_STATE_CONTINUITY'
        event['reference_density_hold_from_seconds'] = round(gap_start, 6)
        event['reference_density_hold_to_seconds'] = round(new_end, 6)
        _refresh_motion_intervals(event)


def _restore_events(events: list[dict], snapshots: dict[str, dict]) -> None:
    for event in events:
        event_id = str(event.get('event_id') or '')
        snapshot = snapshots.get(event_id)
        if snapshot is None:
            continue
        event.clear()
        event.update(copy.deepcopy(snapshot))


def _density_monotonic(before: dict, after: dict) -> bool:
    return (
        float(after.get('near_blank_duration_seconds', 0.0))
        <= float(before.get('near_blank_duration_seconds', 0.0)) + 0.01
        and float(after.get('median_safe_frame_union_coverage', 0.0))
        >= float(before.get('median_safe_frame_union_coverage', 0.0)) - 0.001
        and float(after.get('mean_temporal_population', 0.0))
        >= float(before.get('mean_temporal_population', 0.0)) - 0.001
    )


def _plan_safe(plan: dict, card: dict, fps: float) -> bool:
    cs = float(card.get('start_seconds', 0.0))
    ce = float(card.get('end_seconds', cs))
    neighbors=[e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density') and _physical_interval(e)[0]<ce and _physical_interval(e)[1]>cs]
    if card_motion_conflicts(neighbors, cs, ce, fps):
        return False
    # Count simultaneously readable semantic primaries, not just event count.
    t=cs
    while t<ce-1e-6:
        visible=[e for e in neighbors if (s:=_state(e,t)) and s[2]>.22]
        units=_cohorts(visible)
        primaries=sum(any(str(e.get('attention_priority')).upper()=='PRIMARY' for e in unit) for unit in units)
        if primaries>2 or len(units)-primaries>3:return False
        t+=1/max(12.,min(20.,fps))
    return bool(composition_plan_qa(plan).get('pass'))


def _fit_readable_context(plan: dict, card: dict, cohort: list[dict], fps: float) -> bool:
    """Fit a retained root in a semantic slot without creating position travel."""
    from hexa_v31.layout.reference_geometry_finalizer import (
        _candidate_safe, _group_has_position_authority, _root_fit_destinations,
    )
    from hexa_v31.composition_solver import _fp, _rect, MOTION_ENVELOPE_SCALE

    if len(cohort) != 1 or str(cohort[0].get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
        return False  # partitions retain their complete-group geometry owner
    event = cohort[0]
    if _group_has_position_authority(cohort):
        return False
    snapshot = copy.deepcopy(event)
    scale = float(event.get('layout_scale_multiplier') or 1.0)
    for center in _root_fit_destinations(plan, event, scale):
        event['card_rest_position_norm'] = list(center)
        event['planned_rect_norm'] = list(_rect(center, _fp(event), scale * MOTION_ENVELOPE_SCALE))
        event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
        for key in ('composition_states', 'composition_participant_states'):
            for state in event.get(key) or []:
                state['center_norm'] = list(center)
        if _candidate_safe(plan, cohort, fps) and _plan_safe(plan, card, fps):
            return True
    event.clear(); event.update(snapshot)
    return False


def finalize_reference_density_topology(plan: dict, fps: float = 30.0) -> dict:
    """Rescue source-backed underfilled intervals by retaining prior semantic state.

    The pass never invents a visual, changes semantic hit time, changes source
    identity, or separates a certified source partition. A candidate may only
    extend an already-revealed predecessor cohort inside its owning visual card.
    Partition members are extended as one carrier cohort. Every candidate is
    checked against animated collision/composition QA and must improve projected
    source-backed density monotonically before it can commit.
    """
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    events = plan.get('events') or []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    before_density = build_visual_density_report(plan)
    before_card_quality = {
        str(card.get('card_id') or ''): _card_quality(plan, card, step)
        for card in cards
    }
    stats = {
        'authority': 'REFERENCE_DENSITY_TOPOLOGY_RESCUE_V1',
        'projected_ink_floor': _REFERENCE_PROJECTED_INK_FLOOR,
        'sample_step_seconds': round(step, 6),
        'candidate_intervals_evaluated': 0,
        'candidate_cohorts_evaluated': 0,
        'holds_committed': 0,
        'partition_cohort_holds_committed': 0,
        'held_event_ids': [],
        'rejections': {},
        'before_underfilled_seconds': round(sum(row['underfilled_seconds'] for row in before_card_quality.values()), 6),
        'before_mean_projected_ink': round(
            sum(row['mean_ink'] for row in before_card_quality.values()) / max(1, len(before_card_quality)), 6
        ),
    }

    commits = 0
    while commits < _MAX_COMMITS:
        intervals = []
        card_by_id = {str(card.get('card_id') or ''): card for card in cards}
        for card in cards:
            intervals.extend(_underfilled_intervals(plan, card, step))
        intervals.sort(key=lambda row: (-float(row['duration_seconds']), float(row['start_seconds']), str(row['card_id'])))
        committed = False
        for interval in intervals:
            stats['candidate_intervals_evaluated'] += 1
            card = card_by_id.get(str(interval['card_id']))
            if card is None:
                continue
            pre_quality = _card_quality(plan, card, step)
            pre_density = build_visual_density_report(plan)
            gap_start = float(interval['start_seconds'])
            gap_end = min(float(card.get('end_seconds', interval['end_seconds'])), float(interval['end_seconds']))
            for cohort in _candidate_predecessor_cohorts(plan, card, gap_start, step, gap_end):
                stats['candidate_cohorts_evaluated'] += 1
                cohort_ids = {str(event.get('event_id') or '') for event in cohort}
                snapshots = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in events}
                _extend_cohort(cohort, gap_end, gap_start)
                from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe
                safe = _plan_safe(plan, card, fps) and _candidate_safe(plan, cohort, fps)
                if not safe and not _fit_readable_context(plan, card, cohort, fps):
                    _restore_events(events, snapshots)
                    stats['rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                    continue
                readable = True
                for event in cohort:
                    original = snapshots[str(event.get('event_id') or '')]
                    start = max(float(original.get('end_seconds', 0.)),
                                float(event.get('settle_seconds', event.get('start_seconds', 0.))))
                    end = float((event.get('preset_exit') or {}).get('start_seconds', gap_end))
                    while start < end - 1e-6:
                        state = _state(event, start)
                        if state is None or state[2] < .85:
                            readable = False
                            break
                        start += step
                if not readable:
                    _restore_events(events, snapshots)
                    stats['rejections']['UNREADABLE_RETAINED_CONTEXT'] = stats['rejections'].get('UNREADABLE_RETAINED_CONTEXT', 0) + 1
                    continue
                post_quality = _card_quality(plan, card, step)
                post_density = build_visual_density_report(plan)
                material = (
                    float(post_quality['underfilled_seconds']) <= float(pre_quality['underfilled_seconds']) - min(0.20, step * 2.0)
                    or float(post_quality['mean_ink']) >= float(pre_quality['mean_ink']) + 0.012
                )
                if not material or not _density_monotonic(pre_density, post_density):
                    _restore_events(events, snapshots)
                    reason = 'NO_MATERIAL_DENSITY_GAIN' if not material else 'DENSITY_MONOTONICITY'
                    stats['rejections'][reason] = stats['rejections'].get(reason, 0) + 1
                    continue
                stats['holds_committed'] += 1
                if str(cohort[0].get('render_mode') or '') in _PARTITION_MODES:
                    stats['partition_cohort_holds_committed'] += 1
                stats['held_event_ids'].extend(sorted(cohort_ids))
                from hexa_v31.layout.reference_geometry_finalizer import _sync_constraint_layout
                for event in cohort:
                    _sync_constraint_layout(plan, event)
                commits += 1
                committed = True
                break
            if committed:
                break
        if not committed:
            break

    after_density = build_visual_density_report(plan)
    after_card_quality = {
        str(card.get('card_id') or ''): _card_quality(plan, card, step)
        for card in cards
    }
    stats['held_event_ids'] = sorted(set(stats['held_event_ids']))
    stats['after_underfilled_seconds'] = round(sum(row['underfilled_seconds'] for row in after_card_quality.values()), 6)
    stats['after_mean_projected_ink'] = round(
        sum(row['mean_ink'] for row in after_card_quality.values()) / max(1, len(after_card_quality)), 6
    )
    stats['changed'] = bool(stats['holds_committed'])
    stats['pass'] = _density_monotonic(before_density, after_density) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        raise ValueError('REFERENCE_DENSITY_TOPOLOGY_RESCUE_FAILED')
    return stats
