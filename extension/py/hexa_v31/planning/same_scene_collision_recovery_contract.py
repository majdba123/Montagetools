"""Late recovery for residual same-scene geometry collisions.

Round 2/3 deliberately keep same-scene collisions hard while ordered cross-scene
carrier overlap may be deferred to the final readable-successor handoff authority.
The early planner can still reach a residual case where optional motion has already
been removed, yet two independent source roots occupy incompatible settled geometry.

This contract handles only that missing case. It never relaxes collision thresholds,
changes source lifetimes, suppresses actors, or moves protected partition/residual
geometry. Instead it re-solves independent same-scene roots against their exact
physical co-occurrence intervals using the canonical layout solver, then delegates
again to the existing recovery chain so any remaining ordered cross-scene conflict is
owned by the final bounded handoff reconciler.
"""
from __future__ import annotations

import copy


_ERROR_TOKEN = 'NO_COLLISION_FREE_SPATIOTEMPORAL_PLAN after preset-safe recovery'
_AUTHORITY = 'LATE_SAME_SCENE_EXACT_PHYSICAL_COOCCURRENCE_LAYOUT'
_EPS = 1e-9


def _event_id(event: dict) -> str:
    return str(event.get('event_id') or '')


def _scene_id(event: dict) -> str:
    return str(event.get('scene_id') or '')


def _physical_window(event: dict, card_start: float, card_end: float) -> tuple[float, float]:
    start = float(event.get('physical_start_seconds', event.get('start_seconds', card_start)))
    end = float(event.get('physical_end_seconds', event.get('end_seconds', start)))
    return max(card_start, start), min(card_end, end)


def _same_scene_conflict_rows(conflicts: list[dict], events: list[dict]) -> list[dict]:
    by_id = {_event_id(event): event for event in events}
    rows = []
    for row in conflicts:
        a = by_id.get(str(row.get('event_a') or ''))
        b = by_id.get(str(row.get('event_b') or ''))
        if a is None or b is None:
            continue
        scene_a = _scene_id(a)
        scene_b = _scene_id(b)
        if scene_a and scene_a == scene_b:
            rows.append(row)
    return rows


def _same_scene_conflict_scenes(conflicts: list[dict], events: list[dict]) -> set[str]:
    by_id = {_event_id(event): event for event in events}
    scenes: set[str] = set()
    for row in _same_scene_conflict_rows(conflicts, events):
        event = by_id.get(str(row.get('event_a') or ''))
        if event is not None and _scene_id(event):
            scenes.add(_scene_id(event))
    return scenes


def _is_independent_root(event: dict) -> bool:
    return (
        str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and not event.get('partition_group_id')
    )


def _exact_physical_cooccurrence_plan(
    events: list[dict],
    card_start: float,
    card_end: float,
) -> dict:
    """Describe only intervals in which the source carriers physically coexist.

    This is a geometry constraint map, not a semantic retime. Event lifetimes are
    read but never modified. Consecutive intervals with the same active set collapse
    into one phase so the canonical solver sees the minimum exact co-occurrence graph.
    """
    windows: dict[str, tuple[float, float]] = {}
    boundaries = {float(card_start), float(card_end)}
    for event in events:
        event_id = _event_id(event)
        if not event_id:
            continue
        start, end = _physical_window(event, card_start, card_end)
        if end <= start + _EPS:
            continue
        windows[event_id] = (start, end)
        boundaries.add(start)
        boundaries.add(end)

    ordered = sorted(boundaries)
    phases: list[dict] = []
    for left, right in zip(ordered, ordered[1:]):
        if right <= left + _EPS:
            continue
        midpoint = (left + right) * 0.5
        active = sorted(
            event_id
            for event_id, (start, end) in windows.items()
            if start <= midpoint + _EPS and midpoint < end - _EPS
        )
        if not active:
            continue
        if phases and phases[-1]['event_ids'] == active and abs(float(phases[-1]['end_seconds']) - left) <= 1e-6:
            phases[-1]['end_seconds'] = round(right, 6)
            continue
        phases.append({
            'phase_id': f'PHYSICAL_COOCCURRENCE_{len(phases) + 1:02d}',
            'start_seconds': round(left, 6),
            'end_seconds': round(right, 6),
            'event_ids': active,
        })

    return {
        'schema': 'HEXA_EXACT_PHYSICAL_COOCCURRENCE_GEOMETRY_V1',
        'phases': phases,
        'phase_count': len(phases),
        'geometry_only': True,
        'authority': _AUTHORITY,
    }


def _remove_stale_phase_geometry(event: dict) -> int:
    removed = 0
    for container in ('composition_states', 'composition_participant_states'):
        kept = []
        for state in event.get(container) or []:
            state_id = str(state.get('state_id') or '')
            semantic_beat = str(state.get('semantic_beat') or '')
            phase_owned = (
                state.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY'
                or state_id.endswith('::EDITORIAL_GEOMETRY')
                or state_id.endswith('::HANDOFF_GEOMETRY')
                or semantic_beat == 'HANDOFF_GEOMETRY'
            )
            if phase_owned:
                removed += 1
            else:
                kept.append(state)
        if kept:
            event[container] = kept
        else:
            event.pop(container, None)
    return removed


