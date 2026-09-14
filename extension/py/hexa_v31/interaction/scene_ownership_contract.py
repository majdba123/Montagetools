"""Install final source-scene ownership and readable pixel handoff contracts.

Semantic/action timing remains authoritative.  When the truthful incoming scene has no
material pixels at an ordinary cut, the renderer may hold the outgoing scene's exact
last material pose until the first truthful incoming frame.  That hold is pixel-only:
physical lifetime, preset timing and interaction actions are never moved to manufacture
coverage.
"""
from __future__ import annotations

_BOUNDARY_AUTHORITY = 'OUTGOING_LAST_MATERIAL_PIXEL_HOLD'
_CARRIER_FIELDS = (
    'scene_boundary_carrier_start_seconds',
    'scene_boundary_carrier_end_seconds',
    'scene_boundary_carrier_sample_seconds',
    'scene_boundary_carrier_authority',
)


def _carrier_window(event):
    start = event.get('scene_boundary_carrier_start_seconds')
    end = event.get('scene_boundary_carrier_end_seconds')
    if start is None or end is None:
        return None
    start = float(start); end = float(end)
    return (start, end) if end > start + 1e-9 else None


def _carrier_covers(event, t):
    window = _carrier_window(event)
    return bool(window and window[0] - 1e-9 <= float(t) < window[1] - 1e-9)


def _compile_with_boundary_carriers(plan, fps, base_compile):
    from hexa_v31.composition_qa import _state
    from hexa_v31.planning.scene_ownership import (
        _active, _frame_time, _material_frames, _scene_id,
    )

    fps = max(1.0, float(fps or plan.get('fps') or 30.0))
    events = _active(list(plan.get('events') or []))
    for event in events:
        for field in _CARRIER_FIELDS:
            event.pop(field, None)

    report = base_compile(plan, fps=fps)
    if not report.get('pass'):
        return report

    by_scene = {}
    for event in events:
        by_scene.setdefault(_scene_id(event), []).append(event)

    failures = list(report.get('failures') or [])
    carriers = []
    for handoff in report.get('handoffs') or []:
        outgoing_id = str(handoff.get('outgoing_scene_id') or '')
        incoming_id = str(handoff.get('incoming_scene_id') or '')
        outgoing = by_scene.get(outgoing_id, [])
        incoming = by_scene.get(incoming_id, [])
        boundary = int(handoff.get('frame') or 0)

        # A protected outgoing source may have pushed ownership past the incoming
        # scene's earlier pre-roll.  The final handoff must still land on a truthful
        # materially-visible incoming frame, never on an invisible semantic placeholder.
        incoming_material = _material_frames(incoming, fps, ignore_scene_ownership=True)
        truthful_incoming = next((int(frame) for frame in incoming_material if int(frame) >= boundary), None)
        if truthful_incoming is None:
            failures.append(
                f'{outgoing_id}->{incoming_id}: no materially-visible incoming frame exists at or after ownership handoff'
            )
            continue
        if truthful_incoming > boundary:
            boundary = truthful_incoming
            handoff['frame'] = boundary
            handoff['seconds'] = round(_frame_time(boundary, fps), 6)
            handoff['reason'] = str(handoff.get('reason') or 'SOURCE_SCENE_BOUNDARY') + '__INCOMING_MATERIAL_ALIGN'
            for event in outgoing:
                event['scene_ownership_end_seconds'] = _frame_time(boundary, fps)
            for event in incoming:
                event['scene_ownership_start_seconds'] = _frame_time(boundary, fps)

        outgoing_material = [
            int(frame) for frame in _material_frames(outgoing, fps, ignore_scene_ownership=False)
            if int(frame) < boundary
        ]
        if not outgoing_material:
            failures.append(f'{outgoing_id}->{incoming_id}: outgoing scene has no material frame before handoff')
            continue
        sample_frame = max(outgoing_material)
        carrier_start_frame = sample_frame + 1
        if carrier_start_frame >= boundary:
            continue

        sample_time = _frame_time(sample_frame, fps)
        carrier_start = _frame_time(carrier_start_frame, fps)
        carrier_end = _frame_time(boundary, fps)
        held = []
        for event in outgoing:
            state = _state(event, sample_time, ignore_scene_ownership=True)
            if state is None or float(state[2]) <= 0.05:
                continue
            event['scene_boundary_carrier_start_seconds'] = carrier_start
            event['scene_boundary_carrier_end_seconds'] = carrier_end
            event['scene_boundary_carrier_sample_seconds'] = sample_time
            event['scene_boundary_carrier_authority'] = _BOUNDARY_AUTHORITY
            held.append(str(event.get('event_id')))
        if not held:
            failures.append(f'{outgoing_id}->{incoming_id}: no materially-visible outgoing pose for boundary carrier')
            continue
        carriers.append({
            'authority': _BOUNDARY_AUTHORITY,
            'outgoing_scene_id': outgoing_id,
            'incoming_scene_id': incoming_id,
            'event_ids': sorted(held),
            'sample_frame': sample_frame,
            'sample_seconds': round(sample_time, 6),
            'start_frame': carrier_start_frame,
            'start_seconds': round(carrier_start, 6),
            'end_frame': boundary,
            'end_seconds': round(carrier_end, 6),
            'duration_frames': boundary - carrier_start_frame,
            'duration_seconds': round(carrier_end - carrier_start, 6),
        })

    report['boundary_carriers'] = carriers
    report['failures'] = failures
    report['pass'] = not failures
    plan['scene_ownership_compiler'] = report
    return report


