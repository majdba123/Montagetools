"""Global encoded-frame coverage authority for scene handoff certification.

Coverage must be measured on the timestamps that can actually exist in the encoded
video (frame / fps). Card-local floating sample clocks can report gaps that are not
representable by any encoded frame. This contract preserves every non-gap failure from
the canonical coverage QA and replaces only gap/card sampling with encoded-frame-grid
evidence, including certified scene-boundary carriers.
"""
from __future__ import annotations

import math


def _coverage_on_global_frame_grid(plan, fps, base_coverage):
    from hexa_v31.interaction import scene_ownership_contract as ownership

    fps = max(1.0, float(fps or plan.get('fps') or 30.0))
    report = dict(base_coverage(plan, fps=fps))
    events = [event for event in (plan.get('events') or []) if not event.get('suppressed_by_card_density')]
    cards = list((plan.get('visual_cards') or {}).get('cards') or [])
    eps = 1e-9

    def normal_active(event, t):
        physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
        physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
        ownership_start = float(event.get('scene_ownership_start_seconds', physical_start))
        ownership_end = float(event.get('scene_ownership_end_seconds', physical_end))
        return max(physical_start, ownership_start) - eps <= t < min(physical_end, ownership_end) - eps

    def pixel_active(event, t):
        return normal_active(event, t) or ownership._carrier_covers(event, t)

    gaps = []
    card_rows = []
    for card in cards:
        card_id = str(card.get('card_id'))
        card_start = float(card.get('start_seconds', 0.0))
        card_end = float(card.get('end_seconds', card_start))
        first_frame = max(0, int(math.ceil(card_start * fps - eps)))
        end_frame = max(first_frame, int(math.ceil(card_end * fps - eps)))
        sample_count = max(1, end_frame - first_frame)
        uncovered = 0
        run_start_frame = None
        for frame in range(first_frame, end_frame):
            t = frame / fps
            if not any(pixel_active(event, t) for event in events):
                uncovered += 1
                if run_start_frame is None:
                    run_start_frame = frame
            elif run_start_frame is not None:
                gaps.append({
                    'visual_card_id': card_id,
                    'start_seconds': round(run_start_frame / fps, 6),
                    'end_seconds': round(frame / fps, 6),
                    'duration_seconds': round((frame - run_start_frame) / fps, 6),
                    'start_frame': run_start_frame,
                    'end_frame': frame,
                    'sampling_authority': 'GLOBAL_ENCODED_FRAME_GRID',
                })
                run_start_frame = None
        if run_start_frame is not None:
            gaps.append({
                'visual_card_id': card_id,
                'start_seconds': round(run_start_frame / fps, 6),
                'end_seconds': round(end_frame / fps, 6),
                'duration_seconds': round((end_frame - run_start_frame) / fps, 6),
                'start_frame': run_start_frame,
                'end_frame': end_frame,
                'sampling_authority': 'GLOBAL_ENCODED_FRAME_GRID',
            })
        card_rows.append({
            'visual_card_id': card_id,
            'sample_count': sample_count,
            'active_visual_carrier_count_min': 0 if uncovered else 1,
            'coverage_ratio': round((sample_count - uncovered) / sample_count, 6),
            'sampling_authority': 'GLOBAL_ENCODED_FRAME_GRID',
        })

    failures = [failure for failure in (report.get('failures') or []) if failure != 'VISUAL_TIMELINE_COVERAGE_GAP']
    if gaps:
        failures.append('VISUAL_TIMELINE_COVERAGE_GAP')
    report['visual_gaps'] = gaps
    report['card_coverage'] = card_rows
    report['longest_uncovered_narration_seconds'] = max(
        (float(row.get('duration_seconds') or 0.0) for row in gaps), default=0.0
    )
    report['coverage_sampling_authority'] = 'GLOBAL_ENCODED_FRAME_GRID'
    report['boundary_carrier_count'] = sum(1 for event in events if ownership._carrier_window(event) is not None)
    report['failures'] = failures
    report['pass'] = not failures
    return report


def install(scene_ownership_contract_module) -> None:
    if getattr(scene_ownership_contract_module, '_global_frame_coverage_contract_installed', False):
        return
    scene_ownership_contract_module._coverage_with_boundary_carriers = _coverage_on_global_frame_grid
    scene_ownership_contract_module._global_frame_coverage_contract_installed = True
