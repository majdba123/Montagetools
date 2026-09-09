from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import _state, composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _in_safe, _rect, composition_state_at
from hexa_v31.layout.position_authority import has_actual_center_travel
from hexa_v31.layout.reference_geometry_finalizer import (
    _candidate_safe,
    _density_not_worse,
    _physical_interval,
    _projected_settled_ink,
    _root_fit_destinations,
    _sync_constraint_layout,
)
from hexa_v31.layout.reference_quality_finalizer import (
    _card_quality,
    _underfilled_intervals,
)
from hexa_v31.visual_density import build_visual_density_report


_AUTHORITY = 'REFERENCE_RESIDUAL_CARD_AND_FOCUS_CLOSURE_V1'
_MAX_DENSITY_COMMITS = 14
_MAX_DENSITY_COMMITS_PER_CARD = 2
_MAX_FOCUS_COMMITS = 12
_MIN_INTERVAL_SECONDS = 0.55
_MIN_MEAN_INK_GAIN = 0.015
_MIN_UNDERFILL_GAIN_SECONDS = 0.30
_MIN_FOCUS_AUTHORED_INK_DELTA = 0.020
_MAX_PRIMARY_ABSOLUTE_SCALE = 3.00
_MAX_SUPPORT_ABSOLUTE_SCALE = 2.30


def _card_id(card: dict) -> str:
    return str(card.get('card_id') or '')


def _event_id(event: dict) -> str:
    return str(event.get('event_id') or '')


def _card_duration(card: dict) -> float:
    return max(
        0.001,
        float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)),
    )


def _card_events(plan: dict, card: dict) -> list[dict]:
    cid = _card_id(card)
    return [
        event
        for event in plan.get('events') or []
        if not event.get('suppressed_by_card_density')
        and str(event.get('visual_card_id') or '') == cid
    ]


def _eligible_root(event: dict) -> bool:
    return (
        not event.get('suppressed_by_card_density')
        and str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and event.get('visible_ink_fraction') is not None
        and bool(event.get('planned_rect_norm'))
    )


def _semantic_pair_allowed(card: dict, a: dict, b: dict) -> bool:
    if str(a.get('visual_card_id') or '') != str(b.get('visual_card_id') or ''):
        return False
    a_scene = str(a.get('scene_id') or '')
    b_scene = str(b.get('scene_id') or '')
    if a_scene and a_scene == b_scene:
        return True
    a_id, b_id = _event_id(a), _event_id(b)
    for phase in (card.get('story_phase_plan') or {}).get('phases') or []:
        ids = {str(event_id) for event_id in phase.get('event_ids') or []}
        if a_id in ids and b_id in ids:
            return True
    return False


def _quality_target(card: dict, quality: dict) -> float:
    duration = _card_duration(card)
    underfill_ratio = min(
        1.0,
        max(0.0, float(quality.get('underfilled_seconds') or 0.0) / duration),
    )
    mean_ink = max(0.0, float(quality.get('mean_ink') or 0.0))
    severe_deficit = min(1.0, max(0.0, (0.18 - mean_ink) / 0.18))
    # The old 0.20 planner floor mapped to roughly 0.16 encoded occupancy on
    # the canonical production replay. Residual closure therefore aims above
    # that floor only for cards that remain measurably sparse after every
    # preceding density/geometry pass.
    return round(min(0.30, 0.24 + 0.04 * underfill_ratio + 0.02 * severe_deficit), 6)


def _severity(card: dict, quality: dict) -> float:
    duration = _card_duration(card)
    underfill_ratio = min(
        1.0,
        max(0.0, float(quality.get('underfilled_seconds') or 0.0) / duration),
    )
    mean_ink = max(0.0, float(quality.get('mean_ink') or 0.0))
    return (
        2.0 * underfill_ratio
        + 2.5 * max(0.0, 0.22 - mean_ink)
        + 0.35 * max(0.0, 1.6 - float(quality.get('mean_population') or 0.0))
    )


