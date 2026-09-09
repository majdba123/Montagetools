from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.composition_solver import SAFE_X, SAFE_Y, _in_safe
from hexa_v31.layout.position_authority import has_actual_center_travel
from hexa_v31.layout.reference_geometry_finalizer import (
    _candidate_safe,
    _density_not_worse,
    _root_fit_destinations,
    _sync_constraint_layout,
)
from hexa_v31.layout.reference_quality_finalizer import _card_quality
from hexa_v31.layout.reference_residual_closure import (
    _active_roots,
    _apply_geometry,
    _card_id,
    _event_id,
    _worst_interval,
)
from hexa_v31.visual_density import build_visual_density_report


_AUTHORITY = 'REFERENCE_PERCEPTUAL_RESIDUAL_CARD_CLOSURE_V1'
_MAX_CARD_COMMITS = 12
_MAX_COMMITS_PER_CARD = 2
_MAX_EVALUATIONS = 144
_SINGLE_PRIMARY_ABSOLUTE_SCALE_CAP = 4.0
_SINGLE_SUPPORT_ABSOLUTE_SCALE_CAP = 3.2
_GROUP_RELATIVE_SCALE_CAP = 1.55
# _card_quality uses a full-frame denominator, matching the encoded occupancy
# measurement. build_visual_density_report's logged estimated-alpha metric is
# safe-frame-normalized and MUST NOT be compared numerically to this value.
# Residual closure therefore targets 24%+ full-frame projected ink directly,
# with extra headroom on severe cards, instead of deriving a false calibration
# from the safe-frame-normalized global proxy.
_RESIDUAL_MEAN_INK_FLOOR = 0.24
_TARGET_SEVERE_INK = 0.28
_TARGET_MODERATE_INK = 0.26
_MIN_SETTLED_INTERVAL = 0.45
_MIN_SINGLE_MEAN_GAIN = 0.030
_MIN_GROUP_MEAN_GAIN = 0.025
_MIN_UNDERFILL_GAIN = 0.50


def _card_duration(card: dict) -> float:
    return max(0.001, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))


def _residual(card: dict, quality: dict) -> bool:
    return (
        float(quality.get('underfilled_seconds') or 0.0) >= 0.55
        or float(quality.get('mean_ink') or 0.0) < _RESIDUAL_MEAN_INK_FLOOR
    )


def _severity(card: dict, quality: dict) -> float:
    duration = _card_duration(card)
    under = min(1.0, float(quality.get('underfilled_seconds') or 0.0) / duration)
    ink = float(quality.get('mean_ink') or 0.0)
    pop = float(quality.get('mean_population') or 0.0)
    return 3.0 * under + 3.5 * max(0.0, _RESIDUAL_MEAN_INK_FLOOR - ink) + 0.4 * max(0.0, 1.5 - pop)


def _target_ink(quality: dict) -> float:
    return _TARGET_SEVERE_INK if float(quality.get('mean_ink') or 0.0) < 0.16 else _TARGET_MODERATE_INK


def _eligible_static_root(event: dict) -> bool:
    return (
        str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and not event.get('suppressed_by_card_density')
        and event.get('visible_ink_fraction') is not None
        and bool(event.get('planned_rect_norm'))
        and not has_actual_center_travel(event)
    )


def _settled_overlap(event: dict, interval: dict) -> float:
    start = max(
        float(interval.get('start_seconds') or 0.0),
        float(event.get('settle_seconds', event.get('start_seconds', 0.0))),
    )
    end = min(
        float(interval.get('end_seconds') or start),
        float(event.get('physical_end_seconds', event.get('end_seconds', start))),
    )
    return max(0.0, end - start)


def _semantic_cohort(card: dict, roots: list[dict]) -> bool:
    if len(roots) < 2:
        return True
    scenes = {str(event.get('scene_id') or '') for event in roots if event.get('scene_id')}
    if len(scenes) == 1:
        return True
    ids = {_event_id(event) for event in roots}
    return any(
        ids.issubset({str(event_id) for event_id in phase.get('event_ids') or []})
        for phase in (card.get('story_phase_plan') or {}).get('phases') or []
    )


