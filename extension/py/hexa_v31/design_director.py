"""Backward-compatible module shim; implementation lives in hexa_v31.story.design_director."""
from __future__ import annotations

import copy

from .story import design_director as _implementation
from .interaction.director import assert_final_motion_plan_immutable

# Re-export the implementation surface first, then override the public title
# planner with a post-certification immutability guard.  The underlying title
# planner has a legacy fallback that may rebalance live motion geometry when no
# title slot is available.  That repair is valid only before Final Motion Plan
# certification; after the barrier, typography is a read-only consumer.
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})


def build_title_plan(package, alignment, vision_results, motion, alignment_report=None):
    """Build titles without allowing post-certification motion mutation.

    A sealed motion plan is probed on a deep copy. If the legacy title-slot
    fallback would move certified geometry, retry without deferred-slot
    rebalancing so only already-safe title slots may be used. The live plan is
    asserted immutable before returning.
    """
    barrier = motion.get('finalization_barrier') or {}
    if not barrier.get('timing_sha256'):
        return _implementation.build_title_plan(
            package, alignment, vision_results, motion, alignment_report
        )

    probe_motion = copy.deepcopy(motion)
    candidate = _implementation.build_title_plan(
        package, alignment, vision_results, probe_motion, alignment_report
    )
    try:
        assert_final_motion_plan_immutable(probe_motion)
    except ValueError as exc:
        if 'FINAL_MOTION_PLAN_MUTATED_AFTER_CERTIFICATION' not in str(exc):
            raise
        # A deferred title is optional presentation support. It must never
        # rewrite certified P1/P2/P3/P4 geometry. Removing only the deferred
        # fallback preserves titles that fit an already-safe slot.
        safe_report = copy.deepcopy(alignment_report or {})
        safe_report['deferred_anchors'] = []
        candidate = _implementation.build_title_plan(
            package, alignment, vision_results, motion, safe_report
        )
        if isinstance(candidate, dict):
            candidate['post_seal_geometry_rebalance_suppressed'] = True
    assert_final_motion_plan_immutable(motion)
    return candidate
