"""Phase-settled QA contract shared by shipping composition certification.

A semantic phase destination is only "settled" after both its composition-state
transition and any entry preset that is still resolving at the phase boundary.
Trajectory safety remains owned by ``card_motion_conflicts`` and is sampled over
the complete motion path; this module does not relax those thresholds.
"""
from __future__ import annotations

_EPS = 1e-6
_BOUNDARY_TOLERANCE_SECONDS = 0.02
_SETTLE_PAD_SECONDS = 0.02


def _boundary_settle_time(event: dict, phase: dict) -> float:
    start = float(phase.get('start_seconds', 0.0))
    settle = start

    # The phase-owned semantic state starts at the boundary.  Late handoff and
    # independent sequence-envelope states are separate motion authorities and
    # must not move the settled sample to the end of the phase.
    states = list(event.get('composition_states') or []) + list(event.get('composition_participant_states') or [])
    for state in states:
        if state.get('sequence_envelope'):
            continue
        state_start = float(state.get('start_seconds', 0.0))
        if abs(state_start - start) > _BOUNDARY_TOLERANCE_SECONDS:
            continue
        duration = max(0.0, float(state.get('transition_duration_seconds') or 0.0))
        settle = max(settle, state_start + duration)

    # A newly entering actor is not a settled phase participant while its
    # supplied preset is still appearing/travelling.  The dynamic path QA sees
    # every intermediate frame; settled QA should inspect the readable arrival.
    entry = event.get('preset_entry') or {}
    if entry:
        entry_start = float(entry.get('start_seconds', event.get('start_seconds', start)))
        entry_duration = max(0.0, float(entry.get('duration_seconds') or 0.0))
        entry_end = entry_start + entry_duration
        if entry_start <= start + _BOUNDARY_TOLERANCE_SECONDS and entry_end > start:
            settle = max(settle, entry_end)

    return settle


def install(qa_module) -> None:
    if getattr(qa_module, '_phase_settled_qa_contract_installed', False):
        return

    base_settled_rect = qa_module._settled_rect

    def phase_settled_rect(event: dict, phase: dict):
        start = float(phase.get('start_seconds', 0.0))
        end = float(phase.get('end_seconds', start))
        if end <= start + _EPS:
            return base_settled_rect(event), 0.0

        settle = _boundary_settle_time(event, phase)
        # If the actor never reaches a settled/readable state inside this phase,
        # there is no legitimate endpoint sample.  Motion-path and viewport QA
        # still certify every visible intermediate frame; pacing QA owns whether
        # such a short phase is editorially acceptable.
        if settle >= end - _EPS:
            return base_settled_rect(event), 0.0

        sample_time = min(end - _EPS, max(start + _SETTLE_PAD_SECONDS, settle + _SETTLE_PAD_SECONDS))
        state = qa_module._state(event, sample_time)
        if state is None:
            return base_settled_rect(event), 0.0
        return state[3], float(state[2])

    qa_module._phase_settled_rect = phase_settled_rect
    qa_module._phase_settled_qa_contract_installed = True