def _residual_interval(plan: dict, card: dict, step: float, quality: dict) -> dict | None:
    """Return the worst sparse interval using this stage's own 24% authority.

    The older residual pass falls back to a whole-card interval only below 22%.
    Reusing that fallback directly would create a blind 22-24% band: a card
    could be classified residual here but have no candidate interval. Preserve
    the older pass unchanged and close that band locally.
    """
    interval = _worst_interval(plan, card, step, quality)
    if interval is not None:
        return interval
    if float(quality.get('mean_ink') or 0.0) >= _RESIDUAL_MEAN_INK_FLOOR:
        return None
    start = float(card.get('start_seconds', 0.0))
    end = float(card.get('end_seconds', start))
    if end - start < _MIN_SETTLED_INTERVAL:
        return None
    return {
        'card_id': _card_id(card),
        'start_seconds': start,
        'end_seconds': end,
        'duration_seconds': end - start,
        'mean_projected_ink': float(quality.get('mean_ink') or 0.0),
        'authority': 'REFERENCE_PERCEPTUAL_RESIDUAL_WHOLE_CARD_FALLBACK',
    }


def _material_gain(before: dict, after: dict, *, group: bool) -> bool:
    mean_gain = float(after.get('mean_ink') or 0.0) - float(before.get('mean_ink') or 0.0)
    under_gain = float(before.get('underfilled_seconds') or 0.0) - float(after.get('underfilled_seconds') or 0.0)
    minimum = _MIN_GROUP_MEAN_GAIN if group else _MIN_SINGLE_MEAN_GAIN
    return mean_gain >= minimum or (under_gain >= _MIN_UNDERFILL_GAIN and mean_gain >= minimum * 0.5)


def _single_absolute_scales(event: dict, quality: dict) -> list[float]:
    old = max(1e-6, float(event.get('layout_scale_multiplier') or 1.0))
    primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
    cap = _SINGLE_PRIMARY_ABSOLUTE_SCALE_CAP if primary else _SINGLE_SUPPORT_ABSOLUTE_SCALE_CAP
    target = _target_ink(quality)
    mean = max(0.01, float(quality.get('mean_ink') or 0.0))
    desired = min(cap, old * math.sqrt(target / mean))
    values = [
        min(cap, desired * 1.04),
        desired,
        min(cap, max(desired * 0.94, old * 1.55)),
        min(cap, old * 1.75),
        min(cap, old * 1.45),
        min(cap, old * 1.25),
    ]
    out: list[float] = []
    for value in values:
        value = round(float(value), 6)
        if value <= old * 1.04 or value in out:
            continue
        out.append(value)
    return out