def _worst_interval(plan: dict, card: dict, step: float, quality: dict) -> dict | None:
    intervals = _underfilled_intervals(plan, card, step)
    if intervals:
        return sorted(
            intervals,
            key=lambda row: (
                -float(row.get('duration_seconds') or 0.0),
                float(row.get('mean_projected_ink') or 0.0),
                float(row.get('start_seconds') or 0.0),
            ),
        )[0]
    if float(quality.get('mean_ink') or 0.0) < 0.22:
        start = float(card.get('start_seconds', 0.0))
        end = float(card.get('end_seconds', start))
        return {
            'card_id': _card_id(card),
            'start_seconds': start,
            'end_seconds': end,
            'duration_seconds': max(0.0, end - start),
            'mean_projected_ink': float(quality.get('mean_ink') or 0.0),
        }
    return None


def _active_roots(plan: dict, card: dict, interval: dict) -> list[dict]:
    start = float(interval.get('start_seconds') or card.get('start_seconds', 0.0))
    end = float(interval.get('end_seconds') or card.get('end_seconds', start))
    duration = max(0.001, end - start)
    samples = [
        start + 0.20 * duration,
        start + 0.50 * duration,
        start + 0.80 * duration,
    ]
    rows = []
    for event in _card_events(plan, card):
        if not _eligible_root(event):
            continue
        visible = 0
        for t in samples:
            state = _state(event, t)
            if state is not None and float(state[2]) > 0.22:
                visible += 1
        overlap = max(
            0.0,
            min(end, _physical_interval(event)[1])
            - max(start, _physical_interval(event)[0]),
        )
        if visible < 2 or overlap < min(_MIN_INTERVAL_SECONDS, duration * 0.50):
            continue
        primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
        rows.append(
            (
                0 if primary else 1,
                -visible,
                -overlap,
                -_projected_settled_ink(event),
                _event_id(event),
                event,
            )
        )
    rows.sort(key=lambda row: row[:-1])
    return [row[-1] for row in rows]


def _apply_geometry(event: dict, center: list[float], factor: float) -> None:
    old_center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    old_scale = float(event.get('layout_scale_multiplier') or 1.0)
    new_scale = old_scale * factor
    rect = list(_rect(center, _fp(event), new_scale * MOTION_ENVELOPE_SCALE))
    event['card_rest_position_norm'] = [
        round(float(center[0]), 6),
        round(float(center[1]), 6),
    ]
    event['layout_scale_multiplier'] = round(new_scale, 6)
    event['planned_rect_norm'] = [round(float(value), 6) for value in rect]
    event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
    # Relocate only center-preserving hierarchy states. Authored center travel
    # remains owned by its existing motion/composition authority.
    if math.dist(old_center, event['card_rest_position_norm']) > 1e-6:
        for key in ('composition_states', 'composition_participant_states'):
            for state in event.get(key) or []:
                state_center = state.get('center_norm') or old_center
                try:
                    stationary = (
                        math.dist(
                            [float(state_center[0]), float(state_center[1])],
                            [float(old_center[0]), float(old_center[1])],
                        )
                        <= 1e-6
                    )
                except (TypeError, ValueError, IndexError):
                    stationary = False
                if stationary:
                    state['center_norm'] = list(event['card_rest_position_norm'])


