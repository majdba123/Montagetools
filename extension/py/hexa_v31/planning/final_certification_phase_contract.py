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


def _clamp_movable_phase_states_to_safe_frame(events: list[dict]) -> list[str]:
    """Keep phase destinations legal after late footprint/scale finalizers.

    Late reference passes may change an independent root's effective footprint
    after phase geometry was solved. Re-center only movable ROOT_ATOMIC phase
    states by the minimum delta; protected partition/residual geometry is never
    touched and scale/semantic timing remain unchanged.
    """
    from hexa_v31.layout.composition_solver import SAFE_X, SAFE_Y, _fp, _rect
    from hexa_v31.composition_qa import _state

    changed=[]
    for event in events:
        protected=(str(event.get('render_mode') or 'ROOT_ATOMIC') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} or bool(event.get('partition_group_id')))
        fp=_fp(event);base_scale=float(event.get('layout_scale_multiplier') or 1.0)
        for container in ('composition_states','composition_participant_states'):
            for state in event.get(container) or []:
                if state.get('state_reason')!='SEMANTIC_ARCHETYPE_PHASE_GEOMETRY':continue
                center=list(state.get('center_norm') or event.get('card_rest_position_norm') or [.5,.5])
                if len(center)<2:continue
                if protected:
                    destination=[round(float(x),6) for x in (event.get('card_rest_position_norm') or center)]
                    if destination!=list(center) or abs(float(state.get('scale_multiplier') or 1.0)-1.0)>1e-9:
                        state['center_norm']=destination
                        state['scale_multiplier']=1.0
                        state['protected_geometry_restored']='P1_PARTITION_BASE_GEOMETRY'
                        changed.append(str(event.get('event_id')))
                    continue
                state_scale=float(state.get('scale_multiplier') or 1.0)
                planned=list(event.get('planned_rect_norm') or [])
                if len(planned)==4:
                    width=float(planned[2])*state_scale;height=float(planned[3])*state_scale
                    rect=(float(center[0])-width/2,float(center[1])-height/2,width,height)
                else:
                    sample=float(state.get('start_seconds') or 0.0)+float(state.get('transition_duration_seconds') or 0.0)+1e-4
                    actual=_state(event,sample)
                    rect=(actual[3] if actual is not None else
                          _rect((float(center[0]),float(center[1])),fp,base_scale*state_scale))
                cx=float(center[0]);cy=float(center[1])
                if rect[0]<SAFE_X[0]:cx+=SAFE_X[0]-rect[0]
                if rect[0]+rect[2]>SAFE_X[1]:cx-=rect[0]+rect[2]-SAFE_X[1]
                if rect[1]<SAFE_Y[0]:cy+=SAFE_Y[0]-rect[1]
                if rect[1]+rect[3]>SAFE_Y[1]:cy-=rect[1]+rect[3]-SAFE_Y[1]
                destination=[round(cx,6),round(cy,6)]
                if destination!=list(center):
                    state['center_norm']=destination
                    state['late_footprint_safe_frame_recenter']='MINIMUM_PHASE_DESTINATION_DELTA'
                    changed.append(str(event.get('event_id')))
    return sorted(set(changed))


def _serialized_state(state: dict) -> dict:
    return {
        key: state.get(key)
        for key in (
            'state_id', 'owner_state_id', 'previous_state_id', 'state_reason',
            'semantic_beat', 'start_seconds', 'transition_duration_seconds',
            'center_norm', 'scale_multiplier', 'visibility', 'sequence_envelope',
            'position_envelope', 'envelope_track', 'editorial_motion_family',
            'translation_safe', 'phase_center_authority',
        )
        if state.get(key) is not None
    }


