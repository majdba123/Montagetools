"""Round 3 hard-cut readability delivery for installed appearance presets."""
from __future__ import annotations


def install(impl) -> None:
    if getattr(impl, '_round3_readability_installed', False):
        return
    base = impl._preset_event_state

    def preset_event_state(event: dict, t: float):
        floor = max(0.0, min(1.0, float(event.get('entry_curve_progress_floor') or 0.0)))
        entry = event.get('preset_entry') or {}
        name = str(entry.get('name') or '')
        if floor > 0.0 and name:
            definition = impl._preset_def(name)
            if definition.get('family') == 'APPEARANCE':
                start = float(entry.get('start_seconds', event.get('start_seconds', 0.0)))
                duration = float(entry.get('duration_seconds') or definition.get('duration_seconds') or 0.8)
                q = max(0.0, min(1.0, (t - start) / max(1e-6, duration)))
                if q < floor:
                    event = dict(event)
                    virtual_entry = dict(entry)
                    # Per-evaluation virtual start reproduces q=max(q,floor) exactly;
                    # serialized semantic/preset timing and physical lifetime never move.
                    virtual_entry['start_seconds'] = float(t) - floor * duration
                    event['preset_entry'] = virtual_entry
        return base(event, t)

    impl._preset_event_state = preset_event_state
    impl._round3_readability_installed = True
