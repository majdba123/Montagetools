"""Install the final source-scene ownership gate on renderer state evaluation."""
from __future__ import annotations


def install(impl) -> None:
    if getattr(impl, '_scene_ownership_contract_installed', False):
        return
    base = impl._event_state

    def event_state(event: dict, t: float):
        physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
        physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
        ownership_start = float(event.get('scene_ownership_start_seconds', physical_start))
        ownership_end = float(event.get('scene_ownership_end_seconds', physical_end))
        if t < ownership_start - 1e-9 or t >= ownership_end - 1e-9:
            return None
        return base(event, t)

    impl._event_state = event_state
    impl._scene_ownership_contract_installed = True