def _qa_with_boundary_carriers(plan, fps, base_qa):
    from hexa_v31.composition_qa import _state
    from hexa_v31.planning.scene_ownership import _frame_time, _scene_id

    report = dict(base_qa(plan, fps=fps))
    events = [event for event in (plan.get('events') or []) if not event.get('suppressed_by_card_density')]
    by_scene = {}
    for event in events:
        by_scene.setdefault(_scene_id(event), []).append(event)

    remaining = []
    covered = []
    for row in report.get('uncovered_handoffs') or []:
        frame = int(row.get('frame') or 0)
        prev_t = _frame_time(max(0, frame - 1), fps)
        next_t = _frame_time(frame, fps)
        outgoing = by_scene.get(str(row.get('outgoing_scene_id') or ''), [])
        incoming = by_scene.get(str(row.get('incoming_scene_id') or ''), [])
        outgoing_visible = any(
            _carrier_covers(event, prev_t)
            and (state := _state(event, float(event['scene_boundary_carrier_sample_seconds']), ignore_scene_ownership=True)) is not None
            and float(state[2]) > 0.05
            for event in outgoing
        )
        incoming_visible = any(
            (state := _state(event, next_t)) is not None and float(state[2]) > 0.05
            for event in incoming
        )
        if outgoing_visible and incoming_visible:
            covered.append(row)
        else:
            remaining.append(row)

    failures = list(report.get('failures') or [])
    if covered and not remaining:
        failures = [failure for failure in failures if failure != 'SCENE_OWNERSHIP_HANDOFF_GAP']

    carrier_rows = []
    for event in events:
        window = _carrier_window(event)
        if window is None:
            continue
        sample = event.get('scene_boundary_carrier_sample_seconds')
        authority = event.get('scene_boundary_carrier_authority')
        valid = sample is not None and authority == _BOUNDARY_AUTHORITY
        if valid:
            sample = float(sample)
            owner_start = float(event.get('scene_ownership_start_seconds', window[0]))
            owner_end = float(event.get('scene_ownership_end_seconds', window[1]))
            state = _state(event, sample, ignore_scene_ownership=True)
            valid = (
                owner_start - 1e-6 <= window[0] < window[1] <= owner_end + 1e-6
                and sample < window[0] - 1e-9
                and state is not None and float(state[2]) > 0.05
            )
        if not valid:
            failures.append(f"{event.get('event_id')}: invalid scene boundary carrier")
        carrier_rows.append({
            'event_id': str(event.get('event_id')),
            'scene_id': _scene_id(event),
            'start_seconds': window[0], 'end_seconds': window[1],
            'sample_seconds': sample, 'authority': authority, 'pass': bool(valid),
        })

    report['uncovered_handoffs'] = remaining
    report['uncovered_handoff_count'] = len(remaining)
    report['boundary_carrier_covered_handoffs'] = covered
    report['boundary_carrier_count'] = len(carrier_rows)
    report['boundary_carriers'] = carrier_rows
    report['failures'] = failures
    report['pass'] = not failures
    return report


