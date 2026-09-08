from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, SAFE_X, SAFE_Y, _fp, _in_safe, _rect
from hexa_v31.layout.reference_geometry_finalizer import (
    _candidate_safe,
    _continue_semantic_sequences,
    _density_not_worse,
    _overlap_seconds,
    _projected_settled_ink,
    _restore_all,
    _root_fit_destinations,
    _root_scale_target,
    _sync_constraint_layout,
)
from hexa_v31.layout.reference_quality_finalizer import _card_quality
from hexa_v31.preset_authority import preset as _preset_def
from hexa_v31.visual_density import build_visual_density_report


_PAIR_TARGET_INK = 0.26
_MAX_SEVERE_PAIR_TARGET_INK = 0.32
_MIN_PAIR_OVERLAP_SECONDS = 0.55
_MIN_PAIR_INK_GAIN = 0.012
_MAX_PAIR_COMMITS = 12
_MAX_PAIR_LAYOUTS = 12


def _semantic_pair_allowed(card: dict, primary: dict, context: dict) -> bool:
    if str(primary.get('visual_card_id') or '') != str(context.get('visual_card_id') or ''):
        return False
    primary_scene = str(primary.get('scene_id') or '')
    context_scene = str(context.get('scene_id') or '')
    if primary_scene and primary_scene == context_scene:
        return True
    primary_id = str(primary.get('event_id') or '')
    context_id = str(context.get('event_id') or '')
    for phase in (card.get('story_phase_plan') or {}).get('phases') or []:
        ids = {str(event_id) for event_id in phase.get('event_ids') or []}
        if primary_id in ids and context_id in ids:
            return True
    return False


def _source_backed_root(event: dict) -> bool:
    return (
        not event.get('suppressed_by_card_density')
        and str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and event.get('visible_ink_fraction') is not None
        and bool(event.get('planned_rect_norm'))
    )


def _preset_moves_center(row: dict | None) -> bool:
    if not row:
        return False
    name = str(row.get('name') or '')
    if not name:
        return False
    try:
        definition = _preset_def(name)
    except KeyError:
        return True
    family = str(definition.get('family') or '').upper()
    if family in {'ENTRY_EXIT', 'WITHIN_FRAME'}:
        return True
    delta = definition.get('position_delta_norm') or [0.0, 0.0]
    try:
        return abs(float(delta[0])) > 1e-6 or abs(float(delta[1])) > 1e-6
    except (TypeError, ValueError, IndexError):
        return True


def _state_moves_center(event: dict) -> bool:
    base = event.get('card_rest_position_norm') or [0.5, 0.5]
    for key in ('composition_states', 'composition_participant_states'):
        for state in event.get(key) or []:
            center = state.get('center_norm') or base
            try:
                if math.dist([float(center[0]), float(center[1])],
                             [float(base[0]), float(base[1])]) > 1e-6:
                    return True
            except (TypeError, ValueError, IndexError):
                return True
    return False


def _vector_motion_authority(event: dict) -> bool:
    if abs(float(event.get('drift_dx_norm') or 0.0)) > 1e-6 or abs(float(event.get('drift_dy_norm') or 0.0)) > 1e-6:
        return True
    for key in ('focus_beats', 'story_beats', 'story_actions'):
        for row in event.get(key) or []:
            if (
                abs(float(row.get('dx_norm') or 0.0)) > 1e-6
                or abs(float(row.get('dy_norm') or 0.0)) > 1e-6
                or abs(float(row.get('arc_norm') or 0.0)) > 1e-6
            ):
                return True
    return False


def _joint_position_authority(event: dict) -> bool:
    """Protect actual center travel while allowing center-preserving hierarchy."""
    if event.get('position_animated'):
        return True
    if _preset_moves_center(event.get('preset_entry')) or _preset_moves_center(event.get('preset_exit')):
        return True
    if any(_preset_moves_center(row) for row in event.get('preset_actions') or []):
        return True
    if _state_moves_center(event) or _vector_motion_authority(event):
        return True
    return False


def _static_root(event: dict) -> bool:
    return _source_backed_root(event) and not _joint_position_authority(event)


