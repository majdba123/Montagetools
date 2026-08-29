import json
import sys

import cv2
import numpy as np


video_path, typography_path = sys.argv[1:3]
events = json.load(open(typography_path, encoding="utf-8"))["events"]
capture = cv2.VideoCapture(video_path)
fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
occupancy = []
sample_step = 5
frame_index = 0
while True:
    ok, frame = capture.read()
    if not ok:
        break
    if frame_index % sample_step:
        frame_index += 1
        continue
    frame = cv2.resize(frame, (426, 240))
    occupancy.append(float(np.mean(np.min(frame, axis=2) < 248) * 100.0))
    frame_index += 1
capture.release()

underfilled = np.asarray(occupancy) < 15.0
sample_fps = fps / sample_step
start = None
intervals = []
for index, value in enumerate(underfilled):
    if value and start is None:
        start = index
    elif not value and start is not None:
        if index - start >= 2:
            intervals.append((start / sample_fps, index / sample_fps, (index - start) / sample_fps))
        start = None
if start is not None and len(underfilled) - start >= 2:
    intervals.append((start / sample_fps, len(underfilled) / sample_fps, (len(underfilled) - start) / sample_fps))

for begin, end, duration in sorted(intervals, key=lambda row: -row[2])[:40]:
    active = [
        row["text_id"]
        for row in events
        if min(end, float(row["end_seconds"])) > max(begin, float(row["start_seconds"]))
    ]
    print(f"{begin:.2f}\t{end:.2f}\t{duration:.2f}\t{','.join(active) or '-'}")
