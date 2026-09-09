from __future__ import annotations

import copy
import math

from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa
from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, SAFE_X, SAFE_Y, _fp, _in_safe, _rect
from hexa_v31.visual_density import build_visual_density_report
from hexa_v31.layout.position_authority import has_actual_center_travel


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


def _affected_cards(group: list[dict], cards: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for event in group:
        est, een = _physical_interval(event)
        for card in cards:
            cs = float(card.get('start_seconds', 0.0))
            ce = float(card.get('end_seconds', cs))
            if est >= ce - 1e-6 or een <= cs + 1e-6:
                continue
            key = str(card.get('card_id') or '')
            if key in seen:
                continue
            seen.add(key)
            out.append(card)
    return out


def _card_neighbors(events: list[dict], card: dict) -> list[dict]:
    cs = float(card.get('start_seconds', 0.0))
    ce = float(card.get('end_seconds', cs))
    return [
        event for event in events
        if not event.get('suppressed_by_card_density')
        and _physical_interval(event)[0] < ce - 1e-6
        and _physical_interval(event)[1] > cs + 1e-6
    ]


def _candidate_safe(plan: dict, group: list[dict], fps: float) -> bool:
    events = plan.get('events') or []
    cards = (plan.get('visual_cards') or {}).get('cards') or []
    for card in _affected_cards(group, cards):
        if card_motion_conflicts(
            _card_neighbors(events, card),
            float(card.get('start_seconds', 0.0)),
            float(card.get('end_seconds', 0.0)),
            fps,
        ):
            return False
    # Card and actor clocks need not share the same sampling origin. Certify
    # the changed actor's physical interval too, including cross-card neighbors.
    # Otherwise a short hierarchy/exit overlap can fall between card samples.
    for event in group:
        start, end = _physical_interval(event)
        neighbors = [other for other in events
                     if not other.get('suppressed_by_card_density')
                     and _physical_interval(other)[0] < end
                     and _physical_interval(other)[1] > start]
        if card_motion_conflicts(neighbors, start, end, fps):
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
    fp = _fp(event)
    scale = max(0.0, float(event.get('layout_scale_multiplier') or 1.0))
    return max(0.0, float(fp.visible_area) * scale * scale)


def _restore_group(group: list[dict], snapshots: dict[str, dict]) -> None:
    for event in group:
        event_id = str(event.get('event_id') or '')
        # The id is captured before clear so rollback cannot lose its lookup key.
        snapshot = snapshots[event_id]
        event.clear()
        event.update(copy.deepcopy(snapshot))


def _restore_all(events: list[dict], snapshots: dict[str, dict]) -> None:
    for event in events:
        event_id = str(event.get('event_id') or '')
        snapshot = snapshots.get(event_id)
        if snapshot is None:
            continue
        event.clear()
        event.update(copy.deepcopy(snapshot))


def _group_has_position_authority(group: list[dict]) -> bool:
    return any(has_actual_center_travel(event) for event in group)


def _partition_key(event: dict) -> tuple[str, str, str]:
    return (
        str(event.get('visual_card_id') or ''),
        str(event.get('scene_id') or ''),
        str(event.get('partition_group_id') or event.get('partition_root_id') or 'ROOT_COMPOSITE'),
    )


def _partition_groups(events: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for event in events:
        if str(event.get('render_mode') or '') not in _PARTITION_MODES:
            continue
        grouped.setdefault(_partition_key(event), []).append(event)
    return [grouped[key] for key in sorted(grouped) if len(grouped[key]) >= 2
            and not any(e.get('suppressed_by_card_density') for e in grouped[key])]


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


def _scale_partition_groups(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    density = build_visual_density_report(plan)
    for group in _partition_groups(events):
        stats['partition_groups_requested'] += 1
        if _group_has_position_authority(group):
            stats['partition_rejections']['POSITION_OR_STATE_AUTHORITY'] = stats['partition_rejections'].get('POSITION_OR_STATE_AUTHORITY', 0) + 1
            continue
        current_ink = sum(_projected_settled_ink(event) for event in group)
        if current_ink <= 1e-8:
            continue
        ids = {str(event.get('event_id') or '') for event in group}
        simultaneous = any(
            str(other.get('event_id') or '') not in ids
            and not other.get('suppressed_by_card_density')
            and any(_overlap_seconds(member, other) >= 0.25 for member in group)
            for other in events
        )
        target = 0.22 if simultaneous else 0.30
        desired = math.sqrt(target / current_ink) if current_ink < target else 1.0
        candidate_max = min(2.10, desired)
        if candidate_max <= 1.025:
            continue
        factors = []
        for factor in (candidate_max, 2.0, 1.85, 1.70, 1.55, 1.42, 1.32, 1.24, 1.16, 1.10):
            factor = round(float(factor), 6)
            if factor <= 1.025 or factor > candidate_max + 1e-6 or factor in factors:
                continue
            factors.append(factor)
        snapshots = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in group}
        center = _group_center(group)
        old_density = density
        for factor in factors:
            stats['partition_candidates_evaluated'] += 1
            safe = True
            for event in group:
                event_id = str(event.get('event_id') or '')
                original = snapshots[event_id]
                original_center = original.get('card_rest_position_norm') or [0.5, 0.5]
                new_center = [
                    center[0] + (float(original_center[0]) - center[0]) * factor,
                    center[1] + (float(original_center[1]) - center[1]) * factor,
                ]
                new_scale = float(original.get('layout_scale_multiplier') or 1.0) * factor
                rect = list(_rect((new_center[0], new_center[1]), _fp(event), new_scale * MOTION_ENVELOPE_SCALE))
                event['card_rest_position_norm'] = [round(new_center[0], 6), round(new_center[1], 6)]
                event['layout_scale_multiplier'] = round(new_scale, 6)
                event['planned_rect_norm'] = [round(value, 6) for value in rect]
                event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
            # Fit the complete partition with one common static translation,
            # never by relocating or shrinking individual members.
            rects = [e['planned_rect_norm'] for e in group]
            x0 = min(r[0] for r in rects)
            y0 = min(r[1] for r in rects)
            x1 = max(r[0] + r[2] for r in rects)
            y1 = max(r[1] + r[3] for r in rects)
            safe = x1 - x0 <= SAFE_X[1] - SAFE_X[0] and y1 - y0 <= SAFE_Y[1] - SAFE_Y[0]
            dx = max(SAFE_X[0] - x0, min(0., SAFE_X[1] - x1))
            dy = max(SAFE_Y[0] - y0, min(0., SAFE_Y[1] - y1))
            if safe:
                for event in group:
                    event['card_rest_position_norm'] = [event['card_rest_position_norm'][0] + dx,
                                                        event['card_rest_position_norm'][1] + dy]
                    event['planned_rect_norm'][0] += dx
                    event['planned_rect_norm'][1] += dy
                    event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
                    for key in ('composition_states', 'composition_participant_states'):
                        for state in event.get(key) or []:
                            state['center_norm'] = list(event['card_rest_position_norm'])
            if not safe:
                _restore_group(group, snapshots)
                stats['partition_rejections']['SAFE_FRAME'] = stats['partition_rejections'].get('SAFE_FRAME', 0) + 1
                continue
            if not _candidate_safe(plan, group, fps):
                _restore_group(group, snapshots)
                stats['partition_rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['partition_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                continue
            candidate_density = build_visual_density_report(plan)
            new_ink = sum(_projected_settled_ink(event) for event in group)
            if not _density_not_worse(old_density, candidate_density) or new_ink <= current_ink + 0.010:
                _restore_group(group, snapshots)
                reason = 'DENSITY_MONOTONICITY' if not _density_not_worse(old_density, candidate_density) else 'NO_MATERIAL_INK_GAIN'
                stats['partition_rejections'][reason] = stats['partition_rejections'].get(reason, 0) + 1
                continue
            for event in group:
                event['reference_partition_scale_authority'] = 'SOURCE_BACKED_PARTITION_UNIFORM_TRANSFORM_FULL_LIFETIME_CERTIFIED'
                event['reference_partition_scale_factor'] = factor
                event['reference_partition_ink_before'] = round(current_ink, 6)
                event['reference_partition_ink_after'] = round(new_ink, 6)
                _sync_constraint_layout(plan, event)
            stats['partition_groups_committed'] += 1
            stats['partition_event_ids'].extend(sorted(ids))
            density = candidate_density
            break


def _root_scale_target(event: dict, events: list[dict]) -> tuple[float, float]:
    primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
    simultaneous = any(
        other is not event
        and not other.get('suppressed_by_card_density')
        and _overlap_seconds(event, other) >= 0.25
        for other in events
    )
    if primary:
        return (0.23 if simultaneous else 0.30, 2.10)
    return (0.11 if simultaneous else 0.15, 1.60)


def _root_fit_destinations(plan: dict, event: dict, scale: float) -> list[list[float]]:
    """Bounded semantic slots for static fitting; never a motion trajectory."""
    from hexa_v31.composition_solver import _slots

    base = list(event.get('card_rest_position_norm') or [.5, .5])
    if _group_has_position_authority([event]):
        return [base]
    fp = _fp(event)
    width, height = fp.w * scale * MOTION_ENVELOPE_SCALE, fp.h * scale * MOTION_ENVELOPE_SCALE
    if width > SAFE_X[1] - SAFE_X[0] or height > SAFE_Y[1] - SAFE_Y[0]:
        return []
    card = next((c for c in (plan.get('visual_cards') or {}).get('cards') or []
                 if str(c.get('card_id')) == str(event.get('visual_card_id'))), {})
    archetype = str((card.get('universal_scene_grammar') or {}).get('archetype') or 'GENERIC')
    role = str(event.get('composition_role') or 'SUPPORT')
    destinations = []
    for cx, cy in [base, *_slots(archetype, role)]:
        fitted = [min(SAFE_X[1] - width / 2, max(SAFE_X[0] + width / 2, float(cx))),
                  min(SAFE_Y[1] - height / 2, max(SAFE_Y[0] + height / 2, float(cy)))]
        if not any(math.dist(fitted, existing) < 1e-6 for existing in destinations):
            destinations.append(fitted)
    return destinations[:6]


def _scale_root_actors(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    density = build_visual_density_report(plan)
    candidates = sorted(
        [
            event for event in events
            if not event.get('suppressed_by_card_density')
            and str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
            and event.get('visible_ink_fraction') is not None
            and event.get('planned_rect_norm')
        ],
        key=lambda event: (
            0 if str(event.get('attention_priority') or '').upper() == 'PRIMARY' else 1,
            _projected_settled_ink(event),
            str(event.get('event_id') or ''),
        ),
    )
    for event in candidates:
        target, cap = _root_scale_target(event, events)
        current_ink = _projected_settled_ink(event)
        if current_ink <= 1e-8 or current_ink >= target - 1e-6:
            continue
        desired = min(cap, math.sqrt(target / current_ink))
        if desired <= 1.025:
            continue
        factors = []
        for factor in (desired, 2.0, 1.85, 1.70, 1.55, 1.42, 1.32, 1.24, 1.16, 1.10, 1.06):
            factor = round(float(factor), 6)
            if factor <= 1.025 or factor > desired + 1e-6 or factor in factors:
                continue
            factors.append(factor)
        event_id = str(event.get('event_id') or '')
        snapshot = copy.deepcopy(event)
        old_density = density
        old_scale = float(event.get('layout_scale_multiplier') or 1.0)
        center = event.get('card_rest_position_norm') or [0.5, 0.5]
        static_destination = not _group_has_position_authority([snapshot])
        # Keep factor ranking dominant: try the available semantic negative
        # space before giving up on a meaningful source-backed subject size.
        candidates = [(factor, destination) for factor in factors
                      for destination in _root_fit_destinations(plan, snapshot, old_scale * factor)]
        for factor, candidate_center in candidates:
            stats['root_candidates_evaluated'] += 1
            new_scale = old_scale * factor
            rect = list(_rect(candidate_center, _fp(event), new_scale * MOTION_ENVELOPE_SCALE))
            if not _in_safe(rect):
                stats['root_rejections']['SAFE_FRAME'] = stats['root_rejections'].get('SAFE_FRAME', 0) + 1
                continue
            event['card_rest_position_norm'] = candidate_center
            for key in ('composition_states', 'composition_participant_states'):
                for state in event.get(key) or []:
                    if static_destination:
                        state['center_norm'] = list(candidate_center)
            event['layout_scale_multiplier'] = round(new_scale, 6)
            event['planned_rect_norm'] = [round(value, 6) for value in rect]
            event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
            if not _candidate_safe(plan, [event], fps):
                event.clear(); event.update(copy.deepcopy(snapshot))
                stats['root_rejections']['COLLISION_OR_COMPOSITION_QA'] = stats['root_rejections'].get('COLLISION_OR_COMPOSITION_QA', 0) + 1
                continue
            candidate_density = build_visual_density_report(plan)
            new_ink = _projected_settled_ink(event)
            if not _density_not_worse(old_density, candidate_density) or new_ink <= current_ink + 0.005:
                event.clear(); event.update(copy.deepcopy(snapshot))
                reason = 'DENSITY_MONOTONICITY' if not _density_not_worse(old_density, candidate_density) else 'NO_MATERIAL_INK_GAIN'
                stats['root_rejections'][reason] = stats['root_rejections'].get(reason, 0) + 1
                continue
            event['reference_root_scale_authority'] = 'SOURCE_BACKED_REFERENCE_DENSITY_FULL_LIFETIME_CERTIFIED'
            event['reference_root_scale_factor'] = factor
            event['reference_root_ink_before'] = round(current_ink, 6)
            event['reference_root_ink_after'] = round(new_ink, 6)
            _sync_constraint_layout(plan, event)
            stats['root_actors_committed'] += 1
            stats['root_event_ids'].append(event_id)
            density = candidate_density
            break


def _semantic_focus_cascade(plan: dict, fps: float, stats: dict) -> None:
    events = plan.get('events') or []
    cards = plan.get('visual_cards') or {'cards': []}
    snapshots = {str(event.get('event_id') or ''): copy.deepcopy(event) for event in events}
    before = build_visual_density_report(plan)

    from hexa_v31.planning.preset_story_planner import _adaptive_composition_state_optimize

    result = _adaptive_composition_state_optimize(events, cards, fps)
    stats['semantic_cascade_candidates_evaluated'] = int(result.get('candidates_evaluated') or 0)
    stats['semantic_cascade_committed'] = int(result.get('candidates_committed') or 0)
    stats['semantic_cascade_event_ids'] = list(result.get('event_ids') or [])
    stats['semantic_cascade_rejections'] = dict(result.get('rejections') or {})
    _continue_semantic_sequences(plan, fps, stats)
    if not stats['semantic_cascade_committed']:
        return
    after = build_visual_density_report(plan)
    if not _density_not_worse(before, after) or not bool(composition_plan_qa(plan).get('pass')):
        _restore_all(events, snapshots)
        stats['semantic_cascade_rejections']['FULL_PLAN_QA_OR_DENSITY_MONOTONICITY'] = stats['semantic_cascade_committed']
        stats['semantic_cascade_committed'] = 0
        stats['semantic_cascade_event_ids'] = []
        return
    for event in events:
        if str(event.get('event_id') or '') in stats['semantic_cascade_event_ids']:
            event['reference_semantic_cascade_authority'] = 'SOURCE_REVEAL_FOCUS_TRANSFER_FULL_LIFETIME_CERTIFIED'


def _hierarchy_scale_candidates(owner: dict, target: dict, events: list[dict],
                                center: list[float], current: float) -> list[float]:
    """Source-ink deficit and role-weighted safe headroom set beat amplitude."""
    footprint = _fp(owner)
    layout_scale = max(1e-9, float(owner.get('layout_scale_multiplier') or 1.0))
    half_width = footprint.w * layout_scale / 2.0
    half_height = footprint.h * layout_scale / 2.0
    safe_scale = min((center[0] - SAFE_X[0]) / max(half_width, 1e-9),
                     (SAFE_X[1] - center[0]) / max(half_width, 1e-9),
                     (center[1] - SAFE_Y[0]) / max(half_height, 1e-9),
                     (SAFE_Y[1] - center[1]) / max(half_height, 1e-9))
    target_ink, _ = _root_scale_target(owner, events)
    ink = _projected_settled_ink(owner)
    if ink <= 1e-9 or ink * current * current >= target_ink:
        return []
    primary = str(owner.get('attention_priority') or '').upper() == 'PRIMARY'
    importance = 1.0 if primary else .65
    relationship = str(target.get('composition_role') or '').upper()
    if relationship in {'RESULT', 'TARGET', 'BLOCKER'}:
        importance = min(1.0, importance + .15)
    ink_destination = math.sqrt(target_ink / ink)
    desired = min(safe_scale, ink_destination, current * (1.0 + .45 * importance))
    delta = desired - current
    return [round(current + delta * fraction, 6) for fraction in (1., .8, .6, .4)
            if delta * fraction >= .12]


def _author_reveal_participant(owner: dict, target: dict, state: dict) -> bool:
    """Give the new source a bounded focus establishment, owned by this beat.

    An ordinary preset reveal cannot certify an unrelated hierarchy change on
    a tiny owner. The participant starts at a subordinate source-backed scale
    and establishes its existing solved destination, without new travel.
    """
    if (str(target.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC'
            or has_actual_center_travel(target)
            or target.get('composition_states') or target.get('composition_participant_states')):
        return False
    entry = target.get('preset_entry') or {}
    reveal_start = float(entry.get('start_seconds', target.get('motion_start_seconds', target.get('start_seconds', 0.))))
    initial_start = max(reveal_start, _physical_interval(target)[0])
    start = max(float(state['start_seconds']), initial_start)
    end = float(state['start_seconds']) + float(state['transition_duration_seconds'])
    if end - start < .24 or end + .12 > _physical_interval(target)[1]:
        return False
    # Require material source-ink participation; tiny sources must not create
    # metadata-only recompositions. This is geometry, never planner rendering.
    ink = _projected_settled_ink(target)
    if ink * (1.0 - .88**2) < .012:
        return False
    sid = str(state['state_id'])
    base = dict(owner_state_id=sid, card_id=state['card_id'],
                scene_id=target.get('scene_id'), center_norm=list(target.get('card_rest_position_norm') or [.5,.5]),
                visibility=1.0, translation_safe=False,
                participating_event_ids=list(state['participating_event_ids']))
    target['composition_participant_states'] = [
        dict(base, state_id=sid+'::PARTICIPANT_A', start_seconds=round(initial_start,6),
             transition_duration_seconds=0., scale_multiplier=.88,
             semantic_beat='SOURCE_REVEAL_SUBORDINATE_HIERARCHY'),
        dict(base, state_id=sid+'::PARTICIPANT_B', previous_state_id=sid+'::PARTICIPANT_A',
             start_seconds=round(start,6), transition_duration_seconds=round(end-start,6),
             scale_multiplier=1., semantic_beat='SOURCE_REVEAL_FOCUS_ESTABLISHMENT'),
    ]
    return True


def _continue_semantic_sequences(plan: dict, fps: float, stats: dict) -> None:
    """Use later authored reveals, not elapsed time, to continue a focal state.

    The pair compiler establishes the first relationship. A long-lived focal
    actor can then establish a larger relationship hierarchy on a later reveal.
    The target must already have a renderable reveal/handoff at this trigger;
    this avoids competing participant tracks and invented idle movement.
    """
    from hexa_v31.composition_solver import composition_state_at
    from hexa_v31.composition_qa import _state

    events = plan.get('events') or []
    for card in (plan.get('visual_cards') or {}).get('cards') or []:
        card_id = str(card.get('card_id') or '')
        local = sorted([e for e in events if str(e.get('visual_card_id') or '') == card_id
                        and not e.get('suppressed_by_card_density')],
                       key=lambda e: (float(e.get('perceptual_hit_seconds', 0.)), str(e.get('event_id'))))
        for owner in local:
            states = owner.get('composition_states') or []
            if len(states) < 2 or has_actual_center_travel(owner):
                continue
            # Partition hierarchy is owned by the complete group, not a lone
            # child. Existing authored states are preserved, never multiplied.
            if str(owner.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
                continue
            last_end = max(float(s.get('start_seconds', 0.)) + float(s.get('transition_duration_seconds') or 0.) for s in states)
            used = {str(eid) for state in states for eid in state.get('participating_event_ids') or []}
            for target in local:
                if str(target.get('event_id')) in used:
                    continue
                hit = float(target.get('perceptual_hit_seconds', target.get('start_seconds', 0.)))
                start, duration = hit - .64, .64
                if start < last_end + .40 or hit + .20 > min(_physical_interval(owner)[1], _physical_interval(target)[1]):
                    continue
                # A visible new source must actually establish itself during
                # this beat. An old held actor is not a fresh semantic trigger.
                reveal_tracks = (target.get('composition_participant_states') or []) + (target.get('composition_states') or [])
                entry = target.get('preset_entry') or {}
                revealing = any(start - .12 <= float(s.get('start_seconds', 0.)) <= hit
                                and float(s.get('transition_duration_seconds') or 0.) > .10 for s in reveal_tracks)
                revealing = revealing or (bool(entry) and float(entry.get('start_seconds', 0.)) <= hit
                                           and float(entry.get('start_seconds', 0.)) + float(entry.get('duration_seconds') or 0.) >= start)
                if not revealing:
                    continue
                if any((sample := _state(owner, t)) is None or sample[2] <= .22
                       for t in (start, hit, hit + .12)):
                    continue
                center, scale, visibility = composition_state_at(owner, start)
                # One additional relationship establishment, bounded by a real
                # later reveal. Never oscillate or add repeating scale pulses.
                destinations = _hierarchy_scale_candidates(owner, target, events, center, scale)
                if not destinations:
                    # A focal actor at its safe size can still hand focus to
                    # a later source. The participant must supply the entire
                    # material change; a no-op owner alone never commits.
                    destinations = [scale]
                snapshot = copy.deepcopy(owner)
                target_snapshot = copy.deepcopy(target)
                density_before = build_visual_density_report(plan)
                state_id = card_id + '::' + str(owner.get('event_id')) + '::REVEAL::' + str(target.get('event_id'))
                candidate_state = {
                    'state_id': state_id, 'scene_id': owner.get('scene_id'), 'card_id': card_id,
                    'semantic_beat': 'LATER_SOURCE_RELATIONSHIP_ESTABLISHMENT',
                    'start_seconds': round(start, 6), 'transition_duration_seconds': duration,
                    'participating_event_ids': [str(owner.get('event_id')), str(target.get('event_id'))],
                    'center_norm': center, 'visibility': visibility,
                    'translation_safe': bool(owner.get('translation_safe_after_occlusion', owner.get('animation_safe', False))),
                    'role': owner.get('composition_role'),
                    'state_reason': 'EXISTING_FOCAL_CONTEXT_FOR_LATER_SOURCE_REVEAL',
                    'previous_state_id': owner['composition_states'][-1].get('state_id'),
                }
                committed = False
                for destination_scale in destinations:
                    stats['semantic_cascade_candidates_evaluated'] += 1
                    owner['composition_states'].append(dict(candidate_state, scale_multiplier=destination_scale))
                    owner_ink_gain = _projected_settled_ink(owner) * (destination_scale**2 - scale**2)
                    participant_authored = False
                    if owner_ink_gain < .012:
                        participant_authored = _author_reveal_participant(owner, target, candidate_state)
                    effective_delta = abs(composition_state_at(owner, hit)[1] - scale)
                    if ((effective_delta >= .12 and owner_ink_gain >= .012) or participant_authored) and _candidate_safe(plan, [owner, target], fps):
                        density_after = build_visual_density_report(plan)
                        if _density_not_worse(density_before, density_after):
                            committed = True
                            break
                    owner.clear(); owner.update(copy.deepcopy(snapshot))
                    target.clear(); target.update(copy.deepcopy(target_snapshot))
                    reasons = stats['semantic_cascade_rejections']
                    reasons['LATER_REVEAL_GEOMETRY_OR_DENSITY'] = reasons.get('LATER_REVEAL_GEOMETRY_OR_DENSITY', 0) + 1
                if committed:
                    stats['semantic_cascade_committed'] += 1
                    stats['semantic_cascade_event_ids'].append(str(owner.get('event_id')))
                    break  # bounded to one additional, non-repeating relationship


def finalize_reference_geometry(plan: dict, fps: float = 30.0) -> dict:
    """Certified reference-density geometry plus semantic focus-transfer cascade.

    This stage is deliberately separate from the stable perceptual finalizer.
    It may enlarge ROOT_ATOMIC actors from source-backed ink evidence, enlarge a
    certified partition only as one uniform group transform, and synthesize
    focus-transfer states only at existing source-backed reveal anchors. It does
    not invent source pixels, change semantic hit times, split partition actors,
    or authorize arbitrary camera drift.
    """
    before = build_visual_density_report(plan)
    stats = {
        'authority': 'REFERENCE_GEOMETRY_AND_SEMANTIC_FOCUS_V1',
        'partition_groups_requested': 0,
        'partition_candidates_evaluated': 0,
        'partition_groups_committed': 0,
        'partition_event_ids': [],
        'partition_rejections': {},
        'root_candidates_evaluated': 0,
        'root_actors_committed': 0,
        'root_event_ids': [],
        'root_rejections': {},
        'semantic_cascade_candidates_evaluated': 0,
        'semantic_cascade_committed': 0,
        'semantic_cascade_event_ids': [],
        'semantic_cascade_rejections': {},
        'before_median_alpha_coverage': before.get('median_estimated_alpha_coverage'),
        'before_median_safe_frame_union_coverage': before.get('median_safe_frame_union_coverage'),
        'before_mean_temporal_population': before.get('mean_temporal_population'),
    }

    _semantic_focus_cascade(plan, fps, stats)
    _scale_partition_groups(plan, fps, stats)
    _scale_root_actors(plan, fps, stats)

    after = build_visual_density_report(plan)
    stats['partition_event_ids'] = sorted(set(stats['partition_event_ids']))
    stats['root_event_ids'] = sorted(set(stats['root_event_ids']))
    stats['after_median_alpha_coverage'] = after.get('median_estimated_alpha_coverage')
    stats['after_median_safe_frame_union_coverage'] = after.get('median_safe_frame_union_coverage')
    stats['after_mean_temporal_population'] = after.get('mean_temporal_population')
    stats['changed'] = bool(
        stats['partition_groups_committed']
        or stats['root_actors_committed']
        or stats['semantic_cascade_committed']
    )
    stats['pass'] = _density_not_worse(before, after) and bool(composition_plan_qa(plan).get('pass'))
    if not stats['pass']:
        raise ValueError('REFERENCE_GEOMETRY_AND_SEMANTIC_FOCUS_FAILED')
    return stats
