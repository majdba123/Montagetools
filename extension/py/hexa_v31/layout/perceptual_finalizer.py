from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _in_safe, _rect
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel
from hexa_v31.visual_density import build_visual_density_report


_INK_MODEL = ProjectedVisibleInkModel()


def _physical_interval(event: dict) -> tuple[float, float]:
    return (
        float(event.get('physical_start_seconds', event.get('start_seconds', 0.0))),
        float(event.get('physical_end_seconds', event.get('end_seconds', 0.0))),
    )


def _overlap_seconds(a: dict, b: dict) -> float:
    ast, aen = _physical_interval(a)
    bst, ben = _physical_interval(b)
    return max(0.0, min(aen, ben) - max(ast, bst))


def _affected_cards(event: dict, cards: list[dict]) -> list[dict]:
    est, een = _physical_interval(event)
    return [
        card for card in cards
        if est < float(card.get('end_seconds', 0.0)) - 1e-6
        and een > float(card.get('start_seconds', 0.0)) + 1e-6
    ]


def _card_neighbors(events: list[dict], card: dict) -> list[dict]:
    cs = float(card.get('start_seconds', 0.0))
    ce = float(card.get('end_seconds', cs))
    return [
        event for event in events
        if not event.get('suppressed_by_card_density')
        and _physical_interval(event)[0] < ce - 1e-6
        and _physical_interval(event)[1] > cs + 1e-6
    ]


def _candidate_safe(plan: dict, event: dict, fps: float) -> bool:
    from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe as geometry_safe

    return geometry_safe(plan, [event], fps)


def _density_not_worse(before: dict, after: dict) -> bool:
    return (
        float(after.get('near_blank_duration_seconds', 0.0))
        <= float(before.get('near_blank_duration_seconds', 0.0)) + 0.01
        and float(after.get('median_safe_frame_union_coverage', 0.0))
        >= float(before.get('median_safe_frame_union_coverage', 0.0)) - 0.001
        and float(after.get('mean_temporal_population', 0.0))
        >= float(before.get('mean_temporal_population', 0.0)) - 0.001
    )


def _sync_constraint_layout(plan: dict, event: dict) -> None:
    event_id = str(event.get('event_id') or '')
    card_id = str(event.get('visual_card_id') or '')
    for card in (plan.get('visual_cards') or {}).get('cards') or []:
        if str(card.get('card_id') or '') != card_id:
            continue
        placement = ((card.get('constraint_layout') or {}).get('placements') or {}).get(event_id)
        if placement is None:
            return
        placement['center_norm'] = list(event.get('card_rest_position_norm') or [0.5, 0.5])
        placement['scale'] = float(event.get('layout_scale_multiplier') or 1.0)
        placement['rect_norm'] = list(event.get('planned_rect_norm') or [])
        return


def _projected_settled_ink(event: dict) -> float:
    footprint = _fp(event)
    scale = max(0.0, float(event.get('layout_scale_multiplier') or 1.0))
    return max(0.0, footprint.visible_area * scale * scale)


def _scale_target(event: dict, events: list[dict]) -> tuple[float, float]:
    primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
    simultaneous = any(
        other is not event
        and not other.get('suppressed_by_card_density')
        and _overlap_seconds(event, other) >= 0.25
        for other in events
    )
    if primary:
        return (0.20 if simultaneous else 0.26, 1.65)
    return (0.095 if simultaneous else 0.13, 1.35)


