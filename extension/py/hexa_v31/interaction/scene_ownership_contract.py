"""Install source-scene pixel ownership at the interaction finalization barrier.

Pixel ownership is intentionally independent from semantic/action timing.  The
contract compiles renderer-visible source ownership around the unchanged interaction
plan, then seals the resulting ownership metadata into the final timing digest.
"""
from __future__ import annotations


def install(impl) -> None:
    if getattr(impl, '_scene_ownership_contract_installed', False):
        return

    from hexa_v31.composition_qa import composition_plan_qa
    from hexa_v31.planning.scene_ownership import compile_scene_ownership
    from hexa_v31.planning.scene_ownership_qa import scene_ownership_qa
    from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa

    ownership_fields = (
        'scene_ownership_start_seconds', 'scene_ownership_end_seconds',
        'scene_ownership_authority', 'scene_ownership_index',
        'scene_ownership_recovery_authority',
    )
    impl._FINAL_TIMING_FIELDS = tuple(dict.fromkeys((*impl._FINAL_TIMING_FIELDS, *ownership_fields)))

    def finalize_interaction_motion_plan(plan: dict, fps: float = 30.0) -> dict:
        from hexa_v31.planning.preset_story_planner import (
            _finalize_visual_lifetimes,
            _final_physical_certification,
        )

        events = plan.get('events') or []
        cards = plan.get('visual_cards') or {'cards': []}
        lifetime = _finalize_visual_lifetimes(events, cards, fps)

        ownership_before = compile_scene_ownership(plan, fps=fps)
        if not ownership_before.get('pass'):
            raise ValueError(
                'SCENE_OWNERSHIP_COMPILATION_FAILED: '
                + ' | '.join(ownership_before.get('failures') or [])[:2000]
            )

        certification = _final_physical_certification(events, cards, fps)

        # Physical certification/recovery may change carriers. Recompile from the
        # exact final carrier state so QA and renderer consume one ownership truth.
        ownership_compiler = compile_scene_ownership(plan, fps=fps)
        if not ownership_compiler.get('pass'):
            raise ValueError(
                'FINAL_SCENE_OWNERSHIP_COMPILATION_FAILED: '
                + ' | '.join(ownership_compiler.get('failures') or [])[:2000]
            )
        ownership_qa = scene_ownership_qa(plan, fps=fps)
        if not ownership_qa.get('pass'):
            raise ValueError(
                'FINAL_SCENE_OWNERSHIP_QA_FAILED: '
                + ' | '.join(ownership_qa.get('failures') or [])[:2000]
            )
        post_ownership_composition = composition_plan_qa(plan)
        if not post_ownership_composition.get('pass'):
            raise ValueError(
                'FINAL_SCENE_OWNERSHIP_COMPOSITION_QA_FAILED: '
                + ' | '.join(post_ownership_composition.get('failures') or [])[:2000]
            )

        coverage = visual_timeline_coverage_qa(plan, fps=fps)
        if not coverage.get('pass'):
            raise ValueError(
                'FINAL_INTERACTION_LIFETIME_RECONCILIATION_FAILED: '
                + ' | '.join(coverage.get('failures') or [])[:2000]
            )

        plan['final_lifetime_commit'] = lifetime
        plan['final_physical_certification'] = certification
        plan['scene_ownership_compiler'] = ownership_compiler
        plan['final_scene_ownership_qa'] = ownership_qa
        plan['final_visual_timeline_coverage_qa'] = coverage
        plan['final_semantic_timing_composition_qa'] = post_ownership_composition
        timing_sha256 = impl._final_timing_sha256(plan)
        plan['finalization_barrier'] = {
            'authority': 'POST_INTERACTION_FINAL_LIFETIME_PHYSICAL_AND_SCENE_OWNERSHIP_CERTIFICATION',
            'timing_sha256': timing_sha256,
            'immutable_timing_fields': list(impl._FINAL_TIMING_FIELDS),
            'pass': True,
        }
        return plan

    def build_interaction_motion_plan(
        plan: dict,
        alignment: dict,
        vision_results: list[dict],
        rules_path,
        reference_path,
        *,
        fps: float = 30.0,
        logger=None,
        calibration: dict | None = None,
    ):
        from hexa_v31.motion.motion import build_motion_plan as base_build_motion_plan

        base = base_build_motion_plan(
            plan, alignment, vision_results, rules_path, reference_path,
            fps=fps, logger=logger, calibration=calibration,
        )
        ownership = compile_scene_ownership(base, fps=fps)
        if not ownership.get('pass'):
            raise ValueError(
                'BASE_SCENE_OWNERSHIP_COMPILATION_FAILED: '
                + ' | '.join(ownership.get('failures') or [])[:2000]
            )
        interacted = impl.apply_interaction_director(
            base, plan, alignment, fps=fps, logger=logger
        )
        return finalize_interaction_motion_plan(interacted, fps=fps)

    impl.finalize_interaction_motion_plan = finalize_interaction_motion_plan
    impl.build_interaction_motion_plan = build_interaction_motion_plan
    impl._scene_ownership_contract_installed = True