def _pair_target_ink(card: dict, quality: dict) -> float:
    duration = max(0.001, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))
    underfilled_ratio = min(1.0, max(0.0, float(quality.get('underfilled_seconds') or 0.0) / duration))
    mean_ink = max(0.0, float(quality.get('mean_ink') or 0.0))
    ink_deficit_ratio = min(1.0, max(0.0, (0.20 - mean_ink) / 0.20))
    severity = max(underfilled_ratio, ink_deficit_ratio)
    return round(_PAIR_TARGET_INK + (_MAX_SEVERE_PAIR_TARGET_INK - _PAIR_TARGET_INK) * severity, 6)


def _pair_scale_ladder(primary: dict, context: dict, events: list[dict], pair_target_ink: float) -> list[tuple[float, float]]:
    primary_ink = _projected_settled_ink(primary)
    context_ink = _projected_settled_ink(context)
    combined = primary_ink + context_ink
    if primary_ink <= 1e-9 or context_ink <= 1e-9 or combined >= pair_target_ink - 1e-6:
        return []
    primary_target, primary_cap = _root_scale_target(primary, events)
    context_target, context_cap = _root_scale_target(context, events)
    primary_individual = min(primary_cap, math.sqrt(primary_target / primary_ink)) if primary_ink < primary_target else 1.0
    context_individual = min(context_cap, math.sqrt(context_target / context_ink)) if context_ink < context_target else 1.0
    pair_factor = math.sqrt(pair_target_ink / max(1e-9, combined))
    primary_desired = min(primary_cap, max(primary_individual, pair_factor))
    context_desired = min(context_cap, max(context_individual, pair_factor))
    if primary_desired <= 1.025 and context_desired <= 1.025:
        return []

    out: list[tuple[float, float]] = []
    for fraction in (1.0, 0.84, 0.68, 0.52):
        primary_factor = round(1.0 + (primary_desired - 1.0) * fraction, 6)
        context_factor = round(1.0 + (context_desired - 1.0) * fraction, 6)
        row = (primary_factor, context_factor)
        if max(row) <= 1.025 or row in out:
            continue
        out.append(row)
    if primary_desired > 1.08:
        for context_fraction in (0.34, 0.0):
            row = (
                round(primary_desired, 6),
                round(1.0 + (context_desired - 1.0) * context_fraction, 6),
            )
            if row not in out:
                out.append(row)
    return out[:6]


def _pair_axis(primary: dict, context: dict) -> tuple[int, float]:
    primary_center = primary.get('card_rest_position_norm') or [0.5, 0.5]
    context_center = context.get('card_rest_position_norm') or [0.5, 0.5]
    dx = float(context_center[0]) - float(primary_center[0])
    dy = float(context_center[1]) - float(primary_center[1])
    axis = 0 if abs(dx) >= abs(dy) else 1
    delta = dx if axis == 0 else dy
    return axis, 1.0 if delta >= 0.0 else -1.0


def _fit_common_translation(rects: list[list[float]], centers: list[list[float]]) -> list[list[float]] | None:
    x0 = min(rect[0] for rect in rects)
    y0 = min(rect[1] for rect in rects)
    x1 = max(rect[0] + rect[2] for rect in rects)
    y1 = max(rect[1] + rect[3] for rect in rects)
    if x1 - x0 > SAFE_X[1] - SAFE_X[0] + 1e-9:
        return None
    if y1 - y0 > SAFE_Y[1] - SAFE_Y[0] + 1e-9:
        return None
    dx = max(SAFE_X[0] - x0, min(0.0, SAFE_X[1] - x1))
    dy = max(SAFE_Y[0] - y0, min(0.0, SAFE_Y[1] - y1))
    return [[round(center[0] + dx, 6), round(center[1] + dy, 6)] for center in centers]


