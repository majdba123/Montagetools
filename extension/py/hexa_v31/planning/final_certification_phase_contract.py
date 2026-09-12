"""Protect certified semantic-phase geometry during legacy final repair.

The final physical gate is allowed to remove unsafe optional motion and to run bounded
static fallbacks. Its older card-wide settled-geometry repair, however, predates
phase-owned composition states and can change the base center/scale beneath already
certified phase-relative scale factors. This guard preserves the phase solver's base
geometry unless the legacy mutation is actually required for canonical final QA.

No QA threshold is relaxed. A rollback is accepted only when the exact restored plan
passes the canonical composition QA (settled destinations, swept motion and viewport
clipping). Cross-card placement is applied before the snapshot so legitimate late
cross-card geometry authority is never discarded.
"""
from __future__ import annotations

import copy
import json

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
        if (key in event) != present or event.get(key) != value:
            changed = True
        if present:
            event[key] = copy.deepcopy(value)
        else:
            event.pop(key, None)
    return changed


def _restore_many(events: list[dict], snapshots: dict[str, dict]) -> list[str]:
    restored = []
    for event in events:
        event_id = str(event.get('event_id'))
        snapshot = snapshots.get(event_id)
        if snapshot is not None and _restore(event, snapshot):
            restored.append(event_id)
    return restored


def _failure_diagnostic(events: list[dict], cards: dict, failures: list[str]) -> str:
    """Emit one bounded generic phase snapshot for actionable CI failures."""
    if not failures:
        return '{}'
    first = str(failures[0])
    card_id = first.split('/', 1)[0] if '/' in first else ''
    phase_id = ''
    if '/' in first:
        phase_id = first.split('/', 1)[1].split(':', 1)[0]
    card = next((row for row in (cards.get('cards') or []) if str(row.get('card_id')) == card_id), None)
    phase = next(
        (
            row for row in ((card or {}).get('story_phase_plan') or {}).get('phases') or []
            if str(row.get('phase_id')) == phase_id
        ),
        None,
    )
    member_ids = {str(event_id) for event_id in ((phase or {}).get('event_ids') or [])}
    rows = []
    for event in events:
        event_id = str(event.get('event_id'))
        if member_ids and event_id not in member_ids:
            continue
        if not member_ids and str(event.get('visual_card_id')) != card_id:
            continue
        rows.append({
            'event_id': event_id,
            'scene_id': event.get('scene_id'),
            'attention_priority': event.get('attention_priority'),
            'base_center': event.get('card_rest_position_norm'),
            'base_scale': event.get('layout_scale_multiplier'),
            'planned_rect': event.get('planned_rect_norm'),
            'start_seconds': event.get('start_seconds'),
            'end_seconds': event.get('end_seconds'),
            'physical_start_seconds': event.get('physical_start_seconds'),
            'physical_end_seconds': event.get('physical_end_seconds'),
            'preset_entry': event.get('preset_entry'),
            'preset_exit': event.get('preset_exit'),
            'phase_states': [
                {
                    'state_id': state.get('state_id'),
                    'start_seconds': state.get('start_seconds'),
                    'transition_duration_seconds': state.get('transition_duration_seconds'),
                    'center_norm': state.get('center_norm'),
                    'scale_multiplier': state.get('scale_multiplier'),
                    'visibility': state.get('visibility'),
                    'state_reason': state.get('state_reason'),
                    'semantic_beat': state.get('semantic_beat'),
                }
                for state in (
                    list(event.get('composition_states') or [])
                    + list(event.get('composition_participant_states') or [])
                )
                if state.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY'
            ],
        })
    return json.dumps({
        'failure': first,
        'card_id': card_id,
        'phase_id': phase_id,
        'phase': phase,
        'events': rows[:8],
    }, sort_keys=True, separators=(',', ':'))


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
        # before the rollback baseline so restoring phase-owned geometry never
        # discards a required cross-card placement correction.
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

        baseline = {
            str(event.get('event_id')): _snapshot(event)
            for event in phase_owned
        }

        base_result = None
        base_error = None
        try:
            base_result = base_final_certification(events, cards, fps)
        except ValueError as exc:
            if 'FINAL_PHYSICAL_CERTIFICATION_FAILED' not in str(exc):
                raise
            base_error = exc

        # Capture the legacy result before testing the phase-owned baseline. If
        # restoring the baseline is not valid, a successful legacy result can be
        # reinstated exactly rather than recomputed nondeterministically.
        legacy_geometry = {
            str(event.get('event_id')): _snapshot(event)
            for event in phase_owned
        }
        restored = _restore_many(phase_owned, baseline)

        from hexa_v31.composition_qa import composition_plan_qa

        restored_qa = composition_plan_qa({
            'events': events,
            'visual_cards': cards,
            'fps': fps,
        })

        if restored_qa.get('pass'):
            if not restored:
                # Base certification made no phase-owned geometry change. Preserve
                # its normal success result; a failure in this branch is genuine.
                if base_result is not None:
                    return base_result
                raise base_error

            repairs = list((base_result or {}).get('repairs') or [])
            repairs.append({
                'type': 'RESTORE_CERTIFIED_PHASE_OWNED_BASE_GEOMETRY',
                'event_ids': sorted(restored),
            })
            return {
                'pass': True,
                'repair_passes': max(1, int((base_result or {}).get('repair_passes') or 0)),
                'before': (base_result or {}).get('before') or {
                    'pass': False,
                    'failures': [str(base_error)] if base_error is not None else [],
                    'authority': 'LEGACY_CARD_WIDE_REPAIR_REJECTED_FOR_PHASE_OWNED_GEOMETRY',
                },
                'after': restored_qa,
                'repairs': repairs,
                'cross_card_placement': (base_result or {}).get('cross_card_placement') or cross_card_placement,
                'phase_owned_geometry_rollback': {
                    'restored_event_count': len(restored),
                    'authority': 'CANONICAL_PHASE_DESTINATION_QA_FAIL_CLOSED',
                },
            }

        # Restoration did not certify the plan. If the legacy repair itself was
        # successful, reinstate exactly that geometry and keep its certified result.
        if base_result is not None and base_result.get('pass'):
            _restore_many(phase_owned, legacy_geometry)
            return base_result

        # Neither state is certifiable. Leave the safer phase-owned baseline in
        # place and include one bounded state snapshot so CI identifies the true
        # geometry/timing authority instead of requiring another blind patch.
        diagnostic = _failure_diagnostic(events, cards, restored_qa.get('failures') or [])
        if base_error is not None:
            raise ValueError(
                str(base_error)
                + ' | RESTORED_PHASE_QA='
                + ' | '.join(restored_qa.get('failures') or [])[:1200]
                + ' | PHASE_STATE_DIAGNOSTIC='
                + diagnostic[:6000]
            ) from base_error
        raise ValueError(
            'FINAL_PHYSICAL_CERTIFICATION_FAILED_AFTER_PHASE_GEOMETRY_ROLLBACK: '
            + ' | '.join(restored_qa.get('failures') or [])[:1600]
            + ' | PHASE_STATE_DIAGNOSTIC='
            + diagnostic[:6000]
        )

    final_physical_certification.__name__ = base_final_certification.__name__
    final_physical_certification.__doc__ = base_final_certification.__doc__
    planner_module._final_physical_certification = final_physical_certification
    planner_module._phase_owned_final_certification_contract_installed = True
