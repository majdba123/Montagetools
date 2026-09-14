"""Phase-authority compatibility contract for the V31 shipping planner.

The editorial phase compiler owns absolute semantic-phase geometry. Older card-wide
history and late-optimizer code predates that ownership model. Two failure classes are
closed here without relaxing QA:

* phase placement centers must be encoded into the actual composition state consumed by
  QA and rendering (not replaced by the card-wide base center);
* a mirrored card variant must mirror phase-local placements as the same atomic geometry
  transformation, otherwise base and phase coordinate systems disagree;
* legacy late optimizers must not mutate phase-owned base geometry or layer generic state
  authority over a certified semantic phase.

Legacy/non-phase plans keep their existing behavior. Round 3 independent sequence tracks
and final cross-card handoff logic remain available downstream.
"""
from __future__ import annotations

import copy

_SENTINEL_STATE_ID = "__HEXA_PHASE_AUTHORITY_OPTIMIZER_GUARD__"
_SENTINEL_ACTION_NAME = "__HEXA_PHASE_AUTHORITY_OPTIMIZER_GUARD__"


def _phase_owned(event: dict) -> bool:
    if event.get("editorial_phase_geometry_authority"):
        return True
    for container in ("composition_states", "composition_participant_states"):
        for state in event.get(container) or []:
            if state.get("state_reason") == "SEMANTIC_ARCHETYPE_PHASE_GEOMETRY":
                return True
    return False


def _event_id(event: dict) -> str:
    return str(event.get("event_id") or "")


def _mirror_placement(placement: dict) -> None:
    center = list(placement.get("center_norm") or [])
    rect = list(placement.get("rect_norm") or [])
    if len(center) >= 2:
        center[0] = round(1.0 - float(center[0]), 6)
        placement["center_norm"] = center
    if len(rect) == 4:
        rect[0] = round(1.0 - float(rect[0]) - float(rect[2]), 6)
        placement["rect_norm"] = rect


def _phase_pair_current_ids(events: list[dict], cards: dict) -> set[str]:
    """Return currents whose legacy pair mutation would touch phase authority."""
    ids: set[str] = set()
    for card in cards.get("cards") or []:
        start = float(card.get("start_seconds", 0.0))
        end = float(card.get("end_seconds", start))
        local = sorted(
            (
                event
                for event in events
                if not event.get("suppressed_by_card_density")
                and float(event.get("start_seconds", 0.0)) < end
                and float(event.get("end_seconds", 0.0)) > start
            ),
            key=lambda event: (
                float(event.get("perceptual_hit_seconds", event.get("start_seconds", 0.0))),
                _event_id(event),
            ),
        )
        for current, nxt in zip(local, local[1:]):
            if _phase_owned(current) or _phase_owned(nxt):
                ids.add(_event_id(current))
    return ids


def _with_future_state_shields(events: list[dict], event_ids: set[str]):
    snapshots: dict[str, tuple[bool, object]] = {}
    for event in events:
        event_id = _event_id(event)
        if event_id not in event_ids or event.get("composition_states"):
            continue
        snapshots[event_id] = ("composition_states" in event, copy.deepcopy(event.get("composition_states")))
        event["composition_states"] = [
            {
                "state_id": _SENTINEL_STATE_ID,
                "start_seconds": 1.0e12,
                "transition_duration_seconds": 0.0,
                "visibility": 1.0,
                "temporary_optimizer_guard": True,
            }
        ]
    return snapshots


def _restore_states(events: list[dict], snapshots: dict[str, tuple[bool, object]]) -> None:
    for event in events:
        event_id = _event_id(event)
        if event_id not in snapshots:
            continue
        present, value = snapshots[event_id]
        if present:
            event["composition_states"] = value
        else:
            event.pop("composition_states", None)


def _with_future_action_shields(events: list[dict], event_ids: set[str]):
    snapshots: dict[str, tuple[bool, object]] = {}
    for event in events:
        event_id = _event_id(event)
        if event_id not in event_ids or event.get("preset_actions"):
            continue
        snapshots[event_id] = ("preset_actions" in event, copy.deepcopy(event.get("preset_actions")))
        event["preset_actions"] = [
            {
                "name": _SENTINEL_ACTION_NAME,
                "start_seconds": 1.0e12,
                "duration_seconds": 0.0,
                "temporary_optimizer_guard": True,
            }
        ]
    return snapshots


def _restore_actions(events: list[dict], snapshots: dict[str, tuple[bool, object]]) -> None:
    for event in events:
        event_id = _event_id(event)
        if event_id not in snapshots:
            continue
        present, value = snapshots[event_id]
        if present:
            event["preset_actions"] = value
        else:
            event.pop("preset_actions", None)


