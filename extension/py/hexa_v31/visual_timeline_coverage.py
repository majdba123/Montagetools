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


def frame_survival_signature(image: np.ndarray, frame: int, time_seconds: float,
                             members: list[dict] | None = None, grid=(16, 9)) -> dict:
    """Compact source-structure evidence from an unencoded RGB render frame."""
    ink=np.max(255-image.astype(np.int16),axis=2).astype(np.float32)
    mask=ink>10; yy,xx=np.where(mask); h,w=image.shape[:2];gw,gh=grid
    cells=[]
    for gy in range(gh):
        y0=gy*h//gh;y1=(gy+1)*h//gh
        for gx in range(gw):
            x0=gx*w//gw;x1=(gx+1)*w//gw
            cells.append(round(float(ink[y0:y1,x0:x1].sum()),2))
    rows=[]
    for member in members or []:
        box=member.get('bbox_px') or [0,0,0,0];x0,y0,x1,y1=[int(round(v)) for v in box]
        x0=max(0,min(w,x0));x1=max(x0,min(w,x1));y0=max(0,min(h,y0));y1=max(y0,min(h,y1))
        roi=ink[y0:y1,x0:x1]
        rows.append({'event_id':str(member.get('event_id')),'render_mode':member.get('render_mode'),
                     'bbox_px':[x0,y0,x1,y1],'expected_ink':round(float(roi.sum()),2),
                     'expected_foreground_pixels':int(np.count_nonzero(roi>10))})
    return {'frame':int(frame),'time_seconds':round(float(time_seconds),6),'width':w,'height':h,
            'foreground_pixels':int(np.count_nonzero(mask)),'total_ink':round(float(ink.sum()),2),
            'foreground_bbox_px':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)] if len(xx) else None,
            'grid':[gw,gh],'grid_ink':cells,'members':rows,
            'expected_active_actor_ids':[x['event_id'] for x in rows],
            'expected_foundation_partition_member_ids':[x['event_id'] for x in rows if x.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}]}


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


def encoded_visual_gap_qa(path: str | pathlib.Path, motion_plan: dict, *, max_blank_seconds: float = 0.50,
                          expected_evidence: list[dict] | None = None) -> dict:
    """Decode MP4 and reject blank gaps or material source-structure loss.

    Survival tolerances are deliberately much wider than observed H.264/yuv420p
    drift: at least 45% of expected ink/area, 55% spatial-grid recall, and 35%
    of each expected member ROI must survive. These gates tolerate compression
    and pale anti-aliased edges without accepting a small remaining fragment.
    """
    cap = cv2.VideoCapture(str(path)); fps = float(cap.get(cv2.CAP_PROP_FPS) or motion_plan.get('fps') or 30.0)
    if not cap.isOpened(): return {'pass': False, 'failures': ['encoded MP4 could not be decoded'], 'blank_runs': []}
    events = [e for e in (motion_plan.get('events') or []) if not e.get('suppressed_by_card_density')]
    alpha_pixels = {}
    for event in events:
        src = event.get('source_path') or event.get('source_layer_path')
        try: alpha_pixels[str(event.get('event_id'))] = int(np.count_nonzero(np.asarray(Image.open(src).convert('RGBA'))[:, :, 3] > 12))
        except Exception: alpha_pixels[str(event.get('event_id'))] = 0
    evidence={int(x.get('frame')):x for x in (expected_evidence or [])}
    runs, run_start, frame, losses = [], None, 0, []
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
        reference=evidence.get(frame)
        if reference and float(reference.get('total_ink') or 0)>0:
            actual=frame_survival_signature(cv2.cvtColor(image,cv2.COLOR_BGR2RGB),frame,t)
            ink_ratio=float(actual['total_ink'])/max(1.0,float(reference['total_ink']))
            area_ratio=float(actual['foreground_pixels'])/max(1,int(reference['foreground_pixels']))
            expected_grid=np.asarray(reference.get('grid_ink') or [],dtype=np.float64)
            actual_grid=np.asarray(actual.get('grid_ink') or [],dtype=np.float64)
            grid_recall=float(np.minimum(expected_grid,actual_grid).sum()/max(1.0,expected_grid.sum())) if len(expected_grid)==len(actual_grid) else 0.0
            rb=reference.get('foreground_bbox_px');ab=actual.get('foreground_bbox_px')
            bbox_width_ratio=(float(ab[2]-ab[0])/max(1,float(rb[2]-rb[0]))) if rb and ab else 0.0
            bbox_height_ratio=(float(ab[3]-ab[1])/max(1,float(rb[3]-rb[1]))) if rb and ab else 0.0
            member_losses=[]
            ink=np.max(255-image.astype(np.int16),axis=2).astype(np.float32)
            for member in reference.get('members') or []:
                x0,y0,x1,y1=map(int,member.get('bbox_px') or [0,0,0,0]);roi=ink[y0:y1,x0:x1]
                ratio=float(roi.sum())/max(1.0,float(member.get('expected_ink') or 0))
                if float(member.get('expected_ink') or 0)>500 and ratio<.35:
                    member_losses.append({'event_id':member.get('event_id'),'render_mode':member.get('render_mode'),'ink_ratio':round(ratio,4)})
            if ink_ratio<.45 or area_ratio<.45 or grid_recall<.55 or bbox_width_ratio<.55 or bbox_height_ratio<.55 or member_losses:
                losses.append({'frame':frame,'time_seconds':round(t,6),'ink_ratio':round(ink_ratio,4),
                               'foreground_area_ratio':round(area_ratio,4),'spatial_grid_recall':round(grid_recall,4),
                               'bbox_width_ratio':round(bbox_width_ratio,4),'bbox_height_ratio':round(bbox_height_ratio,4),
                               'missing_or_collapsed_members':member_losses})
        frame += 1
    cap.release()
    if run_start is not None and (frame-run_start)/fps >= max_blank_seconds: runs.append({'start_frame': run_start, 'end_frame': frame, 'duration_seconds': round((frame-run_start)/fps, 6)})
    failures=[]
    if runs:failures.append('ENCODED_VISUAL_TIMELINE_COVERAGE_GAP')
    if losses:failures.append('ENCODED_SOURCE_VISUAL_SURVIVAL_FAILED')
    return {'schema': 'HEXA_V31_ENCODED_VISUAL_GAP_QA', 'pass': not failures,
            'failures':failures,'blank_runs':runs,'source_survival_failures':losses,
            'source_survival_sample_count':len(evidence),'decoded_frames':frame,'fps':fps,
            'max_blank_seconds':max_blank_seconds,
            'thresholds':{'minimum_ink_ratio':.45,'minimum_foreground_area_ratio':.45,
                          'minimum_spatial_grid_recall':.55,'minimum_bbox_axis_ratio':.55,
                          'minimum_member_ink_ratio':.35}}