def _pair_layout_candidates(plan: dict, primary: dict, context: dict, primary_factor: float, context_factor: float) -> list[tuple[list[float], list[float]]]:
    primary_scale = float(primary.get('layout_scale_multiplier') or 1.0) * primary_factor
    context_scale = float(context.get('layout_scale_multiplier') or 1.0) * context_factor
    primary_fp = _fp(primary)
    context_fp = _fp(context)
    primary_width = primary_fp.w * primary_scale * MOTION_ENVELOPE_SCALE
    primary_height = primary_fp.h * primary_scale * MOTION_ENVELOPE_SCALE
    context_width = context_fp.w * context_scale * MOTION_ENVELOPE_SCALE
    context_height = context_fp.h * context_scale * MOTION_ENVELOPE_SCALE
    if max(primary_width, context_width) > SAFE_X[1] - SAFE_X[0]:
        return []
    if max(primary_height, context_height) > SAFE_Y[1] - SAFE_Y[0]:
        return []

    axis, sign = _pair_axis(primary, context)
    primary_base = list(primary.get('card_rest_position_norm') or [0.5, 0.5])
    context_base = list(context.get('card_rest_position_norm') or [0.5, 0.5])
    primary_extent = primary_width if axis == 0 else primary_height
    context_extent = context_width if axis == 0 else context_height
    gap = max(0.025, min(0.065, 0.10 * min(primary_extent, context_extent)))
    separation = primary_extent / 2.0 + context_extent / 2.0 + gap
    cross_axis = 1 - axis
    cross_delta = max(-0.12, min(0.12, float(context_base[cross_axis]) - float(primary_base[cross_axis])))

    primary_destinations = _root_fit_destinations(plan, primary, primary_scale)
    if not primary_destinations:
        return []
    results: list[tuple[list[float], list[float]]] = []
    for primary_center in primary_destinations[:6]:
        for separation_factor in (1.0, 1.12):
            context_center = list(primary_center)
            context_center[axis] = float(primary_center[axis]) + sign * separation * separation_factor
            context_center[cross_axis] = float(primary_center[cross_axis]) + cross_delta
            primary_rect = list(_rect(primary_center, primary_fp, primary_scale * MOTION_ENVELOPE_SCALE))
            context_rect = list(_rect(context_center, context_fp, context_scale * MOTION_ENVELOPE_SCALE))
            fitted = _fit_common_translation([primary_rect, context_rect], [list(primary_center), context_center])
            if fitted is None:
                continue
            p_center, c_center = fitted
            if (c_center[axis] - p_center[axis]) * sign <= 1e-6:
                continue
            p_rect = list(_rect(p_center, primary_fp, primary_scale * MOTION_ENVELOPE_SCALE))
            c_rect = list(_rect(c_center, context_fp, context_scale * MOTION_ENVELOPE_SCALE))
            if not _in_safe(p_rect) or not _in_safe(c_rect):
                continue
            if any(math.dist(p_center, old_p) < 1e-6 and math.dist(c_center, old_c) < 1e-6 for old_p, old_c in results):
                continue
            results.append((p_center, c_center))
            if len(results) >= _MAX_PAIR_LAYOUTS:
                return results
    return results


def _apply_static_transform(event: dict, center: list[float], factor: float) -> None:
    old_center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    new_scale = float(event.get('layout_scale_multiplier') or 1.0) * factor
    rect = list(_rect(center, _fp(event), new_scale * MOTION_ENVELOPE_SCALE))
    event['card_rest_position_norm'] = [round(float(center[0]), 6), round(float(center[1]), 6)]
    event['layout_scale_multiplier'] = round(new_scale, 6)
    event['planned_rect_norm'] = [round(float(value), 6) for value in rect]
    event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
    for key in ('composition_states', 'composition_participant_states'):
        for state in event.get(key) or []:
            state_center = state.get('center_norm') or old_center
            if math.dist([float(state_center[0]), float(state_center[1])], [float(old_center[0]), float(old_center[1])]) <= 1e-6:
                state['center_norm'] = list(event['card_rest_position_norm'])


def _restore_pair(primary: dict, context: dict, snapshots: dict[str, dict]) -> None:
    for event in (primary, context):
        event_id = str(event.get('event_id') or '')
        snapshot = snapshots[event_id]
        event.clear()
        event.update(copy.deepcopy(snapshot))


