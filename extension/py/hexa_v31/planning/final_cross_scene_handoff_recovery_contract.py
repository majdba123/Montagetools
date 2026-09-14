"""Fail-closed recovery for residual cross-scene carrier path collisions.

The primary final handoff reconciler intentionally waits for a readable successor
before retiring an outgoing source. A legal fade/scale reveal can, however, become
visually present before it crosses the stricter readability threshold. When the two
independent source roots share the same composition slot, that short entry interval
can still trip canonical swept-motion collision QA.

This contract closes only that gap. It never relaxes collision thresholds, suppresses
actors, changes narration anchors, or moves protected partition/residual geometry.
For independent ROOT_ATOMIC actors from different source scenes it performs a bounded
search that may delay the incoming reveal within the existing six-frame sync budget,
then retires the outgoing carrier immediately before the successor becomes materially
visible. Every candidate is accepted only when canonical card/global motion QA proves
that the triggering pair is gone, total conflict count strictly decreases, and no new
conflict pair is introduced.
"""
from __future__ import annotations

import copy
import math

_AUTHORITY = 'FINAL_CROSS_SCENE_VISIBLE_ONSET_HANDOFF_RECOVERY'
_EPS = 1e-9


def _event_id(event: dict) -> str:
    return str(event.get('event_id') or '')


def _scene_id(event: dict) -> str:
    return str(event.get('scene_id') or '')


def _is_independent_root(event: dict) -> bool:
    return (
        str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and not event.get('partition_group_id')
    )


def _source_order(event: dict) -> float:
    return float(
        event.get(
            'source_scene_start_seconds',
            event.get(
                'perceptual_hit_seconds',
                event.get('physical_start_seconds', event.get('start_seconds', 0.0)),
            ),
        )
    )


def _pair(row: dict) -> tuple[str, str]:
    return tuple(sorted((str(row.get('event_a') or ''), str(row.get('event_b') or ''))))


def _restore(event: dict, snapshot: dict) -> None:
    event.clear()
    event.update(copy.deepcopy(snapshot))


def _recompile_motion(impl, event: dict) -> None:
    intervals, motion_start, motion_end = impl._compile_final_motion_intervals(event)
    event['motion_intervals'] = intervals
    event['motion_start_seconds'] = round(float(motion_start), 6)
    event['motion_end_seconds'] = round(float(motion_end), 6)


def _shift_incoming(impl, event: dict, delay_frames: int, fps: float, max_sync_frames: int) -> bool:
    if delay_frames <= 0:
        return True
    if not _is_independent_root(event):
        return False
    entry = event.get('preset_entry')
    if not entry:
        return False

    step = 1.0 / max(1.0, float(fps))
    delta = float(delay_frames) * step
    name = str(entry.get('name') or 'APPEAR_HIGH_SCALE')
    duration = float(entry.get('duration_seconds') or impl.preset_duration(name))
    new_entry_start = float(entry.get('start_seconds', event.get('start_seconds', 0.0))) + delta
    impact = new_entry_start + impl._entry_fraction({'preset_entry': {'name': name}}) * duration
    anchor = float(event.get('perceptual_hit_seconds', impact))
    if abs(impact - anchor) * float(fps) > float(max_sync_frames) + 1e-6:
        return False

    old_start = float(event.get('start_seconds', new_entry_start - delta))
    prior_physical_start = float(event.get('physical_start_seconds', old_start))
    event['start_seconds'] = round(max(old_start + delta, new_entry_start), 6)
    entry['start_seconds'] = round(new_entry_start, 6)
    event['physical_start_seconds'] = round(
        max(prior_physical_start + delta, float(event['start_seconds'])), 6
    )
    event['visibility_interval_seconds'] = [
        float(event['physical_start_seconds']),
        float(event.get('physical_end_seconds', event.get('end_seconds', event['start_seconds']))),
    ]
    event['final_cross_source_incoming_delay_frames'] = int(delay_frames)
    event['final_cross_source_incoming_delay_authority'] = _AUTHORITY
    _recompile_motion(impl, event)
    return True


def _first_materially_visible_frame(state_fn, event: dict, start: float, end: float, fps: float) -> float | None:
    """Return first frame where the incoming carrier is actually visible.

    Canonical collision QA ignores effectively invisible states; using the same
    material-opacity boundary lets us hand off at visual onset rather than waiting
    for the stronger readability threshold used by the primary reconciler.
    """
    first = max(0, int(math.floor(float(start) * float(fps))))
    last = max(first, int(math.ceil(float(end) * float(fps))))
    for frame in range(first, last + 1):
        t = frame / float(fps)
        state = state_fn(event, t)
        if state is not None and float(state[2]) > 0.05:
            return t
    return None


