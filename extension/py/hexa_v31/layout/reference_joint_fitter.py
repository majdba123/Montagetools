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
from hexa_v31.layout.position_authority import (
    _preset_moves_center, has_actual_center_travel as _joint_position_authority,
)
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



def _static_root(event: dict) -> bool:
    return _source_backed_root(event) and not _joint_position_authority(event)


def _pair_target_ink(card: dict, quality: dict) -> float:
    duration = max(0.001, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))
    underfilled_ratio = min(1.0, max(0.0, float(quality.get('underfilled_seconds') or 0.0) / duration))
    mean_ink = max(0.0, float(quality.get('mean_ink') or 0.0))
    ink_deficit_ratio = min(1.0, max(0.0, (0.20 - mean_ink) / 0.20))
    severity = max(underfilled_ratio, ink_deficit_ratio)
    return round(_PAIR_TARGET_INK + (_MAX_SEVERE_PAIR_TARGET_INK - _PAIR_TARGET_INK) * severity, 6)


def _viewport_scale_cap(event: dict) -> float:
    fp = _fp(event)
    hierarchy = max([1.] + [float(s.get('scale_multiplier') or 1.)
        for key in ('composition_states', 'composition_participant_states') for s in event.get(key) or []])
    scale = float(event.get('layout_scale_multiplier') or 1.) * MOTION_ENVELOPE_SCALE * hierarchy
    return max(1., min((SAFE_X[1]-SAFE_X[0])/max(1e-9,fp.w*scale),
                       (SAFE_Y[1]-SAFE_Y[0])/max(1e-9,fp.h*scale)))


def _pair_scale_ladder(primary: dict, context: dict, events: list[dict], pair_target_ink: float) -> list[tuple[float, float]]:
    primary_ink = _projected_settled_ink(primary)
    context_ink = _projected_settled_ink(context)
    combined = primary_ink + context_ink
    if primary_ink <= 1e-9 or context_ink <= 1e-9 or combined >= pair_target_ink - 1e-6:
        return []
    primary_target, primary_cap = _root_scale_target(primary, events)
    context_target, context_cap = _root_scale_target(context, events)
    primary_cap = min(primary_cap, _viewport_scale_cap(primary))
    context_cap = min(context_cap, _viewport_scale_cap(context))
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
    if context_desired > 1.08:
        row = (1.0, round(context_desired, 6))
        if row not in out:
            out.append(row)
    # A support may yield some static area to the focal source, provided the
    # complete card gains ink and retains its hierarchy. This is a joint area
    # allocation, not independent enlargement against a fixed blocker.
    if primary_desired > 1.08:
        out.extend([(round(primary_desired,6), .90), (round(primary_desired,6), .80)])
    return out[:9]


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


def _pair_axis_layout_candidates(plan: dict, primary: dict, context: dict, primary_factor: float, context_factor: float, alternate: bool = False) -> list[tuple[list[float], list[float]]]:
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
    if alternate:
        axis = 1 - axis
        p = primary.get('card_rest_position_norm') or [.5,.5]
        c = context.get('card_rest_position_norm') or [.5,.5]
        sign = 1. if c[axis] >= p[axis] else -1.
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


def _pair_layout_candidates(plan, primary, context, primary_factor, context_factor):
    # The same semantic roles can occupy side-by-side or stacked negative
    # space. Two axes with six slots each remain a fixed search bound.
    return (_pair_axis_layout_candidates(plan, primary, context, primary_factor, context_factor)[:6]
            + _pair_axis_layout_candidates(plan, primary, context, primary_factor, context_factor, True)[:6])


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


def _semantic_context(event: dict) -> bool:
    # Attention is a presentation budget, not a semantic relationship. A
    # promoted PRIMARY can still be the source-backed context of a lead.
    return (
        str(event.get('semantic_role') or '').upper() in {'SUPPORTING', 'SUPPORT', 'CONTEXT'}
        or str(event.get('composition_role') or '').upper() in {'SUPPORT', 'CONTEXT'}
        or str(event.get('relationship') or '').upper() == 'CONTEXT_FOR'
        or str(event.get('attention_priority') or '').upper() != 'PRIMARY'
    )