def _candidate_pairs(plan: dict, fps: float) -> list[tuple[dict, dict, dict, float]]:
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    pairs: list[tuple[float, str, str, dict, dict, dict, float]] = []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    for card in cards:
        card_id = str(card.get('card_id') or '')
        quality = _card_quality(plan, card, step)
        if float(quality.get('underfilled_seconds') or 0.0) < 0.55 and float(quality.get('mean_ink') or 0.0) >= 0.20:
            continue
        local = [event for event in events if str(event.get('visual_card_id') or '') == card_id and _source_backed_root(event)]
        primaries = [event for event in local if str(event.get('attention_priority') or '').upper() == 'PRIMARY']
        contexts = [event for event in local if str(event.get('attention_priority') or '').upper() != 'PRIMARY']
        target_ink = _pair_target_ink(card, quality)
        duration = max(0.001, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))
        underfilled_ratio = min(1.0, float(quality.get('underfilled_seconds') or 0.0) / duration)
        for primary in primaries:
            for context in contexts:
                overlap = _overlap_seconds(primary, context)
                if overlap < _MIN_PAIR_OVERLAP_SECONDS or not _semantic_pair_allowed(card, primary, context):
                    continue
                combined = _projected_settled_ink(primary) + _projected_settled_ink(context)
                deficit = max(0.0, target_ink - combined)
                if deficit <= 0.004:
                    continue
                score = deficit * min(3.0, overlap) * (1.0 + 0.35 * underfilled_ratio)
                pairs.append((-score, str(primary.get('event_id') or ''), str(context.get('event_id') or ''), card, primary, context, target_ink))
    pairs.sort(key=lambda row: row[:3])
    return [(card, primary, context, target_ink) for _, _, _, card, primary, context, target_ink in pairs]


def _retry_semantic_after_joint_fit(plan: dict, fps: float, stats: dict) -> None:
    if not stats['joint_pairs_committed']:
        return
    events = plan.get('events') or []
    snapshots = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in events}
    before = build_visual_density_report(plan)
    semantic_stats = {
        'semantic_cascade_candidates_evaluated': 0,
        'semantic_cascade_committed': 0,
        'semantic_cascade_event_ids': [],
        'semantic_cascade_rejections': {},
    }
    _continue_semantic_sequences(plan, fps, semantic_stats)
    if semantic_stats['semantic_cascade_committed']:
        after = build_visual_density_report(plan)
        if not _density_not_worse(before, after) or not bool(composition_plan_qa(plan).get('pass')):
            _restore_all(events, snapshots)
            semantic_stats['semantic_cascade_rejections']['POST_JOINT_FULL_PLAN_QA'] = semantic_stats['semantic_cascade_committed']
            semantic_stats['semantic_cascade_committed'] = 0
            semantic_stats['semantic_cascade_event_ids'] = []
    stats['post_joint_semantic_candidates_evaluated'] = semantic_stats['semantic_cascade_candidates_evaluated']
    stats['post_joint_semantic_committed'] = semantic_stats['semantic_cascade_committed']
    stats['post_joint_semantic_event_ids'] = sorted(set(semantic_stats['semantic_cascade_event_ids']))
    stats['post_joint_semantic_rejections'] = dict(semantic_stats['semantic_cascade_rejections'])