def _commit_single(plan: dict, card: dict, event: dict, quality: dict, fps: float, stats: dict) -> bool:
    snapshot = copy.deepcopy(event)
    old_density = build_visual_density_report(plan)
    old_scale = float(event.get('layout_scale_multiplier') or 1.0)
    old_center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    for absolute_scale in _single_absolute_scales(event, quality):
        for center in _root_fit_destinations(plan, snapshot, absolute_scale)[:5]:
            if stats['candidates_evaluated'] >= _MAX_EVALUATIONS:
                event.clear(); event.update(snapshot)
                return False
            stats['candidates_evaluated'] += 1
            event.clear(); event.update(copy.deepcopy(snapshot))
            _apply_geometry(event, list(center), absolute_scale / max(1e-6, old_scale))
            if not _in_safe(event.get('planned_rect_norm') or []):
                stats['rejections']['SAFE_FRAME'] = stats['rejections'].get('SAFE_FRAME', 0) + 1
                continue
            if not _candidate_safe(plan, [event], fps):
                stats['rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                continue
            after_quality = _card_quality(plan, card, stats['sample_step_seconds'])
            after_density = build_visual_density_report(plan)
            if not _density_not_worse(old_density, after_density):
                stats['rejections']['DENSITY_MONOTONICITY'] = stats['rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                continue
            target = _target_ink(quality)
            target_progress = float(after_quality.get('mean_ink') or 0.0) >= min(target, float(quality.get('mean_ink') or 0.0) + 0.05)
            if not target_progress or not _material_gain(quality, after_quality, group=False):
                stats['rejections']['NO_MATERIAL_PERCEPTUAL_GAIN'] = stats['rejections'].get('NO_MATERIAL_PERCEPTUAL_GAIN', 0) + 1
                continue
            event['reference_perceptual_residual_authority'] = _AUTHORITY
            event['reference_perceptual_residual_card_id'] = _card_id(card)
            event['reference_perceptual_residual_scale_before'] = round(old_scale, 6)
            event['reference_perceptual_residual_scale_after'] = round(float(event.get('layout_scale_multiplier') or 1.0), 6)
            event['reference_perceptual_residual_quality_before'] = copy.deepcopy(quality)
            event['reference_perceptual_residual_quality_after'] = copy.deepcopy(after_quality)
            _sync_constraint_layout(plan, event)
            stats['commits'] += 1
            stats['single_root_commits'] += 1
            stats['event_ids'].append(_event_id(event))
            stats['mutations'].append({
                'card_id': _card_id(card),
                'strategy': 'SINGLE_ROOT_PERCEPTUAL_FILL',
                'event_ids': [_event_id(event)],
                'before_center_norm': old_center,
                'after_center_norm': list(event.get('card_rest_position_norm') or []),
                'before_scale': round(old_scale, 6),
                'after_scale': round(float(event.get('layout_scale_multiplier') or 1.0), 6),
                'before_quality': copy.deepcopy(quality),
                'after_quality': copy.deepcopy(after_quality),
            })
            return True
    event.clear()
    event.update(snapshot)
    return False


def _group_factors(quality: dict) -> list[float]:
    target = _target_ink(quality)
    mean = max(0.02, float(quality.get('mean_ink') or 0.0))
    desired = min(_GROUP_RELATIVE_SCALE_CAP, math.sqrt(target / mean))
    values = [min(_GROUP_RELATIVE_SCALE_CAP, desired * 1.04), desired, 1.42, 1.32, 1.24, 1.16, 1.10]
    out: list[float] = []
    for value in values:
        value = round(float(value), 6)
        if value <= 1.04 or value > _GROUP_RELATIVE_SCALE_CAP + 1e-6 or value in out:
            continue
        out.append(value)
    out.sort(reverse=True)
    return out


def _group_centroid(roots: list[dict]) -> list[float]:
    centers = [event.get('card_rest_position_norm') or [0.5, 0.5] for event in roots]
    return [
        sum(float(center[0]) for center in centers) / len(centers),
        sum(float(center[1]) for center in centers) / len(centers),
    ]


def _fit_group_translation(roots: list[dict]) -> tuple[bool, float, float]:
    rects = [list(map(float, event.get('planned_rect_norm') or [])) for event in roots]
    if any(len(rect) != 4 for rect in rects):
        return False, 0.0, 0.0
    x0 = min(rect[0] for rect in rects)
    y0 = min(rect[1] for rect in rects)
    x1 = max(rect[0] + rect[2] for rect in rects)
    y1 = max(rect[1] + rect[3] for rect in rects)
    if x1 - x0 > SAFE_X[1] - SAFE_X[0] or y1 - y0 > SAFE_Y[1] - SAFE_Y[0]:
        return False, 0.0, 0.0
    dx = max(SAFE_X[0] - x0, min(0.0, SAFE_X[1] - x1))
    dy = max(SAFE_Y[0] - y0, min(0.0, SAFE_Y[1] - y1))
    return True, dx, dy


def _commit_group(plan: dict, card: dict, roots: list[dict], quality: dict, fps: float, stats: dict) -> bool:
    if not (2 <= len(roots) <= 3) or not _semantic_cohort(card, roots):
        return False
    snapshots = {_event_id(event): copy.deepcopy(event) for event in roots}
    old_density = build_visual_density_report(plan)
    centroid = _group_centroid(roots)
    for factor in _group_factors(quality):
        if stats['candidates_evaluated'] >= _MAX_EVALUATIONS:
            break
        stats['candidates_evaluated'] += 1
        spread = min(1.14, max(1.0, math.sqrt(factor)))
        for event in roots:
            snapshot = snapshots[_event_id(event)]
            event.clear()
            event.update(copy.deepcopy(snapshot))
            old_center = snapshot.get('card_rest_position_norm') or [0.5, 0.5]
            center = [
                centroid[0] + (float(old_center[0]) - centroid[0]) * spread,
                centroid[1] + (float(old_center[1]) - centroid[1]) * spread,
            ]
            _apply_geometry(event, center, factor)
        fits, dx, dy = _fit_group_translation(roots)
        if not fits:
            stats['rejections']['SAFE_FRAME'] = stats['rejections'].get('SAFE_FRAME', 0) + 1
            continue
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            translated_centers = {
                _event_id(event): [
                    float((event.get('card_rest_position_norm') or [0.5, 0.5])[0]) + dx,
                    float((event.get('card_rest_position_norm') or [0.5, 0.5])[1]) + dy,
                ]
                for event in roots
            }
            for event in roots:
                snapshot = snapshots[_event_id(event)]
                event.clear()
                event.update(copy.deepcopy(snapshot))
                _apply_geometry(event, translated_centers[_event_id(event)], factor)
        if any(not _in_safe(event.get('planned_rect_norm') or []) for event in roots):
            stats['rejections']['SAFE_FRAME'] = stats['rejections'].get('SAFE_FRAME', 0) + 1
            continue
        if not _candidate_safe(plan, roots, fps):
            stats['rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
            continue
        after_quality = _card_quality(plan, card, stats['sample_step_seconds'])
        after_density = build_visual_density_report(plan)
        if not _density_not_worse(old_density, after_density):
            stats['rejections']['DENSITY_MONOTONICITY'] = stats['rejections'].get('DENSITY_MONOTONICITY', 0) + 1
            continue
        if not _material_gain(quality, after_quality, group=True):
            stats['rejections']['NO_MATERIAL_PERCEPTUAL_GAIN'] = stats['rejections'].get('NO_MATERIAL_PERCEPTUAL_GAIN', 0) + 1
            continue
        for event in roots:
            event['reference_perceptual_residual_authority'] = _AUTHORITY
            event['reference_perceptual_residual_card_id'] = _card_id(card)
            _sync_constraint_layout(plan, event)
        stats['commits'] += 1
        stats['group_commits'] += 1
        ids = sorted(_event_id(event) for event in roots)
        stats['event_ids'].extend(ids)
        stats['mutations'].append({
            'card_id': _card_id(card),
            'strategy': 'STATIC_SEMANTIC_COHORT_PERCEPTUAL_FILL',
            'event_ids': ids,
            'relative_scale_factor': round(float(factor), 6),
            'before_quality': copy.deepcopy(quality),
            'after_quality': copy.deepcopy(after_quality),
        })
        return True
    for event in roots:
        event.clear()
        event.update(snapshots[_event_id(event)])
    return False


def finalize_reference_perceptual_residual(plan: dict, fps: float = 30.0) -> dict:
    """Close perceptually material residual sparsity after all normal fitters.

    The stage is deliberately narrow: it acts only on sustained residual cards,
    never on partitions or center-travel actors. Single visible roots may use
    additional safe-frame headroom because pair/cohort fitters cannot help them.
    Small static semantic cohorts may receive at most two uniform,
    hierarchy-preserving card transforms. Every commit remains deterministic,
    source-backed, atomic, full-lifetime collision certified, and density
    monotonic.
    """
    original = copy.deepcopy(plan)
    before_density = build_visual_density_report(plan)
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    before_quality = {_card_id(card): _card_quality(plan, card, step) for card in cards}
    stats = {
        'authority': _AUTHORITY,
        'sample_step_seconds': round(step, 6),
        'commits': 0,
        'single_root_commits': 0,
        'group_commits': 0,
        'candidates_evaluated': 0,
        'event_ids': [],
        'mutations': [],
        'rejections': {},
        'ink_denominator_authority': 'FULL_FRAME_PROJECTED_SOURCE_INK__MATCHES_ENCODED_OCCUPANCY_DENOMINATOR',
        'before_residual_card_ids': sorted(_card_id(card) for card in cards if _residual(card, before_quality[_card_id(card)])),
    }
    exhausted_cards: set[str] = set()
    per_card_commits: dict[str, int] = {}
    while stats['commits'] < _MAX_CARD_COMMITS and stats['candidates_evaluated'] < _MAX_EVALUATIONS:
        ranked = []
        for card in cards:
            cid = _card_id(card)
            if cid in exhausted_cards or per_card_commits.get(cid, 0) >= _MAX_COMMITS_PER_CARD:
                continue
            quality = _card_quality(plan, card, step)
            if not _residual(card, quality):
                exhausted_cards.add(cid)
                continue
            interval = _residual_interval(plan, card, step, quality)
            if interval is None:
                exhausted_cards.add(cid)
                continue
            roots = [
                event for event in _active_roots(plan, card, interval)
                if _eligible_static_root(event) and _settled_overlap(event, interval) >= _MIN_SETTLED_INTERVAL
            ]
            ranked.append((-_severity(card, quality), cid, card, quality, interval, roots))
        ranked.sort(key=lambda row: row[:2])
        changed = False
        for _, cid, card, quality, interval, roots in ranked:
            if not roots:
                stats['rejections']['NO_STATIC_SOURCE_ROOT'] = stats['rejections'].get('NO_STATIC_SOURCE_ROOT', 0) + 1
                exhausted_cards.add(cid)
                continue
            strategy_committed = False
            if len(roots) == 1:
                strategy_committed = _commit_single(plan, card, roots[0], quality, fps, stats)
            elif 2 <= len(roots) <= 3:
                strategy_committed = _commit_group(plan, card, roots, quality, fps, stats)
                if not strategy_committed:
                    for event in roots:
                        if _commit_single(plan, card, event, quality, fps, stats):
                            strategy_committed = True
                            break
            if strategy_committed:
                per_card_commits[cid] = per_card_commits.get(cid, 0) + 1
                post_quality = _card_quality(plan, card, step)
                if not _residual(card, post_quality) or per_card_commits[cid] >= _MAX_COMMITS_PER_CARD:
                    exhausted_cards.add(cid)
                changed = True
                break
            exhausted_cards.add(cid)
        if not changed:
            break

    after_density = build_visual_density_report(plan)
    after_quality = {_card_id(card): _card_quality(plan, card, step) for card in cards}
    unresolved = sorted(_card_id(card) for card in cards if _residual(card, after_quality[_card_id(card)]))
    stats['event_ids'] = sorted(set(stats['event_ids']))
    stats['after_residual_card_ids'] = unresolved
    stats['resolved_card_ids'] = sorted(set(stats['before_residual_card_ids']) - set(unresolved))
    stats['per_card_commit_counts'] = dict(sorted(per_card_commits.items()))
    stats['closure_satisfied'] = not unresolved
    stats['before_mean_projected_ink'] = round(sum(float(row.get('mean_ink') or 0.0) for row in before_quality.values()) / max(1, len(before_quality)), 6)
    stats['after_mean_projected_ink'] = round(sum(float(row.get('mean_ink') or 0.0) for row in after_quality.values()) / max(1, len(after_quality)), 6)
    stats['before_underfilled_seconds'] = round(sum(float(row.get('underfilled_seconds') or 0.0) for row in before_quality.values()), 6)
    stats['after_underfilled_seconds'] = round(sum(float(row.get('underfilled_seconds') or 0.0) for row in after_quality.values()), 6)
    stats['changed'] = bool(stats['commits'])
    stats['pass'] = _density_not_worse(before_density, after_density) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        plan.clear()
        plan.update(original)
        raise ValueError('REFERENCE_PERCEPTUAL_RESIDUAL_CARD_CLOSURE_FAILED')
    return stats
