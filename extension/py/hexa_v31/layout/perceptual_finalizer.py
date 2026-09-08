from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _in_safe, _rect
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel
from hexa_v31.visual_density import build_visual_density_report


_INK_MODEL = ProjectedVisibleInkModel()
_PARTITION_MODES = {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'}


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


def _affected_cards_for_events(events: list[dict], cards: list[dict]) -> list[dict]:
    ids = set()
    rows = []
    for event in events:
        for card in _affected_cards(event, cards):
            key = str(card.get('card_id') or '')
            if key in ids:
                continue
            ids.add(key)
            rows.append(card)
    return rows


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
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    for card in _affected_cards(event, cards):
        if card_motion_conflicts(
            _card_neighbors(events, card),
            float(card.get('start_seconds', 0.0)),
            float(card.get('end_seconds', 0.0)),
            fps,
        ):
            return False
    return bool(composition_plan_qa(plan).get('pass'))


def _candidate_group_safe(plan: dict, group: list[dict], fps: float) -> bool:
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    for card in _affected_cards_for_events(group, cards):
        if card_motion_conflicts(
            _card_neighbors(events, card),
            float(card.get('start_seconds', 0.0)),
            float(card.get('end_seconds', 0.0)),
            fps,
        ):
            return False
    return bool(composition_plan_qa(plan).get('pass'))


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
        # Reference videos sit materially above the old ~17% encoded occupancy.
        # These are requested source-ink targets only; safe-frame/collision QA is
        # still the hard authority and can reject every aggressive candidate.
        return (0.24 if simultaneous else 0.32, 2.15)
    return (0.12 if simultaneous else 0.16, 1.65)


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
        ladder = [candidate_max, 2.0, 1.85, 1.70, 1.55, 1.42, 1.32, 1.24, 1.16, 1.10, 1.06]
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


def _partition_group_key(event: dict) -> tuple:
    return (
        str(event.get('visual_card_id') or ''),
        str(event.get('scene_id') or ''),
        str(event.get('partition_group_id') or event.get('partition_root_id') or 'ROOT_COMPOSITE'),
    )


def _partition_groups(events: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for event in events:
        if event.get('suppressed_by_card_density'):
            continue
        if str(event.get('render_mode') or '') not in _PARTITION_MODES:
            continue
        grouped.setdefault(_partition_group_key(event), []).append(event)
    return [grouped[key] for key in sorted(grouped, key=str) if len(grouped[key]) >= 2]


def _group_center(group: list[dict]) -> tuple[float, float]:
    rects = [list(map(float, event.get('planned_rect_norm') or [])) for event in group]
    rects = [rect for rect in rects if len(rect) == 4]
    if not rects:
        centers = [event.get('card_rest_position_norm') or [0.5, 0.5] for event in group]
        return (
            sum(float(center[0]) for center in centers) / len(centers),
            sum(float(center[1]) for center in centers) / len(centers),
        )
    x0 = min(rect[0] for rect in rects)
    y0 = min(rect[1] for rect in rects)
    x1 = max(rect[0] + rect[2] for rect in rects)
    y1 = max(rect[1] + rect[3] for rect in rects)
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _group_has_translation_motion(group: list[dict]) -> bool:
    for event in group:
        if event.get('position_animated') or event.get('preset_actions') or event.get('composition_states') or event.get('composition_participant_states'):
            return True
        entry_name = str((event.get('preset_entry') or {}).get('name') or '')
        exit_name = str((event.get('preset_exit') or {}).get('name') or '')
        if entry_name.startswith('ENTRY_') or exit_name.startswith('EXIT_'):
            return True
    return False


def _scale_source_backed_partition_groups(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    density = build_visual_density_report(plan)
    for group in _partition_groups(events):
        stats['partition_groups_requested'] += 1
        if _group_has_translation_motion(group):
            stats['partition_group_rejections']['TRANSLATION_OR_STATE_MOTION'] = stats['partition_group_rejections'].get('TRANSLATION_OR_STATE_MOTION', 0) + 1
            continue
        current_ink = sum(_projected_settled_ink(event) for event in group)
        if current_ink <= 1e-8:
            continue
        group_ids = {str(event.get('event_id') or '') for event in group}
        simultaneous = any(
            str(other.get('event_id') or '') not in group_ids
            and not other.get('suppressed_by_card_density')
            and any(_overlap_seconds(member, other) >= 0.25 for member in group)
            for other in events
        )
        target = 0.22 if simultaneous else 0.30
        desired = math.sqrt(target / current_ink) if current_ink < target else 1.0
        candidate_max = min(2.10, desired)
        if candidate_max <= 1.025:
            continue
        ladder = [candidate_max, 2.0, 1.85, 1.70, 1.55, 1.42, 1.32, 1.24, 1.16, 1.10]
        factors = []
        for factor in ladder:
            factor = round(float(factor), 6)
            if factor <= 1.025 or factor > candidate_max + 1e-6 or factor in factors:
                continue
            factors.append(factor)
        snapshot = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in group}
        old_density = density
        center = _group_center(group)
        committed = False
        for factor in factors:
            stats['partition_group_candidates_evaluated'] += 1
            safe = True
            for event in group:
                old = snapshot[str(event.get('event_id') or '')]
                old_center = old.get('card_rest_position_norm') or [0.5, 0.5]
                new_center = [
                    center[0] + (float(old_center[0]) - center[0]) * factor,
                    center[1] + (float(old_center[1]) - center[1]) * factor,
                ]
                new_scale = float(old.get('layout_scale_multiplier') or 1.0) * factor
                rect = list(_rect((new_center[0], new_center[1]), _fp(event), new_scale * MOTION_ENVELOPE_SCALE))
                if not _in_safe(rect):
                    safe = False
                    break
                event['card_rest_position_norm'] = [round(new_center[0], 6), round(new_center[1], 6)]
                event['layout_scale_multiplier'] = round(new_scale, 6)
                event['planned_rect_norm'] = [round(value, 6) for value in rect]
                event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
            if not safe:
                for event in group:
                    event.clear(); event.update(copy.deepcopy(snapshot[str(event.get('event_id') or '')]))
                stats['partition_group_rejections']['SAFE_FRAME'] = stats['partition_group_rejections'].get('SAFE_FRAME', 0) + 1
                continue
            if not _candidate_group_safe(plan, group, fps):
                for event in group:
                    event.clear(); event.update(copy.deepcopy(snapshot[str(event.get('event_id') or '')]))
                stats['partition_group_rejections']['COLLISION_OR_PATH'] = stats['partition_group_rejections'].get('COLLISION_OR_PATH', 0) + 1
                continue
            candidate_density = build_visual_density_report(plan)
            if not _density_not_worse(old_density, candidate_density):
                for event in group:
                    event.clear(); event.update(copy.deepcopy(snapshot[str(event.get('event_id') or '')]))
                stats['partition_group_rejections']['DENSITY_MONOTONICITY'] = stats['partition_group_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                continue
            new_ink = sum(_projected_settled_ink(event) for event in group)
            if new_ink <= current_ink + 0.010:
                for event in group:
                    event.clear(); event.update(copy.deepcopy(snapshot[str(event.get('event_id') or '')]))
                stats['partition_group_rejections']['NO_MATERIAL_INK_GAIN'] = stats['partition_group_rejections'].get('NO_MATERIAL_INK_GAIN', 0) + 1
                continue
            for event in group:
                event['final_partition_group_scale_authority'] = 'SOURCE_BACKED_PARTITION_GROUP_UNIFORM_TRANSFORM_FULL_LIFETIME_CERTIFIED'
                event['final_partition_group_scale_factor'] = factor
                event['final_partition_group_ink_before'] = round(current_ink, 6)
                event['final_partition_group_ink_after'] = round(new_ink, 6)
                _sync_constraint_layout(plan, event)
            density = candidate_density
            stats['partition_groups_committed'] += 1
            stats['partition_group_event_ids'].extend(sorted(group_ids))
            committed = True
            break
        if not committed:
            for event in group:
                event.clear(); event.update(copy.deepcopy(snapshot[str(event.get('event_id') or '')]))


def _restore_events(events: list[dict], snapshots: dict[str, dict]) -> None:
    for event in events:
        event_id = str(event.get('event_id') or '')
        snapshot = snapshots.get(event_id)
        if snapshot is None:
            continue
        event.clear()
        event.update(copy.deepcopy(snapshot))


def _synthesize_semantic_focus_cascade(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    cards = plan.get('visual_cards') or {'cards': []}
    snapshots = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in events}
    before = build_visual_density_report(plan)
    from hexa_v31.planning.preset_story_planner import _adaptive_composition_state_optimize

    result = _adaptive_composition_state_optimize(events, cards, fps)
    stats['semantic_cascade'] = result
    if not result.get('candidates_committed'):
        return
    after = build_visual_density_report(plan)
    if not _density_not_worse(before, after) or not bool(composition_plan_qa(plan).get('pass')):
        _restore_events(events, snapshots)
        stats['semantic_cascade_rejected'] = True
        stats['semantic_cascade_rejection_reason'] = 'FULL_PLAN_QA_OR_DENSITY_MONOTONICITY'
        stats['semantic_cascade']['candidates_committed'] = 0
        stats['semantic_cascade']['event_ids'] = []
        return
    stats['semantic_cascade_committed'] = int(result.get('candidates_committed') or 0)


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
        candidates = [value for value in (1.34, 1.30, 1.26, 1.22, 1.18, 1.14) if value > current + 0.015]
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


def _amplify_participant_hierarchy(plan: dict, fps: float, stats: dict) -> None:
    density = build_visual_density_report(plan)
    for event in sorted(plan.get('events') or [], key=lambda row: str(row.get('event_id') or '')):
        if event.get('suppressed_by_card_density') or str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
            continue
        states = event.get('composition_participant_states') or []
        if not states:
            continue
        for index, state in enumerate(states):
            beat = str(state.get('semantic_beat') or '').upper()
            current = float(state.get('scale_multiplier') or 1.0)
            if 'YIELDS_FOR_FOCAL_ESTABLISHMENT' in beat:
                candidates = [value for value in (0.78, 0.82) if value < current - 0.015]
            elif 'ASSUMES_RELATIONSHIP_HIERARCHY' in beat:
                candidates = [value for value in (1.22, 1.18, 1.14) if value > current + 0.015]
            else:
                continue
            snapshot = copy.deepcopy(event)
            old_density = density
            stats['participant_hierarchy_candidates_requested'] += 1
            for scale in candidates:
                stats['participant_hierarchy_candidates_evaluated'] += 1
                event['composition_participant_states'][index]['scale_multiplier'] = scale
                if not _candidate_safe(plan, event, fps):
                    event.clear(); event.update(copy.deepcopy(snapshot))
                    stats['participant_hierarchy_rejections']['COLLISION_OR_PATH'] = stats['participant_hierarchy_rejections'].get('COLLISION_OR_PATH', 0) + 1
                    continue
                candidate_density = build_visual_density_report(plan)
                if not _density_not_worse(old_density, candidate_density):
                    event.clear(); event.update(copy.deepcopy(snapshot))
                    stats['participant_hierarchy_rejections']['DENSITY_MONOTONICITY'] = stats['participant_hierarchy_rejections'].get('DENSITY_MONOTONICITY', 0) + 1
                    continue
                event['final_participant_hierarchy_authority'] = 'SEMANTIC_FOCUS_TRANSFER_FULL_LIFETIME_CERTIFIED'
                density = candidate_density
                stats['participant_hierarchy_event_ids'].append(str(event.get('event_id') or ''))
                stats['participant_hierarchy_candidates_committed'] += 1
                break


def finalize_perceptual_composition(plan: dict, fps: float = 30.0) -> dict:
    """Drive source-backed density and semantic hierarchy toward reference quality.

    The pass never invents source pixels or preset names. ROOT_ATOMIC actors may
    scale only through full safe-frame/lifetime certification. Certified source
    partitions may scale only as a uniform group transform that preserves every
    member and relative geometry. Semantic recomposition is synthesized only at
    existing source-backed reveal/handoff anchors, then the same full-plan QA
    authority validates the resulting states.
    """
    before = build_visual_density_report(plan)
    stats = {
        'authority': 'FINAL_SOURCE_BACKED_PERCEPTUAL_COMPOSITION_V2_REFERENCE_FLOOR',
        'scale_candidates_requested': 0,
        'scale_candidates_evaluated': 0,
        'scale_candidates_committed': 0,
        'scaled_event_ids': [],
        'scale_rejections': {},
        'partition_groups_requested': 0,
        'partition_group_candidates_evaluated': 0,
        'partition_groups_committed': 0,
        'partition_group_event_ids': [],
        'partition_group_rejections': {},
        'semantic_cascade': {},
        'semantic_cascade_committed': 0,
        'semantic_cascade_rejected': False,
        'hierarchy_candidates_requested': 0,
        'hierarchy_candidates_evaluated': 0,
        'hierarchy_candidates_committed': 0,
        'hierarchy_event_ids': [],
        'hierarchy_rejections': {},
        'participant_hierarchy_candidates_requested': 0,
        'participant_hierarchy_candidates_evaluated': 0,
        'participant_hierarchy_candidates_committed': 0,
        'participant_hierarchy_event_ids': [],
        'participant_hierarchy_rejections': {},
        'before_median_safe_frame_union_coverage': before.get('median_safe_frame_union_coverage'),
        'before_median_estimated_alpha_coverage': before.get('median_estimated_alpha_coverage'),
        'before_mean_temporal_population': before.get('mean_temporal_population'),
        'before_near_blank_duration_seconds': before.get('near_blank_duration_seconds'),
    }
    _synthesize_semantic_focus_cascade(plan, fps, stats)
    _scale_source_backed_partition_groups(plan, fps, stats)
    _scale_source_backed_actors(plan, fps, stats)
    _amplify_existing_hierarchy(plan, fps, stats)
    _amplify_participant_hierarchy(plan, fps, stats)
    after = build_visual_density_report(plan)
    stats['partition_group_event_ids'] = sorted(set(stats['partition_group_event_ids']))
    stats['participant_hierarchy_event_ids'] = sorted(set(stats['participant_hierarchy_event_ids']))
    stats['after_median_safe_frame_union_coverage'] = after.get('median_safe_frame_union_coverage')
    stats['after_median_estimated_alpha_coverage'] = after.get('median_estimated_alpha_coverage')
    stats['after_mean_temporal_population'] = after.get('mean_temporal_population')
    stats['after_near_blank_duration_seconds'] = after.get('near_blank_duration_seconds')
    stats['changed'] = bool(
        stats['scale_candidates_committed']
        or stats['partition_groups_committed']
        or stats['semantic_cascade_committed']
        or stats['hierarchy_candidates_committed']
        or stats['participant_hierarchy_candidates_committed']
    )
    stats['pass'] = _density_not_worse(before, after) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        raise ValueError('FINAL_SOURCE_BACKED_PERCEPTUAL_COMPOSITION_FAILED')
    return stats