def finalize_reference_joint_geometry(plan: dict, fps: float = 30.0) -> dict:
    """Jointly fit a semantic focal root and its context when independent fitting stalls."""
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    before = build_visual_density_report(plan)
    stats = {
        'authority': 'REFERENCE_COORDINATED_PRIMARY_CONTEXT_FIT_V2',
        'joint_pairs_requested': 0,
        'joint_candidates_evaluated': 0,
        'joint_pairs_committed': 0,
        'joint_event_ids': [],
        'joint_rejections': {},
        'joint_max_target_ink': 0.0,
        'post_joint_semantic_candidates_evaluated': 0,
        'post_joint_semantic_committed': 0,
        'post_joint_semantic_event_ids': [],
        'post_joint_semantic_rejections': {},
        'before_underfilled_seconds': round(sum(float(_card_quality(plan, card, step).get('underfilled_seconds') or 0.0) for card in cards), 6),
    }
    committed_ids: set[str] = set()

    for card, primary, context, target_ink in _candidate_pairs(plan, fps):
        if stats['joint_pairs_committed'] >= _MAX_PAIR_COMMITS:
            break
        primary_id = str(primary.get('event_id') or '')
        context_id = str(context.get('event_id') or '')
        if primary_id in committed_ids or context_id in committed_ids:
            continue
        stats['joint_pairs_requested'] += 1
        stats['joint_max_target_ink'] = max(float(stats['joint_max_target_ink']), float(target_ink))
        if not _static_root(primary) or not _static_root(context):
            stats['joint_rejections']['POSITION_OR_RENDER_AUTHORITY'] = stats['joint_rejections'].get('POSITION_OR_RENDER_AUTHORITY', 0) + 1
            continue
        scales = _pair_scale_ladder(primary, context, events, target_ink)
        if not scales:
            stats['joint_rejections']['NO_SOURCE_INK_DEFICIT'] = stats['joint_rejections'].get('NO_SOURCE_INK_DEFICIT', 0) + 1
            continue

        pre_quality = _card_quality(plan, card, step)
        pre_density = build_visual_density_report(plan)
        old_pair_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
        snapshots = {primary_id: copy.deepcopy(primary), context_id: copy.deepcopy(context)}
        committed = False
        for primary_factor, context_factor in scales:
            layouts = _pair_layout_candidates(plan, snapshots[primary_id], snapshots[context_id], primary_factor, context_factor)
            for primary_center, context_center in layouts:
                stats['joint_candidates_evaluated'] += 1
                _restore_pair(primary, context, snapshots)
                _apply_static_transform(primary, primary_center, primary_factor)
                _apply_static_transform(context, context_center, context_factor)
                if not _candidate_safe(plan, [primary, context], fps):
                    stats['joint_rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['joint_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                    continue
                post_quality = _card_quality(plan, card, step)
                post_density = build_visual_density_report(plan)
                new_pair_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
                material_card_gain = (
                    float(post_quality.get('underfilled_seconds') or 0.0) <= float(pre_quality.get('underfilled_seconds') or 0.0) - min(0.20, step * 2.0)
                    or float(post_quality.get('mean_ink') or 0.0) >= float(pre_quality.get('mean_ink') or 0.0) + 0.010
                )
                if new_pair_ink < old_pair_ink + _MIN_PAIR_INK_GAIN or not material_card_gain or not _density_not_worse(pre_density, post_density):
                    reason = (
                        'NO_MATERIAL_PAIR_INK_GAIN' if new_pair_ink < old_pair_ink + _MIN_PAIR_INK_GAIN
                        else 'NO_MATERIAL_CARD_GAIN' if not material_card_gain
                        else 'DENSITY_MONOTONICITY'
                    )
                    stats['joint_rejections'][reason] = stats['joint_rejections'].get(reason, 0) + 1
                    continue

                for event, partner, factor in ((primary, context, primary_factor), (context, primary, context_factor)):
                    event['reference_joint_fit_authority'] = 'SOURCE_BACKED_PRIMARY_CONTEXT_COORDINATED_STATIC_FIT_FULL_LIFETIME_CERTIFIED'
                    event['reference_joint_fit_partner_event_id'] = str(partner.get('event_id') or '')
                    event['reference_joint_fit_scale_factor'] = round(float(factor), 6)
                    event['reference_joint_fit_target_ink'] = round(float(target_ink), 6)
                    _sync_constraint_layout(plan, event)
                stats['joint_pairs_committed'] += 1
                stats['joint_event_ids'].extend([primary_id, context_id])
                committed_ids.update([primary_id, context_id])
                committed = True
                break
            if committed:
                break
        if not committed:
            _restore_pair(primary, context, snapshots)

    _retry_semantic_after_joint_fit(plan, fps, stats)
    after = build_visual_density_report(plan)
    stats['joint_event_ids'] = sorted(set(stats['joint_event_ids']))
    stats['joint_max_target_ink'] = round(float(stats['joint_max_target_ink']), 6)
    stats['after_underfilled_seconds'] = round(sum(float(_card_quality(plan, card, step).get('underfilled_seconds') or 0.0) for card in cards), 6)
    stats['changed'] = bool(stats['joint_pairs_committed'] or stats['post_joint_semantic_committed'])
    stats['pass'] = _density_not_worse(before, after) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        raise ValueError('REFERENCE_COORDINATED_PRIMARY_CONTEXT_FIT_FAILED')
    return stats