def _apply_scene_layout(impl, card: dict, events: list[dict], scene_id: str) -> tuple[bool, int]:
    card_start = float(card.get('start_seconds', 0.0))
    card_end = float(card.get('end_seconds', card_start))
    scene_events = [
        event for event in events
        if not event.get('suppressed_by_card_density')
        and _scene_id(event) == scene_id
        and _is_independent_root(event)
        and _physical_window(event, card_start, card_end)[1]
            > _physical_window(event, card_start, card_end)[0] + _EPS
    ]
    if len(scene_events) < 2:
        return False, 0

    phase_plan = _exact_physical_cooccurrence_plan(scene_events, card_start, card_end)
    if not phase_plan.get('phases'):
        return False, 0

    grammar = card.get('universal_scene_grammar') or {
        'archetype': 'GENERIC',
        'roles': {},
        'explicit_edges': [],
    }
    layout = impl.solve_card_layout(scene_events, grammar, phase_plan)
    if not layout.get('pass'):
        return False, 0

    placements = layout.get('placements') or {}
    if any(_event_id(event) not in placements for event in scene_events):
        return False, 0

    stale_state_count = 0
    for event in scene_events:
        event_id = _event_id(event)
        placement = placements[event_id]
        event['card_rest_position_norm'] = [float(v) for v in placement['center_norm']]
        event['layout_scale_multiplier'] = float(placement['scale'])
        event['planned_rect_norm'] = [float(v) for v in placement['rect_norm']]
        event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
        stale_state_count += _remove_stale_phase_geometry(event)
        # Keep late generic optimizers from reintroducing the displaced phase track.
        event['editorial_phase_geometry_authority'] = _AUTHORITY
        event['late_same_scene_collision_recovery_authority'] = _AUTHORITY
        event['late_same_scene_collision_recovery_scene_id'] = scene_id

    return True, stale_state_count


def install(impl) -> None:
    if getattr(impl, '_same_scene_collision_recovery_contract_installed', False):
        return

    base_recover = impl._recover_trajectory_conflicts

    def recover_trajectory_conflicts(card, events, phase_plan, resolutions, fps):
        try:
            return base_recover(card, events, phase_plan, resolutions, fps)
        except ValueError as exc:
            if _ERROR_TOKEN not in str(exc):
                raise
            original_exc = exc

        card_start = float(card.get('start_seconds', 0.0))
        card_end = float(card.get('end_seconds', card_start))
        conflicts = impl.card_motion_conflicts(events, card_start, card_end, fps)
        same_scene_rows = _same_scene_conflict_rows(conflicts, events)
        scenes = sorted(_same_scene_conflict_scenes(conflicts, events))
        if not same_scene_rows or not scenes:
            raise original_exc

        by_id = {_event_id(event): event for event in events}
        same_scene_involved = {
            str(event_id)
            for row in same_scene_rows
            for event_id in (row.get('event_a'), row.get('event_b'))
            if event_id is not None and str(event_id) in by_id
        }
        # Never use this fallback to move protected partition/residual geometry.
        if any(not _is_independent_root(by_id[event_id]) for event_id in same_scene_involved):
            raise original_exc

        snapshots = {
            _event_id(event): copy.deepcopy(event)
            for event in events
            if _scene_id(event) in scenes
        }
        recovered_scenes = []
        stale_state_count = 0
        for scene_id in scenes:
            changed, removed = _apply_scene_layout(impl, card, events, scene_id)
            if not changed:
                for event in events:
                    snap = snapshots.get(_event_id(event))
                    if snap is not None:
                        event.clear(); event.update(copy.deepcopy(snap))
                raise original_exc
            recovered_scenes.append(scene_id)
            stale_state_count += removed

        remaining = impl.card_motion_conflicts(events, card_start, card_end, fps)
        if _same_scene_conflict_rows(remaining, events):
            for event in events:
                snap = snapshots.get(_event_id(event))
                if snap is not None:
                    event.clear(); event.update(copy.deepcopy(snap))
            raise original_exc

        card['late_same_scene_collision_recovery'] = _AUTHORITY
        card['late_same_scene_collision_recovery_scene_count'] = len(recovered_scenes)
        card['late_same_scene_collision_recovery_stale_state_count'] = stale_state_count

        # Re-enter the established recovery chain. With same-scene geometry now hard
        # certified, it either returns cleanly or delegates any ordered cross-scene
        # carrier overlap to FINAL_CROSS_SCENE_BOUNDED_HANDOFF_SEARCH.
        return base_recover(card, events, phase_plan, resolutions, fps)

    recover_trajectory_conflicts.__name__ = base_recover.__name__
    recover_trajectory_conflicts.__doc__ = base_recover.__doc__
    impl._recover_trajectory_conflicts = recover_trajectory_conflicts
    impl._same_scene_collision_recovery_contract_installed = True