def _retire_outgoing(impl, state_fn, event: dict, handoff_end: float, fps: float) -> bool:
    """Retire one independent root without touching its semantic anchor."""
    if not _is_independent_root(event):
        return False

    step = 1.0 / max(1.0, float(fps))
    physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
    current_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
    new_end = min(float(handoff_end), current_end)
    if new_end <= physical_start + step * 0.5:
        return False
    if new_end >= current_end - step * 0.25:
        return False

    # Never clip a voice-owned semantic result before its narration anchor.
    anchor = float(event.get('perceptual_hit_seconds', event.get('start_seconds', physical_start)))
    if str(event.get('perceptual_hit_source') or '').upper() == 'VOICE_TRIGGER' and anchor >= new_end - step * 0.25:
        return False

    duration = float(impl.preset_duration('DISAPPEAR_DOWN_SCALE'))
    visible_fraction = float(
        impl._motion_interval_effective_fraction('EXIT', 'DISAPPEAR_DOWN_SCALE')
    )
    visible_duration = duration * visible_fraction
    exit_start = max(physical_start, new_end - visible_duration)

    # Optional within-frame actions are subordinate to carrier survival. If they
    # overlap the emergency exit they are removed rather than allowed to compete
    # for the transform track.
    event['preset_actions'] = []
    event['preset_exit'] = {
        'name': 'DISAPPEAR_DOWN_SCALE',
        'start_seconds': round(exit_start, 6),
        'duration_seconds': duration,
        'authority': _AUTHORITY,
    }
    event['disappearance_method'] = 'PRESET_DISAPPEARANCE'
    event['end_seconds'] = round(new_end, 6)
    event['physical_end_seconds'] = round(new_end, 6)
    event['visibility_interval_seconds'] = [round(physical_start, 6), round(new_end, 6)]
    event['final_cross_source_handoff_authority'] = _AUTHORITY
    event['final_cross_source_motion_fallback'] = 'OPTIONAL_MOTION_REMOVED_FOR_VISIBLE_ONSET_HANDOFF'
    _recompile_motion(impl, event)

    # If the outgoing semantic anchor still lies inside the shortened carrier,
    # require it to remain materially visible there.
    if anchor < new_end - step * 0.25:
        state = state_fn(event, anchor)
        if state is None or float(state[2]) <= 0.22:
            return False
    return True


