"""Install source-scene ownership and pixel-only boundary holds on preview renderers."""
from __future__ import annotations


def _materialize_render_map(render_map):
    mapped = dict(render_map or {})
    rows = []
    for source in (render_map or {}).get('events') or []:
        event = dict(source)
        physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
        physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
        carrier_start = event.get('scene_boundary_carrier_start_seconds')
        carrier_end = event.get('scene_boundary_carrier_end_seconds')
        event['certified_physical_start_seconds'] = physical_start
        event['certified_physical_end_seconds'] = physical_end
        if carrier_start is not None:
            event['physical_start_seconds'] = min(physical_start, float(carrier_start))
        if carrier_end is not None:
            event['physical_end_seconds'] = max(physical_end, float(carrier_end))
        rows.append(event)
    mapped['events'] = rows
    return mapped


def install(impl) -> None:
    if getattr(impl, '_scene_ownership_contract_installed', False):
        return
    base_state = impl._event_state
    base_preview = impl.render_preview
    base_production = impl.render_production_mp4

    def event_state(event: dict, t: float):
        physical_start = float(event.get('certified_physical_start_seconds', event.get('physical_start_seconds', event.get('start_seconds', 0.0))))
        physical_end = float(event.get('certified_physical_end_seconds', event.get('physical_end_seconds', event.get('end_seconds', physical_start))))
        ownership_start = float(event.get('scene_ownership_start_seconds', physical_start))
        ownership_end = float(event.get('scene_ownership_end_seconds', physical_end))
        if t < ownership_start - 1e-9 or t >= ownership_end - 1e-9:
            return None
        carrier_start = event.get('scene_boundary_carrier_start_seconds')
        carrier_end = event.get('scene_boundary_carrier_end_seconds')
        carrier_sample = event.get('scene_boundary_carrier_sample_seconds')
        if carrier_start is not None and carrier_end is not None and carrier_sample is not None:
            if float(carrier_start) - 1e-9 <= t < float(carrier_end) - 1e-9:
                sampled = dict(event)
                sampled['physical_start_seconds'] = physical_start
                sampled['physical_end_seconds'] = physical_end
                return base_state(sampled, float(carrier_sample))
        if t < physical_start - 1e-9 or t >= physical_end - 1e-9:
            return None
        return base_state(event, t)

    def render_preview(edit_map, motion_plan, vision_results, audio_path, out_dir, width=426, height=240, fps=30.0, logger=None, text_plan=None):
        return base_preview(_materialize_render_map(edit_map), motion_plan, vision_results, audio_path, out_dir, width=width, height=height, fps=fps, logger=logger, text_plan=text_plan)

    def render_production_mp4(edit_map, motion_plan, vision_results, audio_path, output_path, width=1920, height=1080, fps=30.0, logger=None):
        return base_production(_materialize_render_map(edit_map), motion_plan, vision_results, audio_path, output_path, width=width, height=height, fps=fps, logger=logger)

    impl._event_state = event_state
    impl.render_preview = render_preview
    impl.render_production_mp4 = render_production_mp4
    impl._scene_ownership_contract_installed = True