def _secondary_support(plan: dict, card: dict, primary: dict, context: dict) -> dict | None:
    candidates = [e for e in plan.get('events') or []
                  if e is not primary and e is not context and _static_root(e)
                  and _semantic_context(e) and _semantic_pair_allowed(card, primary, e)
                  and max(float(x.get('physical_start_seconds', x.get('start_seconds', 0)))
                          for x in (primary, context, e)) + _MIN_PAIR_OVERLAP_SECONDS
                  <= min(float(x.get('physical_end_seconds', x.get('end_seconds', 0)))
                         for x in (primary, context, e))]
    # One semantic successor only; never enumerate arbitrary triples.
    candidates.sort(key=lambda e: (float(e.get('perceptual_hit_seconds', 0)), str(e.get('event_id'))))
    return candidates[0] if candidates else None


def _cohort_layouts(plan, primary, context, secondary, factors):
    if secondary is None:
        return [list(row) for row in _pair_layout_candidates(plan, primary, context, *factors[:2])]
    # Use the established focal/context axis. Place the optional support on
    # its authored side in the orthogonal negative space, preserving order.
    axis, _ = _pair_axis(primary, context)
    cross = 1 - axis
    output = []
    for centers in _pair_layout_candidates(plan, primary, context, *factors[:2])[:6]:
        center = list(centers[1])
        original = secondary.get('card_rest_position_norm') or [.5, .5]
        base = context.get('card_rest_position_norm') or [.5, .5]
        sign = 1 if original[cross] >= base[cross] else -1
        rects = [list(_rect(c, _fp(e), float(e.get('layout_scale_multiplier') or 1)*f*MOTION_ENVELOPE_SCALE))
                 for e, c, f in zip((primary, context), centers, factors)]
        sr = list(_rect(center, _fp(secondary), float(secondary.get('layout_scale_multiplier') or 1)*factors[2]*MOTION_ENVELOPE_SCALE))
        center[cross] += sign * (.025 + (rects[1][cross+2]+sr[cross+2])/2)
        sr = list(_rect(center, _fp(secondary), float(secondary.get('layout_scale_multiplier') or 1)*factors[2]*MOTION_ENVELOPE_SCALE))
        fitted = _fit_common_translation(rects+[sr], [list(c) for c in centers]+[center])
        if fitted is not None:
            output.append(fitted)
    return output


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
        primaries = [event for event in local if str(event.get('attention_priority') or '').upper() == 'PRIMARY' and not _semantic_context(event)]
        contexts = [event for event in local if _semantic_context(event)]
        target_ink = _pair_target_ink(card, quality)
        duration = max(0.001, float(card.get('end_seconds', 0.0)) - float(card.get('start_seconds', 0.0)))
        underfilled_ratio = min(1.0, float(quality.get('underfilled_seconds') or 0.0) / duration)
        for primary in primaries:
            for context in contexts:
                overlap = _overlap_seconds(primary, context)
                if overlap < _MIN_PAIR_OVERLAP_SECONDS or not _semantic_pair_allowed(card, primary, context):
                    continue
                combined = _projected_settled_ink(primary) + _projected_settled_ink(context)
                # Satisfied individual/pair targets do not imply a populated
                # card. Retain a bounded extra source-ink opportunity when the
                # temporal card quality still reports sparse composition.
                local_target = max(target_ink, combined + 2 * _MIN_PAIR_INK_GAIN)
                deficit = max(0.0, local_target - combined)
                if deficit <= 0.004:
                    continue
                score = deficit * min(3.0, overlap) * (1.0 + 0.35 * underfilled_ratio)
                pairs.append((-score, str(primary.get('event_id') or ''), str(context.get('event_id') or ''), card, primary, context, local_target))
    pairs.sort(key=lambda row: row[:3])
    return [(card, primary, context, target_ink) for _, _, _, card, primary, context, target_ink in pairs[:32]]


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
    original_plan = copy.deepcopy(plan)
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    step = max(0.08, min(0.12, 3.0 / max(1.0, float(fps))))
    before = build_visual_density_report(plan)
    stats = {
        'authority': 'REFERENCE_SEMANTIC_CARD_COHORT_FIT_V3',
        'joint_pairs_requested': 0,
        'joint_candidates_evaluated': 0,
        'joint_pairs_committed': 0,
        'joint_event_ids': [],
        'joint_mutations': [],
        'joint_cohorts_committed': 0,
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
        secondary = _secondary_support(plan, card, primary, context)
        if secondary is not None and str(secondary.get('event_id')) in committed_ids:
            secondary = None
        cohort = [primary, context] + ([secondary] if secondary is not None else [])
        scales = _pair_scale_ladder(primary, context, events, target_ink)
        if not scales:
            stats['joint_rejections']['NO_SOURCE_INK_DEFICIT'] = stats['joint_rejections'].get('NO_SOURCE_INK_DEFICIT', 0) + 1
            continue

        pre_quality = _card_quality(plan, card, step)
        pre_density = build_visual_density_report(plan)
        old_pair_ink = sum(_projected_settled_ink(e) for e in cohort)
        snapshots = {str(e.get('event_id')): copy.deepcopy(e) for e in cohort}
        committed = False
        for primary_factor, context_factor in scales:
            factors = [primary_factor, context_factor]
            if secondary is not None:
                _, cap = _root_scale_target(secondary, events)
                factors.append(min(primary_factor, context_factor, cap))
            layouts = _cohort_layouts(plan, snapshots[primary_id], snapshots[context_id],
                                      snapshots[str(secondary.get('event_id'))] if secondary is not None else None, factors)
            if not layouts:
                stats['joint_rejections']['NO_SAFE_COHORT_LAYOUT'] = stats['joint_rejections'].get('NO_SAFE_COHORT_LAYOUT', 0) + 1
            for centers in layouts:
                stats['joint_candidates_evaluated'] += 1
                _restore_all(cohort, snapshots)
                for event, center, factor in zip(cohort, centers, factors):
                    _apply_static_transform(event, center, factor)
                # Preserve the established source-ink hierarchy, including a
                # support promoted to PRIMARY by the presentation budget.
                hierarchy_ok = all(
                    _projected_settled_ink(e) <= _projected_settled_ink(primary) + 1e-6
                    for e in cohort[1:]
                    if _projected_settled_ink(snapshots[str(e.get('event_id'))])
                    <= _projected_settled_ink(snapshots[primary_id]) + 1e-6)
                if not hierarchy_ok or not _candidate_safe(plan, cohort, fps):
                    stats['joint_rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['joint_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                    continue
                post_quality = _card_quality(plan, card, step)
                post_density = build_visual_density_report(plan)
                new_pair_ink = sum(_projected_settled_ink(e) for e in cohort)
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

                for event, factor in zip(cohort, factors):
                    partner = context if event is primary else primary
                    event['reference_joint_fit_authority'] = 'SOURCE_BACKED_PRIMARY_CONTEXT_COORDINATED_STATIC_FIT_FULL_LIFETIME_CERTIFIED'
                    event['reference_joint_fit_partner_event_id'] = str(partner.get('event_id') or '')
                    event['reference_joint_fit_scale_factor'] = round(float(factor), 6)
                    event['reference_joint_fit_target_ink'] = round(float(target_ink), 6)
                    event['reference_cohort_owner_event_id'] = primary_id
                    event['reference_cohort_event_ids'] = [str(e.get('event_id')) for e in cohort]
                    event['reference_cohort_card_id'] = str(card.get('card_id'))
                    _sync_constraint_layout(plan, event)
                stats['joint_pairs_committed'] += 1
                ids = [str(e.get('event_id')) for e in cohort]
                stats['joint_event_ids'].extend(ids)
                committed_ids.update(ids)
                stats['joint_cohorts_committed'] += int(secondary is not None)
                stats['joint_mutations'].append({
                    'card_id': card.get('card_id'), 'event_ids': ids,
                    'before_quality': pre_quality, 'after_quality': post_quality,
                    'actors': [{'event_id': eid,
                        'before': {k: snapshots[eid].get(k) for k in ('card_rest_position_norm', 'layout_scale_multiplier', 'composition_states', 'composition_participant_states')},
                        'after': {k: copy.deepcopy(e.get(k)) for k in ('card_rest_position_norm', 'layout_scale_multiplier', 'composition_states', 'composition_participant_states')}}
                        for eid, e in zip(ids, cohort)]})
                committed = True
                break
            if committed:
                break
        if not committed:
            _restore_all(cohort, snapshots)

    _retry_semantic_after_joint_fit(plan, fps, stats)
    after = build_visual_density_report(plan)
    stats['joint_event_ids'] = sorted(set(stats['joint_event_ids']))
    stats['joint_max_target_ink'] = round(float(stats['joint_max_target_ink']), 6)
    stats['after_underfilled_seconds'] = round(sum(float(_card_quality(plan, card, step).get('underfilled_seconds') or 0.0) for card in cards), 6)
    stats['changed'] = bool(stats['joint_pairs_committed'] or stats['post_joint_semantic_committed'])
    stats['pass'] = _density_not_worse(before, after) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        plan.clear()
        plan.update(original_plan)
        raise ValueError('REFERENCE_COORDINATED_PRIMARY_CONTEXT_FIT_FAILED')
    return stats
