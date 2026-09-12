"""Phase-authority guard for legacy late composition optimizers.

V31's editorial phase compiler owns absolute semantic-phase geometry. Several older
late optimizers predate that ownership model and mutate card-wide rest geometry or add
generic recomposition states after phase destinations have already been certified.
Those mutations can be individually trajectory-safe yet still invalidate the stricter
settled readability contract or create state-authority conflicts in the renderer.

This module installs a narrow compatibility guard around those legacy optimizers. It
does not change QA thresholds and it does not disable the optimizers for legacy/non-
phase plans. Phase-owned actors (and pairs that would write into a phase-owned next
actor) are simply withheld from legacy mutation. Round 3 independent sequence tracks
and the final cross-card handoff solver remain available later in the shipping path.
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
    """Install idempotent guards around legacy late optimizers."""
    if getattr(planner_module, "_phase_optimizer_contract_installed", False):
        return

    base_adaptive = planner_module._adaptive_composition_state_optimize
    base_recomposition = planner_module._recomposition_optimize
    base_optical = planner_module._optical_scale_optimize
    base_spatial = planner_module._spatial_choreography_optimize
    base_variety = planner_module._effect_variety_director

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

    planner_module._adaptive_composition_state_optimize = adaptive
    planner_module._recomposition_optimize = recomposition
    planner_module._optical_scale_optimize = optical
    planner_module._spatial_choreography_optimize = spatial
    planner_module._effect_variety_director = variety
    planner_module._phase_optimizer_contract_installed = True