def install(planner_module) -> None:
    """Install idempotent phase-geometry and late-optimizer compatibility guards."""
    if getattr(planner_module, "_phase_optimizer_contract_installed", False):
        return

    base_history_variant = planner_module._apply_composition_history_variant
    base_commit_phase_geometry = planner_module._commit_editorial_phase_geometry
    base_adaptive = planner_module._adaptive_composition_state_optimize
    base_recomposition = planner_module._recomposition_optimize
    base_optical = planner_module._optical_scale_optimize
    base_spatial = planner_module._spatial_choreography_optimize
    base_variety = planner_module._effect_variety_director

    def history_variant(layout, grammar, history):
        variant = base_history_variant(layout, grammar, history)
        if variant == "MIRRORED":
            # The legacy helper mirrored only card-wide placements. Phase-local
            # destinations are the same geometry authority and must transform with
            # them or the renderer receives two incompatible coordinate spaces.
            if layout.get("phase_geometry_history_variant") != "MIRRORED_ATOMIC_WITH_BASE":
                for placements in (layout.get("phase_placements") or {}).values():
                    for placement in (placements or {}).values():
                        _mirror_placement(placement)
            layout["phase_geometry_history_variant"] = "MIRRORED_ATOMIC_WITH_BASE"
        return variant

    def commit_phase_geometry(events, card, phase_plan, layout):
        base_commit_phase_geometry(events, card, phase_plan, layout)
        phase_placements = layout.get("phase_placements") or {}
        by_id = {_event_id(event): event for event in events}
        corrected = 0
        for phase in phase_plan.get("phases") or []:
            phase_id = str(phase.get("phase_id") or "")
            placements = phase_placements.get(phase_id) or {}
            for event_id, placement in placements.items():
                event = by_id.get(str(event_id))
                center = list((placement or {}).get("center_norm") or [])
                if event is None or len(center) < 2:
                    continue
                expected_state_id = f"{phase_id}::{event_id}::EDITORIAL_GEOMETRY"
                found = False
                for container in ("composition_states", "composition_participant_states"):
                    for state in event.get(container) or []:
                        if (
                            str(state.get("state_id") or "") == expected_state_id
                            and state.get("state_reason") == "SEMANTIC_ARCHETYPE_PHASE_GEOMETRY"
                        ):
                            destination = [round(float(center[0]), 6), round(float(center[1]), 6)]
                            if list(state.get("center_norm") or []) != destination:
                                corrected += 1
                            state["center_norm"] = destination
                            state["phase_center_authority"] = "ABSOLUTE_PHASE_PLACEMENT_CENTER"
                            found = True
                if not found:
                    raise ValueError(
                        f"{phase_id}/{event_id}: missing encoded semantic phase geometry state"
                    )
        if corrected:
            card["phase_center_encoding_correction_count"] = corrected
        card["phase_center_encoding_authority"] = "ABSOLUTE_PHASE_PLACEMENT_CENTER"

    def adaptive(events, cards, fps):
        protected = {_event_id(event) for event in events if _phase_owned(event)}
        protected.update(_phase_pair_current_ids(events, cards))
        snapshots = _with_future_state_shields(events, protected)
        try:
            stats = base_adaptive(events, cards, fps)
        finally:
            _restore_states(events, snapshots)
        stats["phase_authority_guarded_event_count"] = len(protected)
        return stats

    def recomposition(events, cards, fps):
        protected = {_event_id(event) for event in events if _phase_owned(event)}
        protected.update(_phase_pair_current_ids(events, cards))
        snapshots = _with_future_action_shields(events, protected)
        try:
            stats = base_recomposition(events, cards, fps)
        finally:
            _restore_actions(events, snapshots)
        stats["phase_authority_guarded_event_count"] = len(protected)
        return stats

    def optical(events, cards, fps):
        snapshots: dict[str, tuple[bool, object]] = {}
        for event in events:
            if not _phase_owned(event) or str(event.get("attention_priority") or "").upper() != "PRIMARY":
                continue
            event_id = _event_id(event)
            snapshots[event_id] = ("planned_rect_norm" in event, copy.deepcopy(event.get("planned_rect_norm")))
            event["planned_rect_norm"] = None
        try:
            stats = base_optical(events, cards, fps)
        finally:
            for event in events:
                event_id = _event_id(event)
                if event_id not in snapshots:
                    continue
                present, value = snapshots[event_id]
                if present:
                    event["planned_rect_norm"] = value
                else:
                    event.pop("planned_rect_norm", None)
        stats["phase_authority_guarded_event_count"] = len(snapshots)
        return stats

    def spatial(events, cards, fps):
        snapshots: dict[str, tuple[bool, object]] = {}
        for event in events:
            if not _phase_owned(event) or event.get("progressive_phase_authority"):
                continue
            event_id = _event_id(event)
            snapshots[event_id] = (
                "progressive_phase_authority" in event,
                copy.deepcopy(event.get("progressive_phase_authority")),
            )
            event["progressive_phase_authority"] = "PHASE_GEOMETRY_COMPATIBILITY_GUARD"
        try:
            stats = base_spatial(events, cards, fps)
        finally:
            for event in events:
                event_id = _event_id(event)
                if event_id not in snapshots:
                    continue
                present, value = snapshots[event_id]
                if present:
                    event["progressive_phase_authority"] = value
                else:
                    event.pop("progressive_phase_authority", None)
        stats["phase_authority_guarded_event_count"] = len(snapshots)
        return stats

    def variety(events, cards, fps):
        protected = {_event_id(event) for event in events if _phase_owned(event)}
        protected.update(_phase_pair_current_ids(events, cards))
        snapshots = _with_future_action_shields(events, protected)
        try:
            stats = base_variety(events, cards, fps)
        finally:
            _restore_actions(events, snapshots)
        stats["phase_authority_guarded_event_count"] = len(protected)
        return stats

    planner_module._apply_composition_history_variant = history_variant
    planner_module._commit_editorial_phase_geometry = commit_phase_geometry
    planner_module._adaptive_composition_state_optimize = adaptive
    planner_module._recomposition_optimize = recomposition
    planner_module._optical_scale_optimize = optical
    planner_module._spatial_choreography_optimize = spatial
    planner_module._effect_variety_director = variety
    planner_module._phase_optimizer_contract_installed = True
