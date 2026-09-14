"""Carry certified pixel-only scene handoffs through Premiere completeness QA.

This contract does not alter planner/render event identity, physical lifetimes, or source
resolution. It only makes the integration completeness gate use the same certified
boundary-carrier coverage authority as the final interaction barrier.
"""
from __future__ import annotations


def install(impl) -> None:
    if getattr(impl, '_scene_ownership_premiere_contract_installed', False):
        return

    base = impl.planner_render_map_completeness_qa

    def planner_render_map_completeness_qa(motion_plan: dict, mapped_events: list[dict], fps: float = 30.0) -> dict:
        from hexa_v31.interaction.scene_ownership_contract import _coverage_with_boundary_carriers
        from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa

        report = dict(base(motion_plan, mapped_events, fps=fps))
        coverage_plan = dict(motion_plan)
        coverage_plan['events'] = mapped_events
        coverage = _coverage_with_boundary_carriers(
            coverage_plan, fps, visual_timeline_coverage_qa
        )
        report['visual_timeline_coverage_pass'] = bool(coverage.get('pass'))
        report['visual_timeline_coverage_qa'] = coverage

        structural_fail = bool(
            report.get('duplicate_planner_event_ids')
            or report.get('duplicate_mapped_event_ids')
            or report.get('missing_event_ids')
            or report.get('unexpected_event_ids')
            or report.get('physical_lifetime_mismatches')
            or report.get('missing_source_events')
        )
        report['pass'] = (not structural_fail) and bool(coverage.get('pass'))
        report['coverage_authority'] = 'FINAL_CERTIFIED_SCENE_HANDOFF_COVERAGE'
        return report

    impl.planner_render_map_completeness_qa = planner_render_map_completeness_qa
    impl._scene_ownership_premiere_contract_installed = True
