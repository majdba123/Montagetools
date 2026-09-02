from __future__ import annotations

import math
import pathlib

import cv2
import numpy as np
from PIL import Image


def _window(event: dict) -> tuple[float, float]:
    return (float(event.get('physical_start_seconds', event.get('start_seconds', 0.0))),
            float(event.get('physical_end_seconds', event.get('end_seconds', 0.0))))


def _active(events: list[dict], t: float) -> list[dict]:
    return [e for e in events if not e.get('suppressed_by_card_density')
            and _window(e)[0] <= t < _window(e)[1]]


def visual_timeline_coverage_qa(motion_plan: dict, fps: float | None = None,
                                duration_seconds: float | None = None) -> dict:
    """Certify the committed physical layer timeline, independently of motion timing."""
    fps = float(fps or motion_plan.get('fps') or 30.0)
    events = list(motion_plan.get('events') or [])
    cards = list((motion_plan.get('visual_cards') or {}).get('cards') or [])
    failures, gaps, card_rows, truncated = [], [], [], []
    for event in events:
        if event.get('suppressed_by_card_density'):
            continue
        ps, pe = _window(event)
        ms = float(event.get('motion_start_seconds', event.get('start_seconds', ps)))
        me = float(event.get('motion_end_seconds', event.get('end_seconds', pe)))
        if ps > ms + 1e-6 or pe < me - 1e-6:
            failures.append(f"{event.get('event_id')}: motion lifetime escapes physical lifetime")
        if event.get('topology_recovery') == 'TEMPORAL_SPATIAL_REUSE__SUPPORT_EXIT' or event.get('collision_truncated'):
            truncated.append(str(event.get('event_id')))
    step = 1.0 / max(1.0, fps)
    for card in cards:
        cid = str(card.get('card_id')); start = float(card.get('start_seconds', 0)); end = float(card.get('end_seconds', 0))
        samples = max(1, int(math.ceil((end-start)*fps))); uncovered = 0; run_start = None
        for frame in range(samples):
            t = start + frame*step
            if not _active(events, t):
                uncovered += 1
                if run_start is None: run_start = t
            elif run_start is not None:
                gaps.append({'visual_card_id': cid, 'start_seconds': round(run_start, 6), 'end_seconds': round(t, 6), 'duration_seconds': round(t-run_start, 6)})
                run_start = None
        if run_start is not None:
            gaps.append({'visual_card_id': cid, 'start_seconds': round(run_start, 6), 'end_seconds': round(end, 6), 'duration_seconds': round(end-run_start, 6)})
        card_rows.append({'visual_card_id': cid, 'sample_count': samples, 'active_visual_carrier_count_min': 0 if uncovered else 1, 'coverage_ratio': round((samples-uncovered)/samples, 6)})
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for event in events:
        if event.get('render_mode') in {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'} and not event.get('suppressed_by_card_density'):
            key = (str(event.get('visual_card_id')), str(event.get('scene_id')), str(event.get('partition_root_id')))
            groups.setdefault(key, []).append(event)
    group_rows = []
    for key, members in groups.items():
        starts = {_window(e)[0] for e in members}; ends = {_window(e)[1] for e in members}
        residuals = [e for e in members if e.get('render_mode') == 'RESIDUAL_SUPPORT']
        valid = len(starts) == 1 and len(ends) == 1
        if residuals:
            valid = valid and all(not e.get('independent_motion_allowed') and not e.get('translation_safe_after_occlusion') and not e.get('position_animated') for e in residuals)
        if not valid: failures.append(f"{key[0]}:{key[1]}:{key[2]}: Foundation partition physical lifetime is incomplete")
        group_rows.append({'visual_card_id': key[0], 'scene_id': key[1], 'partition_root_id': key[2], 'member_count': len(members), 'residual_support_count': len(residuals), 'collective_lifetime_pass': valid})
    if gaps: failures.append('VISUAL_TIMELINE_COVERAGE_GAP')
    if truncated: failures.append('collision recovery prematurely truncated visual carriers')
    planned_end = max((float(c.get('end_seconds', 0)) for c in cards), default=0.0)
    required_end = float(duration_seconds if duration_seconds is not None else planned_end)
    trailing_gap = max(0.0, required_end-planned_end)
    if trailing_gap > step*.5: failures.append(f'visual timeline ends {trailing_gap:.3f}s before required audio duration')
    return {'schema': 'HEXA_V31_VISUAL_TIMELINE_COVERAGE_QA', 'pass': not failures, 'failures': failures,
            'visual_gaps': gaps, 'longest_uncovered_narration_seconds': max((g['duration_seconds'] for g in gaps), default=0.0),
            'card_coverage': card_rows, 'foundation_partition_groups': group_rows,
            'prematurely_truncated_event_ids': truncated, 'planned_visual_end_seconds': planned_end,
            'required_duration_seconds': required_end, 'trailing_uncovered_seconds': round(trailing_gap, 6)}


def encoded_visual_gap_qa(path: str | pathlib.Path, motion_plan: dict, *, max_blank_seconds: float = 0.50) -> dict:
    """Decode MP4 and reject sustained loss of source-derived foreground ink."""
    cap = cv2.VideoCapture(str(path)); fps = float(cap.get(cv2.CAP_PROP_FPS) or motion_plan.get('fps') or 30.0)
    if not cap.isOpened(): return {'pass': False, 'failures': ['encoded MP4 could not be decoded'], 'blank_runs': []}
    events = [e for e in (motion_plan.get('events') or []) if not e.get('suppressed_by_card_density')]
    alpha_pixels = {}
    for event in events:
        src = event.get('source_path') or event.get('source_layer_path')
        try: alpha_pixels[str(event.get('event_id'))] = int(np.count_nonzero(np.asarray(Image.open(src).convert('RGBA'))[:, :, 3] > 12))
        except Exception: alpha_pixels[str(event.get('event_id'))] = 0
    runs, run_start, frame = [], None, 0
    while True:
        ok, image = cap.read()
        if not ok: break
        t = frame/fps; live = _active(events, t); expected = sum(alpha_pixels.get(str(e.get('event_id')), 0) for e in live)
        meaningful = int(np.count_nonzero(np.max(255-image.astype(np.int16), axis=2) > 10))
        blank = bool(live) and meaningful < max(12, int(expected*.0025))
        if blank and run_start is None: run_start = frame
        elif not blank and run_start is not None:
            if (frame-run_start)/fps >= max_blank_seconds: runs.append({'start_frame': run_start, 'end_frame': frame, 'duration_seconds': round((frame-run_start)/fps, 6)})
            run_start = None
        frame += 1
    cap.release()
    if run_start is not None and (frame-run_start)/fps >= max_blank_seconds: runs.append({'start_frame': run_start, 'end_frame': frame, 'duration_seconds': round((frame-run_start)/fps, 6)})
    return {'schema': 'HEXA_V31_ENCODED_VISUAL_GAP_QA', 'pass': not runs,
            'failures': ['ENCODED_VISUAL_TIMELINE_COVERAGE_GAP'] if runs else [], 'blank_runs': runs,
            'decoded_frames': frame, 'fps': fps, 'max_blank_seconds': max_blank_seconds}
