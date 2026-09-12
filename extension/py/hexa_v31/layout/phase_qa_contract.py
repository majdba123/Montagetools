"""Phase-settled QA contract shared by shipping composition certification.

A semantic phase destination is only "settled" inside a real stable interval:
after inbound entry/phase transitions have completed and before any outbound
handoff, action, exit, or later composition transition begins. Trajectory safety
remains owned by ``card_motion_conflicts`` and viewport QA over the complete
motion path; this module does not relax those thresholds.
"""
from __future__ import annotations

_EPS = 1e-6
_BOUNDARY_TOLERANCE_SECONDS = 0.02
_SETTLE_PAD_SECONDS = 0.02


def _all_states(event: dict) -> list[dict]:
    return list(event.get('composition_states') or []) + list(event.get('composition_participant_states') or [])


def _boundary_settle_time(event: dict, phase: dict) -> float:
    start = float(phase.get('start_seconds', 0.0))
    settle = start

    # The semantic state authored at the phase boundary must finish arriving
    # before this can be called a settled destination.
    for state in _all_states(event):
        state_start = float(state.get('start_seconds', 0.0))
        if abs(state_start - start) > _BOUNDARY_TOLERANCE_SECONDS:
            continue
        duration = max(0.0, float(state.get('transition_duration_seconds') or 0.0))
        settle = max(settle, state_start + duration)

    # A newly entering actor is not settled while its supplied preset is still
    # appearing/travelling across the phase boundary.
    entry = event.get('preset_entry') or {}
    if entry:
        entry_start = float(entry.get('start_seconds', event.get('start_seconds', start)))
        entry_duration = max(0.0, float(entry.get('duration_seconds') or 0.0))
        entry_end = entry_start + entry_duration
        if entry_start <= start + _BOUNDARY_TOLERANCE_SECONDS and entry_end > start:
            settle = max(settle, entry_end)

    # A within-frame action already in progress at the boundary is also inbound
    # motion. Wait for it to complete rather than sampling its interpolation.
    for action in event.get('preset_actions') or []:
        action_start = float(action.get('start_seconds', 0.0))
        action_duration = max(0.0, float(action.get('duration_seconds') or 0.0))
        action_end = action_start + action_duration
        if action_start <= start + _BOUNDARY_TOLERANCE_SECONDS and action_end > start:
            settle = max(settle, action_end)

    return settle


def _stable_window_end(event: dict, phase: dict, settle: float) -> float:
    """Return the first outbound motion boundary after ``settle``.

    Settled QA validates a destination, not an exit/handoff interpolation. Every
    excluded outbound interval is still sampled by motion-path/viewport QA.
    """
    start = float(phase.get('start_seconds', 0.0))
    end = float(phase.get('end_seconds', start))
    physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', end)))
    stable_end = min(end, physical_end)

    exit_row = event.get('preset_exit') or {}
    if exit_row:
        exit_start = float(exit_row.get('start_seconds', stable_end))
        if exit_start > settle + _EPS:
            stable_end = min(stable_end, exit_start)

    for action in event.get('preset_actions') or []:
        action_start = float(action.get('start_seconds', stable_end))
        if action_start > settle + _EPS:
            stable_end = min(stable_end, action_start)

    # Any later composition state is a new handoff/recomposition authority. The
    # stable sample belongs before that transition begins, regardless of whether
    # it is an ordinary or independent sequence-envelope track.
    for state in _all_states(event):
        state_start = float(state.get('start_seconds', stable_end))
        if state_start > settle + _EPS:
            stable_end = min(stable_end, state_start)

    return stable_end


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
        stable_end = _stable_window_end(event, phase, settle)

        # Some intentionally short beats are entirely transition/handoff. They
        # have no static destination to certify. Motion-path and viewport QA still
        # inspect every visible intermediate frame, while pacing QA owns whether
        # the beat is editorially long enough.
        if stable_end <= settle + _SETTLE_PAD_SECONDS + _EPS:
            return base_settled_rect(event), 0.0

        sample_time = min(
            stable_end - _EPS,
            max(settle + _SETTLE_PAD_SECONDS, (settle + stable_end) * 0.5),
        )
        state = qa_module._state(event, sample_time)
        if state is None:
            return base_settled_rect(event), 0.0
        return state[3], float(state[2])

    qa_module._phase_settled_rect = phase_settled_rect
    qa_module._phase_settled_qa_contract_installed = True
