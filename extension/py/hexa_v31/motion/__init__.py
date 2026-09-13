"""Motion layer and lazy compatibility exports for ``hexa_v31.motion``."""


def _build_final_motion_plan(*args, **kwargs):
    # Shipping motion imports the planning implementation directly through the
    # interaction director. Install editorial planner corrections before loading
    # that graph so production, preview and tests execute the same phase geometry
    # without eager package imports or circular initialization.
    from hexa_v31.planning import preset_story_planner as _preset_story_planner
    from hexa_v31.motion import beat_choreography as _beat_choreography
    from hexa_v31.planning.round2_editorial import install as _install_round2_editorial
    from hexa_v31.planning.same_scene_collision_recovery_contract import install as _install_same_scene_collision_recovery
    from hexa_v31.planning.final_cross_scene_handoff_recovery_contract import install as _install_final_cross_scene_handoff_recovery
    from hexa_v31.planning.phase_optimizer_contract import install as _install_phase_optimizer_contract
    from hexa_v31.planning.final_certification_phase_contract import install as _install_final_certification_phase_contract
    from hexa_v31.planning.phase_entry_contract import install as _install_phase_entry_contract
    _install_round2_editorial(_preset_story_planner)
    # Residual settled same-scene geometry is a planner responsibility, not a reason
    # to relax the hard collision gate. Install its bounded recovery immediately after
    # Round 2 so the shipping direct-import path matches the compatibility facade.
    _install_same_scene_collision_recovery(_preset_story_planner)
    # The primary cross-scene reconciler waits for a readable successor. A legal
    # fade/scale reveal may become materially visible earlier and still collide with
    # the outgoing root. Close only that residual interval with a bounded, fail-closed
    # visible-onset handoff search before final certification executes.
    _install_final_cross_scene_handoff_recovery(_preset_story_planner)
    # Round 2 owns the phase-authoring implementation. Install the compatibility
    # guard after it so every shipping caller protects that final phase authority
    # from legacy late optimizers before the final hard certification wrapper runs.
    _install_phase_optimizer_contract(_preset_story_planner)
    _install_final_certification_phase_contract(_preset_story_planner)
    # Beat choreography is a subordinate motion layer. Install the phase-aware
    # entry contract before importing the interaction director so directional
    # entry envelopes land on the certified semantic phase destination instead
    # of restoring stale card-wide rest geometry.
    _install_phase_entry_contract(_beat_choreography)

    from hexa_v31.interaction.director import build_interaction_motion_plan, finalize_interaction_motion_plan
    from hexa_v31.layout.source_integrity_finalizer import finalize_residual_source_integrity
    from hexa_v31.layout.reference_quality_finalizer import finalize_reference_density_topology
    from hexa_v31.layout.reference_geometry_finalizer import finalize_reference_geometry
    from hexa_v31.layout.reference_joint_fitter import finalize_reference_joint_geometry
    from hexa_v31.layout.perceptual_finalizer import finalize_perceptual_composition
    from hexa_v31.layout.reference_residual_closure import finalize_reference_residual_closure
    from hexa_v31.layout.reference_perceptual_residual import finalize_reference_perceptual_residual
    from hexa_v31.layout.reference_joint_interval_framing import finalize_reference_joint_interval_framing
    from hexa_v31.layout.reference_staggered_sequence_v2 import finalize_reference_staggered_sequence
    from hexa_v31.motion.pacing_qa import build_final_card_pacing_report
    from hexa_v31.motion.cross_card_editorial import finalize_cross_card_editorial

    plan = build_interaction_motion_plan(*args, **kwargs)
    fps = float(plan.get('fps') or kwargs.get('fps', 30.0))

    # Reconstruction residuals are source-survival context, not density/focus actors.
    # Normalize any generic support-slot enlargement/recomposition before P3/P4
    # evaluate density, otherwise sparse connectors/rings can become giant artifacts.
    source_integrity_stats = finalize_residual_source_integrity(plan, fps=fps)
    plan['source_integrity_finalizer'] = source_integrity_stats

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

    # Residual semantic/density pass is deliberately late. It only sees
    # deficits that survived topology, geometry, cohort fitting and normal
    # perceptual composition, so it cannot steal opportunities from P1/P2.
    residual_stats = finalize_reference_residual_closure(plan, fps=fps)
    plan['reference_residual_closure_finalizer'] = residual_stats

    # Final card-level perceptual closer is narrower still: sustained sparse
    # cards only, no partitions and no center-travel actors. This catches the
    # single/composite-root case that pair/cohort fitting cannot solve and
    # records any remaining residual cards explicitly instead of hiding them
    # behind a generic changed/pass flag.
    perceptual_residual_stats = finalize_reference_perceptual_residual(plan, fps=fps)
    plan['reference_perceptual_residual_finalizer'] = perceptual_residual_stats

    # P3/P4 cooperation: when a legitimate simultaneous semantic cohort remains
    # sparse, temporarily frame the already-settled roots on an independent
    # DENSITY_FRAME track and restore before the next reveal/handoff. No permanent
    # rest geometry, partition authority or P2 entry timing is changed.
    joint_interval_stats = finalize_reference_joint_interval_framing(plan, fps=fps)
    plan['reference_joint_interval_framing_finalizer'] = joint_interval_stats

    stagger_stats = finalize_reference_staggered_sequence(plan, fps=fps)
    plan['reference_staggered_sequence_finalizer'] = stagger_stats

    # Round 3 cross-card choreography deliberately runs after every reference geometry
    # finalizer. Motion adapts to the final certified footprint; geometry is never shrunk
    # or relocated merely to satisfy a later handoff request.
    cross_card_editorial_stats = finalize_cross_card_editorial(plan, fps=fps)
    plan['cross_card_editorial_finalizer'] = cross_card_editorial_stats
    from hexa_v31.planning.final_density_recovery import recover_final_density
    final_density_recovery = recover_final_density(plan, fps=fps)
    plan['final_density_recovery'] = final_density_recovery

    pacing_stats = build_final_card_pacing_report(plan)
    plan['final_card_pacing_qa'] = pacing_stats

    if (
        source_integrity_stats.get('changed')
        or topology_stats.get('changed')
        or geometry_stats.get('changed')
        or joint_stats.get('changed')
        or perceptual_stats.get('changed')
        or residual_stats.get('changed')
        or perceptual_residual_stats.get('changed')
        or joint_interval_stats.get('changed')
        or stagger_stats.get('changed')
        or cross_card_editorial_stats.get('changed')
        or final_density_recovery.get('repaired_event_ids')
    ):
        # Final reference passes mutate only already-certified source-backed
        # state. Re-run the same lifetime/physical authority once so the final
        # immutable barrier describes the exact pixels consumed by the renderer.
        plan = finalize_interaction_motion_plan(plan, fps=fps)
        plan['source_integrity_finalizer'] = source_integrity_stats
        plan['reference_density_topology_finalizer'] = topology_stats
        plan['reference_geometry_finalizer'] = geometry_stats
        plan['reference_joint_geometry_finalizer'] = joint_stats
        plan['perceptual_composition_finalizer'] = perceptual_stats
        plan['reference_residual_closure_finalizer'] = residual_stats
        plan['reference_perceptual_residual_finalizer'] = perceptual_residual_stats
        plan['reference_joint_interval_framing_finalizer'] = joint_interval_stats
        plan['reference_staggered_sequence_finalizer'] = stagger_stats
        plan['cross_card_editorial_finalizer'] = cross_card_editorial_stats
        plan['final_density_recovery'] = final_density_recovery
        plan['final_card_pacing_qa'] = pacing_stats
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
