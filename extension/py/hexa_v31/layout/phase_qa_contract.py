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


def _is_editorial_entry_state(state: dict) -> bool:
    """Return True only for the explicit positional entry envelope track.

    Round 3 may express a directional reveal as composition states rather than
    a positional ``preset_entry``. These states are inbound motion, not settled
    phase geometry. Restricting the classification to the explicit entry track
    avoids treating ordinary later recomposition/handoff states as inbound.
    """
    if not bool(state.get('position_envelope')):
        return False
    track = str(state.get('envelope_track') or '').strip().upper()
    family = str(state.get('editorial_motion_family') or '').strip().upper()
    return track == 'EDITORIAL_ENTRY' or family == 'DIRECTIONAL_ENTRY'


def _boundary_settle_time(event: dict, phase: dict) -> float:
    start = float(phase.get('start_seconds', 0.0))
    end = float(phase.get('end_seconds', start))
    settle = start

    # The semantic state authored at the phase boundary must finish arriving
    # before this can be called a settled destination.
    for state in _all_states(event):
        state_start = float(state.get('start_seconds', 0.0))
        if abs(state_start - start) > _BOUNDARY_TOLERANCE_SECONDS:
            continue
        duration = max(0.0, float(state.get('transition_duration_seconds') or 0.0))
        settle = max(settle, state_start + duration)

    # A newly entering actor may begin a few frames *after* the semantic phase
    # boundary. The previous implementation only recognized an entry that had
    # already started at the boundary, so a short phase could be sampled in the
    # middle of APPEAR/DIRECTIONAL_ENTRY travel and falsely labelled "settled".
    # Treat the event's one entry preset as inbound when the event itself begins
    # in this phase. Retained actors in later phases are unaffected because their
    # event/entry start predates those phase boundaries.
    entry = event.get('preset_entry') or {}
    if entry:
        event_start = float(event.get('start_seconds', start))
        entry_start = float(entry.get('start_seconds', event_start))
        entry_duration = max(0.0, float(entry.get('duration_seconds') or 0.0))
        entry_end = entry_start + entry_duration
        begins_in_phase = (
            event_start >= start - _BOUNDARY_TOLERANCE_SECONDS
            and event_start < end - _EPS
        )
        overlaps_phase = entry_start < end - _EPS and entry_end > start + _EPS
        if begins_in_phase and overlaps_phase:
            settle = max(settle, entry_end)
        elif entry_start <= start + _BOUNDARY_TOLERANCE_SECONDS and entry_end > start:
            settle = max(settle, entry_end)

    # Round 3 directional entries are an independent composition envelope track.
    # Its origin/settle states can start shortly inside the phase (after the
    # semantic boundary and after an opacity pre-roll), so wait for the complete
    # inbound envelope. This does not exempt any trajectory from path/viewport
    # QA; it only prevents an in-flight frame from being called settled.
    for state in _all_states(event):
        if not _is_editorial_entry_state(state):
            continue
        state_start = float(state.get('start_seconds', 0.0))
        if state_start < start - _BOUNDARY_TOLERANCE_SECONDS or state_start >= end - _EPS:
            continue
        duration = max(0.0, float(state.get('transition_duration_seconds') or 0.0))
        settle = max(settle, state_start + duration)

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
    # it is an ordinary or independent sequence-envelope track. Inbound editorial
    # entry states have already contributed to ``settle`` and therefore do not
    # truncate the stable window here.
    for state in _all_states(event):
        state_start = float(state.get('start_seconds', stable_end))
        if state_start > settle + _EPS:
            stable_end = min(stable_end, state_start)

    return stable_end


def _stable_window(event: dict, phase: dict) -> tuple[float, float]:
    settle = _boundary_settle_time(event, phase)
    return settle, _stable_window_end(event, phase, settle)


def _sample_time(settle: float, stable_end: float) -> float | None:
    if stable_end <= settle + _SETTLE_PAD_SECONDS + _EPS:
        return None
    return min(
        stable_end - _EPS,
        max(settle + _SETTLE_PAD_SECONDS, (settle + stable_end) * 0.5),
    )


def install(qa_module) -> None:
    if getattr(qa_module, '_phase_settled_qa_contract_installed', False):
        return

    base_settled_rect = qa_module._settled_rect

    def phase_settled_rect(event: dict, phase: dict):
        start = float(phase.get('start_seconds', 0.0))
        end = float(phase.get('end_seconds', start))
        if end <= start + _EPS:
            return base_settled_rect(event), 0.0

        settle, stable_end = _stable_window(event, phase)
        sample_time = _sample_time(settle, stable_end)

        # Some intentionally short beats are entirely transition/handoff. They
        # have no static destination to certify. Motion-path and viewport QA still
        # inspect every visible intermediate frame, while pacing QA owns whether
        # the beat is editorially long enough.
        if sample_time is None:
            return base_settled_rect(event), 0.0

        state = qa_module._state(event, sample_time)
        if state is None:
            return base_settled_rect(event), 0.0
        return state[3], float(state[2])

    def phase_common_settled_rects(rows: list[dict], phase: dict):
        """Return simultaneous settled geometry at one shared phase timestamp.

        Pairwise overlap is a simultaneous physical property. Sampling actor A
        before its exit and actor B after its entry, then comparing those two
        rectangles, creates a synthetic composition that never exists on screen.
        When stable windows do not intersect, the phase is a transition-only
        handoff for pairwise purposes; the full swept-motion and viewport gates
        remain authoritative over every actual frame.
        """
        if not rows:
            return []
        windows = [_stable_window(event, phase) for event in rows]
        common_settle = max(start for start, _ in windows)
        common_end = min(end for _, end in windows)
        sample_time = _sample_time(common_settle, common_end)
        if sample_time is None:
            return []

        rects = []
        for event in rows:
            state = qa_module._state(event, sample_time)
            if state is None or float(state[2]) <= 0.05:
                continue
            rects.append((event, state[3]))
        return rects

    qa_module._phase_settled_rect = phase_settled_rect
    qa_module._phase_common_settled_rects = phase_common_settled_rects
    qa_module._phase_settled_qa_contract_installed = True