def _scale_ladder(event: dict, card: dict, quality: dict) -> list[float]:
    mean_ink = max(0.01, float(quality.get('mean_ink') or 0.0))
    target = _quality_target(card, quality)
    desired = math.sqrt(target / mean_ink) if mean_ink < target else 1.0
    old_scale = max(1e-6, float(event.get('layout_scale_multiplier') or 1.0))
    primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
    absolute_cap = _MAX_PRIMARY_ABSOLUTE_SCALE if primary else _MAX_SUPPORT_ABSOLUTE_SCALE
    relative_cap = max(1.0, absolute_cap / old_scale)
    class_cap = 1.85 if primary else 1.45
    cap = min(relative_cap, class_cap)
    if cap <= 1.025:
        return []
    if float(quality.get('mean_ink') or 0.0) < 0.15:
        desired = max(desired, 1.28 if primary else 1.16)
    elif float(quality.get('underfilled_seconds') or 0.0) >= _card_duration(card) * 0.50:
        desired = max(desired, 1.18 if primary else 1.10)
    desired = min(cap, desired)
    candidates = [
        min(cap, desired * 1.18),
        min(cap, desired * 1.08),
        desired,
        1.45 if primary else 1.28,
        1.34 if primary else 1.20,
        1.26 if primary else 1.14,
        1.18 if primary else 1.10,
        1.12,
        1.08,
    ]
    out = []
    for value in candidates:
        value = round(float(value), 6)
        if value <= 1.025 or value > cap + 1e-6 or value in out:
            continue
        out.append(value)
    out.sort(reverse=True)
    return out


def _material_card_gain(before: dict, after: dict, card: dict) -> bool:
    mean_gain = float(after.get('mean_ink') or 0.0) - float(before.get('mean_ink') or 0.0)
    underfill_gain = (
        float(before.get('underfilled_seconds') or 0.0)
        - float(after.get('underfilled_seconds') or 0.0)
    )
    return (
        mean_gain >= _MIN_MEAN_INK_GAIN
        or underfill_gain >= min(
            _MIN_UNDERFILL_GAIN_SECONDS,
            _card_duration(card) * 0.10,
        )
    )


