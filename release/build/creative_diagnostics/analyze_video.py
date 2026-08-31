from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

import cv2
import numpy as np


def _json(path: pathlib.Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _times(plan: dict | None, duration: float) -> list[tuple[float, str]]:
    if not plan:
        return [(duration * i / 19.0, f"sample_{i:02d}") for i in range(20)]
    rows: list[tuple[float, str]] = []
    for card in ((plan.get("visual_cards") or {}).get("cards") or []):
        cid = str(card.get("card_id") or "card")
        rows.extend([(float(card.get("start_seconds", 0)), f"{cid}_start"),
                     (float(card.get("end_seconds", 0)), f"{cid}_end")])
    for event in plan.get("events") or []:
        if event.get("suppressed_by_card_density"):
            continue
        rows.append((float(event.get("perceptual_hit_seconds", event.get("start_seconds", 0))),
                     f"{event.get('event_id', 'event')}_hit"))
    unique: dict[int, tuple[float, str]] = {}
    for t, label in rows:
        t = max(0.0, min(duration - 0.001, t))
        key = int(round(t * 10))
        if key not in unique:
            unique[key] = (t, label)
    return [unique[k] for k in sorted(unique)]


def _read_at(cap: cv2.VideoCapture, fps: float, t: float):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(t * fps))))
    ok, frame = cap.read()
    return frame if ok else None


def analyze(video: pathlib.Path, out_dir: pathlib.Path, stem: str, plan_path: pathlib.Path | None):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "extension" / "py"))
    from hexa_v31.reference_metrics import analyze_video

    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / f"{stem}_metrics.json"
    metrics = analyze_video(video, metrics_path)
    cap = cv2.VideoCapture(str(video))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    duration = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    plan = _json(plan_path) if plan_path else None

    step = max(1, int(round(fps * 0.2)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    prev = None
    timeline = []
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step == 0:
            small = cv2.resize(frame, (426, 240), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            occ = float(np.mean(np.min(small, axis=2) < 248) * 100.0)
            motion = 0.0 if prev is None else float(np.mean(cv2.absdiff(gray, prev))) / 255.0 * 2.0
            changed = 0.0 if prev is None else float(np.mean(cv2.absdiff(gray, prev) >= 7) * 100.0)
            timeline.append((index / fps, motion, changed, occ))
            prev = gray
        index += 1
    with (out_dir / f"{stem}_motion_timeline.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_seconds", "motion_activity_200ms", "changed_pixels_percent", "nonwhite_occupancy_percent"))
        writer.writerows((f"{t:.6f}", f"{m:.9f}", f"{c:.4f}", f"{o:.4f}") for t, m, c, o in timeline)

    picks = _times(plan, duration)
    thumb_w, thumb_h = 384, 216
    cols = 4
    rows = (len(picks) + cols - 1) // cols
    sheet = np.full((rows * (thumb_h + 34), cols * thumb_w, 3), 255, np.uint8)
    for i, (t, label) in enumerate(picks):
        frame = _read_at(cap, fps, t)
        if frame is None:
            continue
        thumb = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        x, y = (i % cols) * thumb_w, (i // cols) * (thumb_h + 34)
        sheet[y:y + thumb_h, x:x + thumb_w] = thumb
        cv2.putText(sheet, f"{t:06.2f}s {label[:35]}", (x + 5, y + thumb_h + 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (20, 20, 20), 1, cv2.LINE_AA)
    cap.release()
    cv2.imwrite(str(out_dir / f"{stem}_contact_sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])

    failures = {
        "video": str(video),
        "failed_metrics": {
            "motion_activity": metrics["motion_activity"] < 0.02,
            "low_motion_percent": metrics["low_motion_percent"] > 48.0,
            "static_p90": metrics["p90_static_hold_seconds"] > 1.35,
            "static_max": metrics["max_static_hold_seconds"] > 2.5,
            "motion_p95": metrics["motion_p95"] < 0.075,
            "underfilled": metrics["underfilled_frame_percent_lt15pct"] > 20.0,
            "severe_spikes": metrics["severe_isolated_motion_spikes_per_minute"] > 3.0,
        },
        "card_boundary_and_major_beat_frame_count": len(picks),
    }
    with (out_dir / f"{stem}_quality_failures.json").open("w", encoding="utf-8") as handle:
        json.dump(failures, handle, ensure_ascii=False, indent=2)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=pathlib.Path)
    parser.add_argument("out_dir", type=pathlib.Path)
    parser.add_argument("stem")
    parser.add_argument("--motion-plan", type=pathlib.Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.video, args.out_dir, args.stem, args.motion_plan), indent=2))
