"""Backward-compatible module shim; implementation lives in hexa_v31.story.design_director."""
from __future__ import annotations

import copy

from .story import design_director as _implementation
from .interaction.director import assert_final_motion_plan_immutable
from .typography.premium import _display_copy_quality

# Re-export the implementation surface first, then override the public title
# planner with a post-certification immutability guard. The underlying title
# planner has a legacy fallback that may rebalance live motion geometry when no
# title slot is available. That repair is valid only before Final Motion Plan
# certification; after the barrier, typography is a read-only consumer.
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})


def _filter_title_copy(candidate):
    """Apply the same visual-copy quality gate to concept titles as support text.

    Exact narration provenance is necessary but not sufficient for good display copy:
    weak boundary glue and sentence-like fragments must not become large HERO text.
    Filtering is presentation-only and never mutates the Final Motion Plan.
    """
    if not isinstance(candidate, dict):
        return candidate
    kept=[];rejected=[]
    for event in candidate.get('events') or []:
        probe=dict(event)
        probe['typography_role']='HERO'
        ok,reason=_display_copy_quality(probe)
        if ok:
            kept.append(event)
        else:
            rejected.append({'scene_id':event.get('scene_id'),'visual_card_id':event.get('visual_card_id'),
                             'text':event.get('text'),'reason':reason,'stage':'PREMIUM_HERO_COPY_GATE'})
    out=dict(candidate)
    out['events']=kept
    out['text_event_count']=len(kept)
    out['premium_title_copy_rejections']=rejected
    out['premium_title_copy_gate']=True
    qa=dict(out.get('title_qa') or {})
    if 'viewer_title_count' in qa:qa['viewer_title_count']=len(kept)
    out['title_qa']=qa
    return out


def build_title_plan(package, alignment, vision_results, motion, alignment_report=None):
    """Build source-grounded titles without allowing post-certification mutation."""
    barrier = motion.get('finalization_barrier') or {}
    if not barrier.get('timing_sha256'):
        return _filter_title_copy(_implementation.build_title_plan(
            package, alignment, vision_results, motion, alignment_report
        ))

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
    return _filter_title_copy(candidate)
