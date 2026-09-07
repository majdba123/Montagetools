"""Motion layer and lazy compatibility exports for ``hexa_v31.motion``."""


def _build_final_motion_plan(*args, **kwargs):
    from hexa_v31.interaction.director import build_interaction_motion_plan, finalize_interaction_motion_plan
    from hexa_v31.layout.perceptual_finalizer import finalize_perceptual_composition

    plan = build_interaction_motion_plan(*args, **kwargs)
    fps = float(kwargs.get('fps', 30.0))
    stats = finalize_perceptual_composition(plan, fps=fps)
    plan['perceptual_composition_finalizer'] = stats
    if stats.get('changed'):
        # The interaction director already sealed a valid timing plan. Geometry
        # and composition-state amplitude are strengthened only after full
        # lifetime collision checks, then the same final lifetime/physical
        # authority is rerun so diagnostics and certification describe the
        # exact pixels the renderer will consume.
        plan = finalize_interaction_motion_plan(plan, fps=fps)
        plan['perceptual_composition_finalizer'] = stats
    return plan


def __getattr__(name):
    if name == 'build_motion_plan':
        value = _build_final_motion_plan
    else:
        from importlib import import_module
        implementation = import_module(__name__ + '.motion')
        value = getattr(implementation, name)
    globals()[name] = value
    return value
