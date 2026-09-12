"""Preserve certified semantic-phase geometry through final physical certification.

The legacy final-certification repair predates phase-owned geometry. When any QA
failure is present it may re-run a card-wide static layout, changing the base
center/scale tuple while already-certified phase states still store scale factors
relative to the previous base. That can turn a safe phase destination into an
out-of-safe-frame destination even though the phase solver itself was valid.

This contract never weakens physical QA. It allows the legacy repair to run, then
rolls back only phase-owned base geometry if that repair made the final plan fail.
The rollback is accepted only when the complete canonical composition QA passes
on the exact restored state, including settled phase bounds, motion-path overlap,
and viewport clipping.
"""
from __future__ import annotations

import copy

_GEOMETRY_KEYS = (
    'card_rest_position_norm',
    'layout_scale_multiplier',
    'planned_rect_norm',
    'collision_envelope_rect_norm',
    'composition_role',
    'composite_atomic',
)


def _phase_owned(event: dict) -> bool:
    if event.get('editorial_phase_geometry_authority'):
        return True
    for container in ('composition_states', 'composition_participant_states'):
        for state in event.get(container) or []:
            if state.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY':
                return True
    return False


def _snapshot(event: dict) -> dict:
    return {
        key: (key in event, copy.deepcopy(event.get(key)))
        for key in _GEOMETRY_KEYS
    }


def _restore(event: dict, snapshot: dict) -> bool:
    changed = False
    for key, (present, value) in snapshot.items():
        current_present = key in event
        current_value = event.get(key)
        if current_present != present or current_value != value:
            changed = True
        if present:
            event[key] = copy.deepcopy(value)
        else:
            event.pop(key, None)
    return changed


def install(planner_module) -> None:
    """Install an idempotent fail-closed guard around final certification."""
    if getattr(planner_module, '_phase_owned_final_certification_contract_installed', False):
        return

    base_final_certification = planner_module._final_physical_certification

    def final_physical_certification(events, cards, fps):
        phase_owned = [event for event in events if _phase_owned(event)]
        if not phase_owned:
            return base_final_certification(events, cards, fps)

        # Cross-card placement is a legitimate late geometry authority. Apply it
        # before taking the rollback snapshot so a successful rollback never
        # discards a required cross-card placement repair.
        cross_card_placement = {
            'pass': True,
            'initial_conflict_count': 0,
            'repairs': [],
        }
        if any(
            event.get('visible_ink_fraction_basis') == 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX'
            for event in events
        ):
            from hexa_v31.composition_solver import certify_cross_card_placements

            cross_card_placement = certify_cross_card_placements(events, cards, fps)

        snapshots = {
            str(event.get('event_id')): _snapshot(event)
            for event in phase_owned
        }

        try:
            return base_final_certification(events, cards, fps)
        except ValueError as exc:
            if 'FINAL_PHYSICAL_CERTIFICATION_FAILED' not in str(exc):
                raise

            restored = []
            for event in phase_owned:
                event_id = str(event.get('event_id'))
                if _restore(event, snapshots[event_id]):
                    restored.append(event_id)

            # If legacy certification did not mutate phase-owned base geometry,
            # the failure is genuine and must remain a hard failure.
            if not restored:
                raise

            from hexa_v31.composition_qa import composition_plan_qa

            after = composition_plan_qa({
                'events': events,
                'visual_cards': cards,
                'fps': fps,
            })
            if not after.get('pass'):
                raise

            return {
                'pass': True,
                'repair_passes': 1,
                'before': {
                    'pass': False,
                    'failures': [str(exc)],
                    'authority': 'LEGACY_CARD_WIDE_REPAIR_REJECTED_FOR_PHASE_OWNED_GEOMETRY',
                },
                'after': after,
                'repairs': [{
                    'type': 'RESTORE_CERTIFIED_PHASE_OWNED_BASE_GEOMETRY',
                    'event_ids': sorted(restored),
                }],
                'cross_card_placement': cross_card_placement,
                'phase_owned_geometry_rollback': {
                    'restored_event_count': len(restored),
                    'authority': 'CANONICAL_PHASE_DESTINATION_QA_FAIL_CLOSED',
                },
            }

    final_physical_certification.__name__ = base_final_certification.__name__
    final_physical_certification.__doc__ = base_final_certification.__doc__
    planner_module._final_physical_certification = final_physical_certification
    planner_module._phase_owned_final_certification_contract_installed = True