def _coverage_with_boundary_carriers(plan, fps, base_coverage):
    report = dict(base_coverage(plan, fps=fps))
    events = [event for event in (plan.get('events') or []) if not event.get('suppressed_by_card_density')]
    covered = []
    remaining = []
    for gap in report.get('visual_gaps') or []:
        start = float(gap.get('start_seconds') or 0.0)
        end = float(gap.get('end_seconds') or start)
        first = int(round(start * fps))
        last = int(round(end * fps))
        okay = True
        for frame in range(first, last):
            t = frame / max(1.0, float(fps))
            if not any(_carrier_covers(event, t) for event in events):
                okay = False
                break
        (covered if okay else remaining).append(gap)

    failures = list(report.get('failures') or [])
    if covered and not remaining:
        failures = [failure for failure in failures if failure != 'VISUAL_TIMELINE_COVERAGE_GAP']
    report['visual_gaps'] = remaining
    report['boundary_carrier_covered_gaps'] = covered
    report['boundary_carrier_covered_gap_count'] = len(covered)
    report['longest_uncovered_narration_seconds'] = max(
        (float(row.get('duration_seconds') or 0.0) for row in remaining), default=0.0
    )
    if covered:
        covered_cards = {str(row.get('visual_card_id')) for row in covered}
        remaining_cards = {str(row.get('visual_card_id')) for row in remaining}
        card_rows = []
        for source in report.get('card_coverage') or []:
            row = dict(source)
            cid = str(row.get('visual_card_id'))
            if cid in covered_cards and cid not in remaining_cards:
                row['active_visual_carrier_count_min'] = 1
                row['coverage_ratio'] = 1.0
            card_rows.append(row)
        report['card_coverage'] = card_rows
    report['failures'] = failures
    report['pass'] = not failures
    return report


def install(impl) -> None:
    if getattr(impl, '_scene_ownership_contract_installed', False):
        return

    from hexa_v31.composition_qa import composition_plan_qa
    from hexa_v31.planning.scene_ownership import compile_scene_ownership as base_compile_scene_ownership
    from hexa_v31.planning.scene_ownership_qa import scene_ownership_qa as base_scene_ownership_qa
    from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa

    ownership_fields = (
        'scene_ownership_start_seconds', 'scene_ownership_end_seconds',
        'scene_ownership_authority', 'scene_ownership_index',
        'scene_ownership_recovery_authority', *_CARRIER_FIELDS,
    )
    impl._FINAL_TIMING_FIELDS = tuple(dict.fromkeys((*impl._FINAL_TIMING_FIELDS, *ownership_fields)))

    def compile_scene_ownership(plan, fps=30.0):
        return _compile_with_boundary_carriers(plan, fps, base_compile_scene_ownership)

    def scene_ownership_qa(plan, fps=30.0):
        return _qa_with_boundary_carriers(plan, fps, base_scene_ownership_qa)

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
            raise ValueError('SCENE_OWNERSHIP_COMPILATION_FAILED: ' + ' | '.join(ownership_before.get('failures') or [])[:2000])

        certification = _final_physical_certification(events, cards, fps)
        ownership_compiler = compile_scene_ownership(plan, fps=fps)
        if not ownership_compiler.get('pass'):
            raise ValueError('FINAL_SCENE_OWNERSHIP_COMPILATION_FAILED: ' + ' | '.join(ownership_compiler.get('failures') or [])[:2000])
        ownership_qa = scene_ownership_qa(plan, fps=fps)
        if not ownership_qa.get('pass'):
            raise ValueError('FINAL_SCENE_OWNERSHIP_QA_FAILED: ' + ' | '.join(ownership_qa.get('failures') or [])[:2000])
        post_ownership_composition = composition_plan_qa(plan)
        if not post_ownership_composition.get('pass'):
            raise ValueError('FINAL_SCENE_OWNERSHIP_COMPOSITION_QA_FAILED: ' + ' | '.join(post_ownership_composition.get('failures') or [])[:2000])

        coverage = _coverage_with_boundary_carriers(plan, fps, visual_timeline_coverage_qa)
        if not coverage.get('pass'):
            raise ValueError('FINAL_INTERACTION_LIFETIME_RECONCILIATION_FAILED: ' + ' | '.join(coverage.get('failures') or [])[:2000])

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

    def build_interaction_motion_plan(plan, alignment, vision_results, rules_path, reference_path, *, fps=30.0, logger=None, calibration=None):
        from hexa_v31.motion.motion import build_motion_plan as base_build_motion_plan
        base = base_build_motion_plan(plan, alignment, vision_results, rules_path, reference_path, fps=fps, logger=logger, calibration=calibration)
        ownership = compile_scene_ownership(base, fps=fps)
        if not ownership.get('pass'):
            raise ValueError('BASE_SCENE_OWNERSHIP_COMPILATION_FAILED: ' + ' | '.join(ownership.get('failures') or [])[:2000])
        interacted = impl.apply_interaction_director(base, plan, alignment, fps=fps, logger=logger)
        return finalize_interaction_motion_plan(interacted, fps=fps)

    impl.finalize_interaction_motion_plan = finalize_interaction_motion_plan
    impl.build_interaction_motion_plan = build_interaction_motion_plan
    impl._scene_ownership_contract_installed = True
