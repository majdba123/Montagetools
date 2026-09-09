"""Motion layer and lazy compatibility exports for ``hexa_v31.motion``."""


def _build_final_motion_plan(*args, **kwargs):
    from hexa_v31.interaction.director import build_interaction_motion_plan, finalize_interaction_motion_plan
    from hexa_v31.layout.reference_quality_finalizer import finalize_reference_density_topology
    from hexa_v31.layout.reference_geometry_finalizer import finalize_reference_geometry
    from hexa_v31.layout.reference_joint_fitter import finalize_reference_joint_geometry
    from hexa_v31.layout.perceptual_finalizer import finalize_perceptual_composition
    from hexa_v31.layout.reference_residual_closure import finalize_reference_residual_closure

    plan = build_interaction_motion_plan(*args, **kwargs)
    fps = float(plan.get('fps') or kwargs.get('fps', 30.0))

    topology_stats = finalize_reference_density_topology(plan, fps=fps)
    plan['reference_density_topology_finalizer'] = topology_stats

    # Reserve semantic cohort space before independent actors consume all
    # available slots. Every later stage retains the same full-plan QA.
    card_allocation = finalize_reference_joint_geometry(plan, fps=fps)

    geometry_stats = finalize_reference_geometry(plan, fps=fps)
    plan['reference_geometry_finalizer'] = geometry_stats

    joint_stats = finalize_reference_joint_geometry(plan, fps=fps)
    joint_stats['initial_card_allocation'] = card_allocation
    joint_stats['changed'] = bool(joint_stats['changed'] or card_allocation['changed'])
    plan['reference_joint_geometry_finalizer'] = joint_stats

    perceptual_stats = finalize_perceptual_composition(plan, fps=fps)
    plan['perceptual_composition_finalizer'] = perceptual_stats

    # Final residual pass is deliberately last. It only sees deficits that
    # survived topology, geometry, cohort fitting and perceptual composition,
    # so it cannot steal opportunities from the established P1/P2 authorities.
    residual_stats = finalize_reference_residual_closure(plan, fps=fps)
    plan['reference_residual_closure_finalizer'] = residual_stats

    if (
        topology_stats.get('changed')
        or geometry_stats.get('changed')
        or joint_stats.get('changed')
        or perceptual_stats.get('changed')
        or residual_stats.get('changed')
    ):
        # Final reference passes mutate only already-certified source-backed
        # state. Re-run the same lifetime/physical authority once so the final
        # immutable barrier describes the exact pixels consumed by the renderer.
        plan = finalize_interaction_motion_plan(plan, fps=fps)
        plan['reference_density_topology_finalizer'] = topology_stats
        plan['reference_geometry_finalizer'] = geometry_stats
        plan['reference_joint_geometry_finalizer'] = joint_stats
        plan['perceptual_composition_finalizer'] = perceptual_stats
        plan['reference_residual_closure_finalizer'] = residual_stats
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