def _failure_diagnostic(events: list[dict], cards: dict, failures: list[str]) -> str:
    """Emit the exact common settled pixel-state authority for the first failure."""
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
    members = [
        event for event in events
        if (str(event.get('event_id')) in member_ids if member_ids else str(event.get('visual_card_id')) == card_id)
    ]

    common_sample = None
    windows = []
    if phase and members:
        try:
            from hexa_v31.layout.phase_qa_contract import _stable_window, _sample_time

            windows = [
                {
                    'event_id': str(event.get('event_id')),
                    'window': [round(float(value), 6) for value in _stable_window(event, phase)],
                }
                for event in members
            ]
            common_start = max(row['window'][0] for row in windows)
            common_end = min(row['window'][1] for row in windows)
            common_sample = _sample_time(common_start, common_end)
        except Exception as exc:  # diagnostics must never mask the certification failure
            windows = [{'diagnostic_error': type(exc).__name__ + ':' + str(exc)[:240]}]

    actual_by_id = {}
    actual_pair_overlaps = []
    if common_sample is not None:
        try:
            from hexa_v31.composition_qa import _state
            from hexa_v31.composition_solver import overlap_ratio

            visible = []
            for event in members:
                actual = _state(event, common_sample)
                if actual is None:
                    actual_by_id[str(event.get('event_id'))] = None
                    continue
                row = {
                    'center_norm': [round(float(x), 6) for x in actual[0]],
                    'scale': round(float(actual[1]), 6),
                    'opacity': round(float(actual[2]), 6),
                    'rect_norm': [round(float(x), 6) for x in actual[3]],
                }
                actual_by_id[str(event.get('event_id'))] = row
                if float(actual[2]) > 0.05:
                    visible.append((event, actual[3]))
            for index, (a, rect_a) in enumerate(visible):
                for b, rect_b in visible[index + 1:]:
                    actual_pair_overlaps.append({
                        'event_a': str(a.get('event_id')),
                        'event_b': str(b.get('event_id')),
                        'overlap_ratio': round(float(overlap_ratio(rect_a, rect_b)), 9),
                    })
        except Exception as exc:  # diagnostics must never mask the certification failure
            actual_by_id['diagnostic_error'] = type(exc).__name__ + ':' + str(exc)[:240]

    rows = []
    for event in members:
        event_id = str(event.get('event_id'))
        rows.append({
            'event_id': event_id,
            'scene_id': event.get('scene_id'),
            'attention_priority': event.get('attention_priority'),
            'base_center': event.get('card_rest_position_norm'),
            'base_scale': event.get('layout_scale_multiplier'),
            'planned_rect': event.get('planned_rect_norm'),
            'start_seconds': event.get('start_seconds'),
            'end_seconds': event.get('end_seconds'),
            'motion_start_seconds': event.get('motion_start_seconds'),
            'motion_end_seconds': event.get('motion_end_seconds'),
            'physical_start_seconds': event.get('physical_start_seconds'),
            'physical_end_seconds': event.get('physical_end_seconds'),
            'preset_entry': event.get('preset_entry'),
            'preset_exit': event.get('preset_exit'),
            'preset_actions': event.get('preset_actions') or [],
            'progressive_phase_authority': event.get('progressive_phase_authority'),
            'adaptive_composition_authority': event.get('adaptive_composition_authority'),
            'meaningful_recomposition': event.get('meaningful_recomposition'),
            'readable_hold_authority': event.get('readable_hold_authority'),
            'final_cross_source_handoff_authority': event.get('final_cross_source_handoff_authority'),
            'composition_states': [_serialized_state(state) for state in event.get('composition_states') or []],
            'composition_participant_states': [
                _serialized_state(state) for state in event.get('composition_participant_states') or []
            ],
            'actual_common_sample_state': actual_by_id.get(event_id),
        })
    return json.dumps({
        'failure': first,
        'card_id': card_id,
        'phase_id': phase_id,
        'phase': phase,
        'stable_windows': windows,
        'common_sample_seconds': None if common_sample is None else round(float(common_sample), 6),
        'actual_pair_overlaps': actual_pair_overlaps,
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

        recentered=_clamp_movable_phase_states_to_safe_frame(phase_owned)

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
            recentered=sorted(set(recentered+_clamp_movable_phase_states_to_safe_frame(phase_owned)))

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
                'late_phase_safe_frame_recentered_event_ids': recentered,
            }

        # Restoration did not certify the plan. If the legacy repair itself was
        # successful, reinstate exactly that geometry and keep its certified result.
        if base_result is not None and base_result.get('pass'):
            _restore_many(phase_owned, legacy_geometry)
            return base_result

        # Neither state is certifiable. Leave the safer phase-owned baseline in
        # place and include the exact common settled render state so CI identifies
        # the true geometry/timing authority instead of requiring another blind patch.
        diagnostic = _failure_diagnostic(events, cards, restored_qa.get('failures') or [])
        if base_error is not None:
            raise ValueError(
                str(base_error)
                + ' | RESTORED_PHASE_QA='
                + ' | '.join(restored_qa.get('failures') or [])[:1200]
                + ' | PHASE_STATE_DIAGNOSTIC='
                + diagnostic[:12000]
            ) from base_error
        raise ValueError(
            'FINAL_PHYSICAL_CERTIFICATION_FAILED_AFTER_PHASE_GEOMETRY_ROLLBACK: '
            + ' | '.join(restored_qa.get('failures') or [])[:1600]
            + ' | PHASE_STATE_DIAGNOSTIC='
            + diagnostic[:12000]
        )

    final_physical_certification.__name__ = base_final_certification.__name__
    final_physical_certification.__doc__ = base_final_certification.__doc__
    planner_module._final_physical_certification = final_physical_certification
    planner_module._phase_owned_final_certification_contract_installed = True