def _scale_source_backed_actors(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    density = build_visual_density_report(plan)
    ordered = sorted(
        (
            event for event in events
            if not event.get('suppressed_by_card_density')
            and str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
            and event.get('planned_rect_norm')
            and event.get('visible_ink_fraction') is not None
        ),
        key=lambda event: (
            0 if str(event.get('attention_priority') or '').upper() == 'PRIMARY' else 1,
            _projected_settled_ink(event),
            str(event.get('event_id') or ''),
        ),
    )
    for event in ordered:
        target, factor_cap = _scale_target(event, events)
        current_ink = _projected_settled_ink(event)
        if current_ink >= target - 1e-6 or current_ink <= 1e-8:
            continue
        desired = math.sqrt(target / current_ink)
        candidate_max = min(factor_cap, desired)
        if candidate_max <= 1.025:
            continue
        ladder = [candidate_max, 1.50, 1.38, 1.30, 1.22, 1.14, 1.08]
        factors = []
        for factor in ladder:
            factor = round(float(factor), 6)
            if factor <= 1.025 or factor > candidate_max + 1e-6 or factor in factors:
                continue
            factors.append(factor)
        snapshot = copy.deepcopy(event)
        old_density = density
        old_scale = float(event.get('layout_scale_multiplier') or 1.0)
        center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
        footprint = _fp(event)
        committed = False
        stats['scale_candidates_requested'] += 1
        for factor in factors:
            stats['scale_candidates_evaluated'] += 1
            new_scale = old_scale * factor
            rect = list(_rect(
                (float(center[0]), float(center[1])),
                footprint,
                new_scale * MOTION_ENVELOPE_SCALE,
            ))
            if not _in_safe(rect):
                stats['scale_rejections']['SAFE_FRAME'] = stats['scale_rejections'].get('SAFE_FRAME', 0) + 1
                continue
            event['layout_scale_multiplier'] = round(new_scale, 6)
            event['planned_rect_norm'] = [round(value, 6) for value in rect]
            event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
            if not _candidate_safe(plan, event, fps):
                event.clear(); event.update(copy.deepcopy(snapshot))
                stats['scale_rejections']['COLLISION_OR_PATH'] = stats['scale_rejections'].get('COLLISION_OR_PATH', 0) + 1
                continue
            candidate_density = build_visual_density_report(plan)
            if not _density_not_worse(old_density, candidate_density):
                event.clear(); event.update(copy.deepcopy(snapshot))
                stats['scale_rejections']['DENSITY_MONOTONICITY'] = stats['scale_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                continue
            new_ink = _projected_settled_ink(event)
            if new_ink <= current_ink + 0.005:
                event.clear(); event.update(copy.deepcopy(snapshot))
                stats['scale_rejections']['NO_MATERIAL_INK_GAIN'] = stats['scale_rejections'].get('NO_MATERIAL_INK_GAIN', 0) + 1
                continue
            event['final_visible_ink_scale_authority'] = 'SOURCE_BACKED_INK_WITH_FULL_LIFETIME_COLLISION_CERTIFICATION'
            event['final_visible_ink_before'] = round(current_ink, 6)
            event['final_visible_ink_after'] = round(new_ink, 6)
            event['final_visible_ink_scale_factor'] = factor
            _sync_constraint_layout(plan, event)
            density = candidate_density
            stats['scaled_event_ids'].append(str(event.get('event_id') or ''))
            stats['scale_candidates_committed'] += 1
            committed = True
            break
        if not committed:
            event.clear(); event.update(snapshot)


def _amplify_existing_hierarchy(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    density = build_visual_density_report(plan)
    for event in sorted(events, key=lambda row: str(row.get('event_id') or '')):
        if event.get('suppressed_by_card_density'):
            continue
        if str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
            continue
        if not event.get('meaningful_recomposition'):
            continue
        states = event.get('composition_states') or []
        if len(states) < 2:
            continue
        state = states[-1]
        if bool(state.get('translation_safe')):
            continue
        current = float(state.get('scale_multiplier') or 1.0)
        candidates = [value for value in (1.26, 1.22, 1.18, 1.14) if value > current + 0.015]
        if not candidates:
            continue
        snapshot = copy.deepcopy(event)
        old_density = density
        stats['hierarchy_candidates_requested'] += 1
        for scale in candidates:
            stats['hierarchy_candidates_evaluated'] += 1
            state['scale_multiplier'] = scale
            if not _candidate_safe(plan, event, fps):
                event.clear(); event.update(copy.deepcopy(snapshot))
                states = event.get('composition_states') or []
                state = states[-1]
                stats['hierarchy_rejections']['COLLISION_OR_PATH'] = stats['hierarchy_rejections'].get('COLLISION_OR_PATH', 0) + 1
                continue
            candidate_density = build_visual_density_report(plan)
            if not _density_not_worse(old_density, candidate_density):
                event.clear(); event.update(copy.deepcopy(snapshot))
                states = event.get('composition_states') or []
                state = states[-1]
                stats['hierarchy_rejections']['DENSITY_MONOTONICITY'] = stats['hierarchy_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                continue
            event['final_hierarchy_amplitude_authority'] = 'EXISTING_SEMANTIC_RECOMPOSITION_FULL_LIFETIME_CERTIFIED'
            event['final_hierarchy_scale_before'] = round(current, 6)
            event['final_hierarchy_scale_after'] = round(scale, 6)
            density = candidate_density
            stats['hierarchy_event_ids'].append(str(event.get('event_id') or ''))
            stats['hierarchy_candidates_committed'] += 1
            break


def finalize_perceptual_composition(plan: dict, fps: float = 30.0) -> dict:
    """Strengthen source-backed density and existing semantic hierarchy safely.

    This is a final bounded candidate pass. It never changes source identity,
    partition membership, card ownership, timing, translation policy, or preset
    vocabulary. Every committed geometry/state candidate is checked over every
    affected physical card and against the complete composition QA authority.
    """
    before = build_visual_density_report(plan)
    stats = {
        'authority': 'FINAL_SOURCE_BACKED_PERCEPTUAL_COMPOSITION_V1',
        'scale_candidates_requested': 0,
        'scale_candidates_evaluated': 0,
        'scale_candidates_committed': 0,
        'scaled_event_ids': [],
        'scale_rejections': {},
        'hierarchy_candidates_requested': 0,
        'hierarchy_candidates_evaluated': 0,
        'hierarchy_candidates_committed': 0,
        'hierarchy_event_ids': [],
        'hierarchy_rejections': {},
        'before_median_safe_frame_union_coverage': before.get('median_safe_frame_union_coverage'),
        'before_mean_temporal_population': before.get('mean_temporal_population'),
        'before_near_blank_duration_seconds': before.get('near_blank_duration_seconds'),
    }
    _scale_source_backed_actors(plan, fps, stats)
    _amplify_existing_hierarchy(plan, fps, stats)
    after = build_visual_density_report(plan)
    stats['after_median_safe_frame_union_coverage'] = after.get('median_safe_frame_union_coverage')
    stats['after_mean_temporal_population'] = after.get('mean_temporal_population')
    stats['after_near_blank_duration_seconds'] = after.get('near_blank_duration_seconds')
    stats['changed'] = bool(stats['scale_candidates_committed'] or stats['hierarchy_candidates_committed'])
    stats['pass'] = _density_not_worse(before, after) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        raise ValueError('FINAL_SOURCE_BACKED_PERCEPTUAL_COMPOSITION_FAILED')
    return stats