def install(impl) -> None:
    if getattr(impl, '_final_cross_scene_handoff_recovery_contract_installed', False):
        return

    base_reconcile = impl._reconcile_final_partition_handoffs

    def reconcile_final_partition_handoffs(events, cards, fps):
        stats = base_reconcile(events, cards, fps)

        from hexa_v31.composition_qa import _state, card_motion_conflicts

        active = [event for event in events if not event.get('suppressed_by_card_density')]
        card_rows = list((cards or {}).get('cards') or [])
        step = 1.0 / max(1.0, float(fps))
        max_sync_frames = 6
        recovery = {
            'authority': _AUTHORITY,
            'candidate_conflict_count': 0,
            'candidate_schedules_evaluated': 0,
            'handoffs_committed': 0,
            'handoffs_rejected': 0,
            'incoming_delay_frames': [],
            'retired_event_ids': [],
            'repairs': [],
        }

        if not active or not card_rows:
            stats['visible_onset_recovery'] = recovery
            return stats

        global_start = min(float(e.get('physical_start_seconds', e.get('start_seconds', 0.0))) for e in active)
        global_end = max(float(e.get('physical_end_seconds', e.get('end_seconds', 0.0))) for e in active)

        # Each accepted mutation strictly reduces the canonical conflict set, so
        # this loop is bounded by the number of possible actor pairs.
        max_passes = max(1, len(active) * 2)
        for _ in range(max_passes):
            committed = False
            for card in card_rows:
                card_start = float(card.get('start_seconds', 0.0))
                card_end = float(card.get('end_seconds', card_start))
                card_id = str(card.get('card_id') or '')
                local = [
                    event for event in active
                    if str(event.get('visual_card_id') or '') == card_id
                    and float(event.get('physical_start_seconds', event.get('start_seconds', 0.0))) < card_end
                    and float(event.get('physical_end_seconds', event.get('end_seconds', 0.0))) > card_start
                ]
                if len(local) < 2:
                    continue

                before_rows = card_motion_conflicts(local, card_start, card_end, fps)
                if not before_rows:
                    continue
                before_pairs = {_pair(row) for row in before_rows}
                local_by_id = {_event_id(event): event for event in local}

                for row in sorted(
                    before_rows,
                    key=lambda item: (
                        float(item.get('time_seconds', 0.0)),
                        str(item.get('event_a') or ''),
                        str(item.get('event_b') or ''),
                    ),
                ):
                    a = local_by_id.get(str(row.get('event_a') or ''))
                    b = local_by_id.get(str(row.get('event_b') or ''))
                    if a is None or b is None:
                        continue
                    if _scene_id(a) == _scene_id(b):
                        continue
                    if not (_is_independent_root(a) and _is_independent_root(b)):
                        continue

                    if _source_order(a) < _source_order(b) - 1e-6:
                        outgoing, incoming = a, b
                    elif _source_order(b) < _source_order(a) - 1e-6:
                        outgoing, incoming = b, a
                    else:
                        continue

                    recovery['candidate_conflict_count'] += 1
                    trigger_pair = _pair(row)
                    outgoing_snapshot = copy.deepcopy(outgoing)
                    incoming_snapshot = copy.deepcopy(incoming)
                    global_before_rows = card_motion_conflicts(active, global_start, global_end, fps)
                    global_before_pairs = {_pair(item) for item in global_before_rows}

                    for delay_frames in range(max_sync_frames + 1):
                        recovery['candidate_schedules_evaluated'] += 1
                        _restore(outgoing, outgoing_snapshot)
                        _restore(incoming, incoming_snapshot)

                        if not _shift_incoming(impl, incoming, delay_frames, fps, max_sync_frames):
                            continue

                        incoming_start = max(
                            card_start,
                            float(incoming.get('physical_start_seconds', incoming.get('start_seconds', card_start))),
                        )
                        incoming_end = min(
                            card_end,
                            float(incoming.get('physical_end_seconds', incoming.get('end_seconds', card_end))),
                        )
                        visible_onset = _first_materially_visible_frame(
                            _state, incoming, incoming_start, incoming_end, fps
                        )
                        if visible_onset is None:
                            continue

                        # One-frame separation keeps the carriers temporally
                        # disjoint while making the handoff perceptually continuous.
                        handoff_end = visible_onset - step
                        if not _retire_outgoing(impl, _state, outgoing, handoff_end, fps):
                            continue

                        after_rows = card_motion_conflicts(local, card_start, card_end, fps)
                        after_pairs = {_pair(item) for item in after_rows}
                        if trigger_pair in after_pairs or len(after_rows) >= len(before_rows):
                            continue

                        global_after_rows = card_motion_conflicts(active, global_start, global_end, fps)
                        global_after_pairs = {_pair(item) for item in global_after_rows}
                        if global_after_pairs - global_before_pairs:
                            continue
                        if len(global_after_rows) >= len(global_before_rows):
                            continue

                        recovery['handoffs_committed'] += 1
                        recovery['incoming_delay_frames'].append(int(delay_frames))
                        recovery['retired_event_ids'].append(_event_id(outgoing))
                        recovery['repairs'].append({
                            'visual_card_id': card_id,
                            'outgoing_scene_id': _scene_id(outgoing),
                            'incoming_scene_id': _scene_id(incoming),
                            'outgoing_event_id': _event_id(outgoing),
                            'incoming_event_id': _event_id(incoming),
                            'handoff_seconds': round(float(handoff_end), 6),
                            'visible_onset_seconds': round(float(visible_onset), 6),
                            'incoming_delay_frames': int(delay_frames),
                            'trigger_conflict': dict(row),
                            'authority': _AUTHORITY,
                        })
                        committed = True
                        break

                    if committed:
                        break

                    _restore(outgoing, outgoing_snapshot)
                    _restore(incoming, incoming_snapshot)
                    recovery['handoffs_rejected'] += 1

                if committed:
                    break
            if not committed:
                break

        recovery['retired_event_ids'] = sorted(set(recovery['retired_event_ids']))
        stats['visible_onset_recovery'] = recovery
        stats['handoffs_committed'] = int(stats.get('handoffs_committed') or 0) + int(recovery['handoffs_committed'])
        stats['handoffs_rejected'] = int(stats.get('handoffs_rejected') or 0) + int(recovery['handoffs_rejected'])
        stats['candidate_conflict_count'] = int(stats.get('candidate_conflict_count') or 0) + int(recovery['candidate_conflict_count'])
        stats['candidate_schedules_evaluated'] = int(stats.get('candidate_schedules_evaluated') or 0) + int(recovery['candidate_schedules_evaluated'])
        stats.setdefault('repairs', []).extend(recovery['repairs'])
        return stats

    reconcile_final_partition_handoffs.__name__ = base_reconcile.__name__
    reconcile_final_partition_handoffs.__doc__ = base_reconcile.__doc__
    impl._reconcile_final_partition_handoffs = reconcile_final_partition_handoffs
    impl._final_cross_scene_handoff_recovery_contract_installed = True
