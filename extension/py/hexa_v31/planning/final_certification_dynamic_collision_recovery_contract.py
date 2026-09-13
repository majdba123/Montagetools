from __future__ import annotations

import copy
import re

from hexa_v31.planning.final_cross_scene_handoff_recovery_contract import (
    _is_independent_root,
    _retire_outgoing,
    _scene_id,
    _shift_incoming,
    _source_order,
)

_AUTHORITY = 'FINAL_CERTIFICATION_DYNAMIC_CROSS_SCENE_HANDOFF_RECOVERY'
_DYNAMIC_RE = re.compile(
    r'(?P<card>VCARD_[^@:\\s]+)@(?P<time>[0-9]+(?:\\.[0-9]+)?)s:\\s*'
    r'motion-path overlap\\s+(?P<a>\\S+)\\s+x\\s+(?P<b>\\S+)='
)


def _restore_all(events, snapshots):
    for live, snapshot in zip(events, snapshots):
        live.clear()
        live.update(copy.deepcopy(snapshot))


def _parse_dynamic_failure(message):
    match = _DYNAMIC_RE.search(str(message))
    if not match:
        return None
    return {
        'card_id': match.group('card'),
        'time_seconds': float(match.group('time')),
        'event_a': match.group('a'),
        'event_b': match.group('b'),
    }


def install(impl):
    if getattr(impl, '_final_certification_dynamic_collision_recovery_installed', False):
        return

    base = impl._final_physical_certification

    def wrapped(events, cards, fps):
        try:
            return base(events, cards, fps)
        except ValueError as original_exc:
            failure = _parse_dynamic_failure(str(original_exc))
            if failure is None:
                raise

        by_id = {str(event.get('event_id') or ''): event for event in events}
        a = by_id.get(failure['event_a'])
        b = by_id.get(failure['event_b'])
        if a is None or b is None or _scene_id(a) == _scene_id(b):
            raise original_exc
        if not (_is_independent_root(a) and _is_independent_root(b)):
            raise original_exc

        if _source_order(a) < _source_order(b) - 1e-6:
            outgoing_id, incoming_id = str(a.get('event_id')), str(b.get('event_id'))
        elif _source_order(b) < _source_order(a) - 1e-6:
            outgoing_id, incoming_id = str(b.get('event_id')), str(a.get('event_id'))
        else:
            raise original_exc

        from hexa_v31.composition_qa import _state

        snapshots = [copy.deepcopy(event) for event in events]
        step = 1.0 / max(1.0, float(fps))
        max_sync_frames = 6
        max_lead_frames = max(6, int(round(float(fps) * 0.8)))

        for delay_frames in range(max_sync_frames + 1):
            for lead_frames in range(1, max_lead_frames + 1):
                _restore_all(events, snapshots)
                live_by_id = {str(event.get('event_id') or ''): event for event in events}
                outgoing = live_by_id[outgoing_id]
                incoming = live_by_id[incoming_id]

                if not _shift_incoming(impl, incoming, delay_frames, fps, max_sync_frames):
                    continue

                handoff_end = (
                    float(failure['time_seconds'])
                    + delay_frames * step
                    - lead_frames * step
                )
                if not _retire_outgoing(impl, _state, outgoing, handoff_end, fps):
                    continue

                outgoing['final_certification_dynamic_recovery_authority'] = _AUTHORITY
                incoming['final_certification_dynamic_recovery_authority'] = _AUTHORITY
                try:
                    result = base(events, cards, fps)
                except ValueError:
                    continue

                if result and result.get('pass'):
                    repairs = list(result.get('repairs') or [])
                    repairs.append({
                        'type': 'FINAL_CERTIFICATION_DYNAMIC_CROSS_SCENE_HANDOFF',
                        'authority': _AUTHORITY,
                        'visual_card_id': failure['card_id'],
                        'outgoing_event_id': outgoing_id,
                        'incoming_event_id': incoming_id,
                        'handoff_seconds': round(float(handoff_end), 6),
                        'incoming_delay_frames': int(delay_frames),
                        'lead_frames': int(lead_frames),
                    })
                    result['repairs'] = repairs
                    return result

        _restore_all(events, snapshots)
        raise original_exc

    wrapped.__name__ = base.__name__
    wrapped.__doc__ = base.__doc__
    impl._final_physical_certification = wrapped
    impl._final_certification_dynamic_collision_recovery_installed = True