def _commit_density_actor(
    plan: dict,
    card: dict,
    event: dict,
    pre_quality: dict,
    fps: float,
    stats: dict,
) -> bool:
    old_density = build_visual_density_report(plan)
    snapshot = copy.deepcopy(event)
    old_center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    old_scale = float(event.get('layout_scale_multiplier') or 1.0)
    static_center = not has_actual_center_travel(event)
    stats['density_candidates_requested'] += 1
    for factor in _scale_ladder(event, card, pre_quality):
        destinations = (
            _root_fit_destinations(plan, snapshot, old_scale * factor)
            if static_center
            else [old_center]
        )
        for center in destinations:
            stats['density_candidates_evaluated'] += 1
            event.clear()
            event.update(copy.deepcopy(snapshot))
            _apply_geometry(event, list(center), factor)
            if not _in_safe(event.get('planned_rect_norm') or []):
                stats['density_rejections']['SAFE_FRAME'] = (
                    stats['density_rejections'].get('SAFE_FRAME', 0) + 1
                )
                continue
            if not _candidate_safe(plan, [event], fps):
                stats['density_rejections']['COLLISION_OR_COMPOSITION_QA'] = (
                    stats['density_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                )
                continue
            post_quality = _card_quality(plan, card, stats['sample_step_seconds'])
            post_density = build_visual_density_report(plan)
            if not _density_not_worse(old_density, post_density):
                stats['density_rejections']['DENSITY_MONOTONICITY'] = (
                    stats['density_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                )
                continue
            if not _material_card_gain(pre_quality, post_quality, card):
                stats['density_rejections']['NO_MATERIAL_CARD_GAIN'] = (
                    stats['density_rejections'].get('NO_MATERIAL_CARD_GAIN', 0) + 1
                )
                continue
            event['reference_residual_density_authority'] = _AUTHORITY
            event['reference_residual_density_card_id'] = _card_id(card)
            event['reference_residual_density_scale_factor'] = round(float(factor), 6)
            event['reference_residual_density_quality_before'] = copy.deepcopy(pre_quality)
            event['reference_residual_density_quality_after'] = copy.deepcopy(post_quality)
            _sync_constraint_layout(plan, event)
            stats['density_candidates_committed'] += 1
            stats['density_event_ids'].append(_event_id(event))
            stats['density_mutations'].append(
                {
                    'card_id': _card_id(card),
                    'event_id': _event_id(event),
                    'before_center_norm': old_center,
                    'after_center_norm': list(event.get('card_rest_position_norm') or []),
                    'before_layout_scale': round(old_scale, 6),
                    'after_layout_scale': round(
                        float(event.get('layout_scale_multiplier') or 1.0), 6
                    ),
                    'before_quality': copy.deepcopy(pre_quality),
                    'after_quality': copy.deepcopy(post_quality),
                }
            )
            return True
    event.clear()
    event.update(snapshot)
    return False


def _close_residual_density(plan: dict, fps: float, stats: dict) -> None:
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    committed_ids: set[str] = set()
    per_card: dict[str, int] = {}
    while stats['density_candidates_committed'] < _MAX_DENSITY_COMMITS:
        ranked = []
        for card in cards:
            quality = _card_quality(plan, card, stats['sample_step_seconds'])
            if (
                float(quality.get('underfilled_seconds') or 0.0) < _MIN_INTERVAL_SECONDS
                and float(quality.get('mean_ink') or 0.0) >= 0.22
            ):
                continue
            ranked.append((-_severity(card, quality), _card_id(card), card, quality))
        ranked.sort(key=lambda row: row[:2])
        changed = False
        for _, cid, card, quality in ranked:
            if per_card.get(cid, 0) >= _MAX_DENSITY_COMMITS_PER_CARD:
                continue
            interval = _worst_interval(plan, card, stats['sample_step_seconds'], quality)
            if interval is None:
                continue
            roots = [
                event
                for event in _active_roots(plan, card, interval)
                if _event_id(event) not in committed_ids
            ]
            if not roots:
                stats['density_rejections']['NO_ACTIVE_SOURCE_ROOT'] = (
                    stats['density_rejections'].get('NO_ACTIVE_SOURCE_ROOT', 0) + 1
                )
                continue
            for event in roots:
                if _commit_density_actor(plan, card, event, quality, fps, stats):
                    committed_ids.add(_event_id(event))
                    per_card[cid] = per_card.get(cid, 0) + 1
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break


def _reveal_entry(target: dict) -> tuple[float, float, float] | None:
    entry = target.get('preset_entry') or {}
    name = str(entry.get('name') or '')
    # Only center-preserving source reveals are eligible here. Real entry/within
    # travel remains protected by has_actual_center_travel().
    if not name.startswith('APPEAR_'):
        return None
    start = float(entry.get('start_seconds', target.get('start_seconds', 0.0)))
    duration = max(0.20, float(entry.get('duration_seconds') or 0.8))
    hit = float(target.get('perceptual_hit_seconds', start + 0.70 * duration))
    return start, duration, hit


def _focus_candidates(plan: dict, stats: dict) -> list[tuple]:
    rows = []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    for card in cards:
        quality = _card_quality(plan, card, stats['sample_step_seconds'])
        local = sorted(
            [event for event in _card_events(plan, card) if _eligible_root(event)],
            key=lambda event: (
                float(event.get('perceptual_hit_seconds', event.get('start_seconds', 0.0))),
                _event_id(event),
            ),
        )
        for owner in local:
            if has_actual_center_travel(owner):
                continue
            owner_hit = float(
                owner.get('perceptual_hit_seconds', owner.get('start_seconds', 0.0))
            )
            owner_states = owner.get('composition_states') or []
            last_owner_state_end = max(
                [
                    float(state.get('start_seconds', 0.0))
                    + float(state.get('transition_duration_seconds') or 0.0)
                    for state in owner_states
                ]
                or [float(owner.get('physical_start_seconds', owner.get('start_seconds', 0.0)))]
            )
            for target in local:
                if target is owner or has_actual_center_travel(target):
                    continue
                if target.get('composition_states') or target.get('composition_participant_states'):
                    continue
                reveal = _reveal_entry(target)
                if reveal is None:
                    continue
                entry_start, _, hit = reveal
                if hit <= owner_hit + 0.42 or not _semantic_pair_allowed(card, owner, target):
                    continue
                transfer_start = max(entry_start + 0.08, hit - 0.52)
                transfer_duration = max(0.32, min(0.64, hit + 0.08 - transfer_start))
                transfer_end = transfer_start + transfer_duration
                if transfer_start < last_owner_state_end + 0.20:
                    continue
                owner_start, owner_end = _physical_interval(owner)
                target_start, target_end = _physical_interval(target)
                if (
                    transfer_start < max(owner_start, target_start) - 1e-6
                    or transfer_end + 0.16 > min(owner_end, target_end)
                ):
                    continue
                if any(
                    (sample := _state(owner, t)) is None or float(sample[2]) <= 0.55
                    for t in (transfer_start - 0.10, hit, transfer_end + 0.08)
                ):
                    continue
                after_overlap = max(0.0, min(owner_end, target_end) - transfer_end)
                if after_overlap < 0.55:
                    continue
                owner_ink = _projected_settled_ink(owner)
                target_ink = _projected_settled_ink(target)
                if min(owner_ink, target_ink) <= 0.012:
                    continue
                rows.append(
                    (
                        -after_overlap,
                        -_severity(card, quality),
                        _card_id(card),
                        _event_id(owner),
                        _event_id(target),
                        card,
                        owner,
                        target,
                        transfer_start,
                        transfer_duration,
                    )
                )
    rows.sort(key=lambda row: row[:5])
    return rows


def _focus_variants(owner_scale: float) -> list[tuple[float, float, float]]:
    return [
        (round(owner_scale * 0.84, 6), 0.82, 1.12),
        (round(owner_scale * 0.88, 6), 0.86, 1.10),
        (round(owner_scale * 0.92, 6), 0.88, 1.08),
        (round(owner_scale, 6), 0.84, 1.12),
        (round(owner_scale, 6), 0.88, 1.10),
        (round(owner_scale, 6), 1.00, 1.16),
    ]


def _author_focus_transfer(
    plan: dict,
    card: dict,
    owner: dict,
    target: dict,
    transfer_start: float,
    transfer_duration: float,
    fps: float,
    stats: dict,
) -> bool:
    owner_snapshot = copy.deepcopy(owner)
    target_snapshot = copy.deepcopy(target)
    before_density = build_visual_density_report(plan)
    owner_center, owner_scale, owner_visibility = composition_state_at(owner, transfer_start)
    target_center = list(target.get('card_rest_position_norm') or [0.5, 0.5])
    entry_start, _, _ = _reveal_entry(target) or (
        float(target.get('start_seconds', 0.0)),
        0.8,
        transfer_start,
    )
    owner_ink = _projected_settled_ink(owner)
    target_ink = _projected_settled_ink(target)
    state_id = (
        _card_id(card)
        + '::'
        + _event_id(owner)
        + '::FOCUS_TRANSFER::'
        + _event_id(target)
    )
    participant_ids = [_event_id(owner), _event_id(target)]
    previous_owner_state = (
        str((owner.get('composition_states') or [])[-1].get('state_id') or '')
        if owner.get('composition_states')
        else None
    )
    stats['focus_candidates_requested'] += 1
    for owner_to, target_from, target_to in _focus_variants(owner_scale):
        stats['focus_candidates_evaluated'] += 1
        owner.clear()
        owner.update(copy.deepcopy(owner_snapshot))
        target.clear()
        target.update(copy.deepcopy(target_snapshot))
        authored_delta = (
            owner_ink * abs(owner_scale * owner_scale - owner_to * owner_to)
            + target_ink * abs(target_to * target_to - target_from * target_from)
        )
        participant_delta = target_ink * abs(
            target_to * target_to - target_from * target_from
        )
        if (
            authored_delta < _MIN_FOCUS_AUTHORED_INK_DELTA
            or participant_delta < 0.012
        ):
            stats['focus_rejections']['NO_MATERIAL_AUTHORED_DELTA'] = (
                stats['focus_rejections'].get('NO_MATERIAL_AUTHORED_DELTA', 0) + 1
            )
            continue
        owner_state = {
            'state_id': state_id,
            'scene_id': owner.get('scene_id'),
            'card_id': _card_id(card),
            'semantic_beat': 'SOURCE_REVEAL_FOCUS_TRANSFER',
            'state_reason': 'VISIBLE_SOURCE_REVEAL_TRANSFERS_HIERARCHY',
            'start_seconds': round(transfer_start, 6),
            'transition_duration_seconds': round(transfer_duration, 6),
            'participating_event_ids': participant_ids,
            'center_norm': [round(float(owner_center[0]), 6), round(float(owner_center[1]), 6)],
            'scale_multiplier': round(float(owner_to), 6),
            'visibility': round(float(owner_visibility), 6),
            'translation_safe': False,
            'role': owner.get('composition_role'),
        }
        if previous_owner_state:
            owner_state['previous_state_id'] = previous_owner_state
        owner.setdefault('composition_states', []).append(owner_state)

        participant_base = {
            'owner_state_id': state_id,
            'card_id': _card_id(card),
            'scene_id': target.get('scene_id'),
            'center_norm': [
                round(float(target_center[0]), 6),
                round(float(target_center[1]), 6),
            ],
            'visibility': 1.0,
            'translation_safe': False,
            'participating_event_ids': participant_ids,
        }
        participant_a_id = state_id + '::PARTICIPANT_A'
        target['composition_participant_states'] = [
            dict(
                participant_base,
                state_id=participant_a_id,
                start_seconds=round(max(entry_start, _physical_interval(target)[0]), 6),
                transition_duration_seconds=0.0,
                scale_multiplier=round(float(target_from), 6),
                semantic_beat='SOURCE_REVEAL_SUBORDINATE_HIERARCHY',
            ),
            dict(
                participant_base,
                state_id=state_id + '::PARTICIPANT_B',
                previous_state_id=participant_a_id,
                start_seconds=round(transfer_start, 6),
                transition_duration_seconds=round(transfer_duration, 6),
                scale_multiplier=round(float(target_to), 6),
                semantic_beat='SOURCE_REVEAL_FOCUS_ESTABLISHMENT',
            ),
        ]
        owner['meaningful_recomposition'] = True
        owner['reference_residual_focus_authority'] = _AUTHORITY
        target['reference_residual_focus_authority'] = _AUTHORITY
        if not _candidate_safe(plan, [owner, target], fps):
            stats['focus_rejections']['COLLISION_OR_COMPOSITION_QA'] = (
                stats['focus_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
            )
            continue
        after_density = build_visual_density_report(plan)
        if not _density_not_worse(before_density, after_density):
            stats['focus_rejections']['DENSITY_MONOTONICITY'] = (
                stats['focus_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
            )
            continue
        stats['focus_candidates_committed'] += 1
        stats['focus_owner_event_ids'].append(_event_id(owner))
        stats['focus_participant_event_ids'].append(_event_id(target))
        stats['focus_mutations'].append(
            {
                'card_id': _card_id(card),
                'owner_event_id': _event_id(owner),
                'participant_event_id': _event_id(target),
                'state_id': state_id,
                'start_seconds': round(transfer_start, 6),
                'duration_seconds': round(transfer_duration, 6),
                'owner_scale_before': round(float(owner_scale), 6),
                'owner_scale_after': round(float(owner_to), 6),
                'participant_scale_from': round(float(target_from), 6),
                'participant_scale_to': round(float(target_to), 6),
                'projected_authored_ink_delta': round(float(authored_delta), 6),
            }
        )
        return True
    owner.clear()
    owner.update(owner_snapshot)
    target.clear()
    target.update(target_snapshot)
    return False


def _close_residual_focus(plan: dict, fps: float, stats: dict) -> None:
    committed_cards: set[str] = set()
    committed_actors: set[str] = set()
    while stats['focus_candidates_committed'] < _MAX_FOCUS_COMMITS:
        changed = False
        for row in _focus_candidates(plan, stats):
            _, _, cid, owner_id, target_id, card, owner, target, start, duration = row
            if (
                cid in committed_cards
                or owner_id in committed_actors
                or target_id in committed_actors
            ):
                continue
            if _author_focus_transfer(
                plan, card, owner, target, start, duration, fps, stats
            ):
                committed_cards.add(cid)
                committed_actors.update((owner_id, target_id))
                changed = True
                break
        if not changed:
            break


def finalize_reference_residual_closure(
    plan: dict,
    fps: float = 30.0,
) -> dict:
    """Close residual sparse cards and semantic holds after normal finalizers.

    This pass exists only for residual deficits that survive topology, geometry,
    joint fitting and perceptual composition. It never invents sources, moves
    position-authored actors, splits partitions, changes semantic hit timing or
    adds idle/repeating motion. Density commits are source-backed static
    geometry changes with full lifetime certification. Motion commits are
    one-way focus transfers tied to an already-authored source reveal.
    """
    original = copy.deepcopy(plan)
    before_density = build_visual_density_report(plan)
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    before_quality = {
        _card_id(card): _card_quality(plan, card, step)
        for card in cards
    }
    stats = {
        'authority': _AUTHORITY,
        'sample_step_seconds': step,
        'density_candidates_requested': 0,
        'density_candidates_evaluated': 0,
        'density_candidates_committed': 0,
        'density_event_ids': [],
        'density_mutations': [],
        'density_rejections': {},
        'focus_candidates_requested': 0,
        'focus_candidates_evaluated': 0,
        'focus_candidates_committed': 0,
        'focus_owner_event_ids': [],
        'focus_participant_event_ids': [],
        'focus_mutations': [],
        'focus_rejections': {},
        'before_underfilled_seconds': round(
            sum(float(row.get('underfilled_seconds') or 0.0) for row in before_quality.values()),
            6,
        ),
        'before_mean_projected_ink': round(
            sum(float(row.get('mean_ink') or 0.0) for row in before_quality.values())
            / max(1, len(before_quality)),
            6,
        ),
    }

    _close_residual_density(plan, fps, stats)
    _close_residual_focus(plan, fps, stats)

    after_density = build_visual_density_report(plan)
    after_quality = {
        _card_id(card): _card_quality(plan, card, step)
        for card in cards
    }
    stats['density_event_ids'] = sorted(set(stats['density_event_ids']))
    stats['focus_owner_event_ids'] = sorted(set(stats['focus_owner_event_ids']))
    stats['focus_participant_event_ids'] = sorted(
        set(stats['focus_participant_event_ids'])
    )
    stats['after_underfilled_seconds'] = round(
        sum(float(row.get('underfilled_seconds') or 0.0) for row in after_quality.values()),
        6,
    )
    stats['after_mean_projected_ink'] = round(
        sum(float(row.get('mean_ink') or 0.0) for row in after_quality.values())
        / max(1, len(after_quality)),
        6,
    )
    stats['changed'] = bool(
        stats['density_candidates_committed']
        or stats['focus_candidates_committed']
    )
    stats['pass'] = (
        _density_not_worse(before_density, after_density)
        and bool(composition_plan_qa(plan).get('pass'))
    )
    if not stats['pass']:
        plan.clear()
        plan.update(original)
        raise ValueError('REFERENCE_RESIDUAL_CARD_AND_FOCUS_CLOSURE_FAILED')
    return stats
