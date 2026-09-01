import cv2
import numpy as np

from hexa_v31.matting import refine_alpha


height, width = 240, 360
rgb = np.full((height, width, 3), 255, np.uint8)

# A real object touches the left image boundary. Its dark outline encloses a
# legitimate white body, including anti-aliased white pixels beside the outline.
cv2.rectangle(rgb, (0, 45), (190, 205), (18, 28, 45), -1)
cv2.rectangle(rgb, (8, 53), (182, 197), (255, 255, 255), -1)
cv2.circle(rgb, (92, 125), 38, (40, 145, 220), -1, lineType=cv2.LINE_AA)

# Model the conservative semantic mask that caused the production failure: its
# bbox also includes a border-connected white-stage pocket to the object's right.
group = np.zeros((height, width), np.uint8)
group[40:211, 0:271] = 255

alpha, _, metrics = refine_alpha(
    rgb,
    group,
    (255, 255, 255),
    group_mask=group,
)

# Actual stage is removed, while boundary-touching ink and enclosed white body survive.
assert int(alpha[80, 235]) <= 8, (alpha[80, 235], metrics)
assert int(alpha[125, 0]) >= 245, (alpha[125, 0], metrics)
assert int(alpha[80, 40]) >= 245, (alpha[80, 40], metrics)
assert int(alpha[125, 92]) >= 245, (alpha[125, 92], metrics)
assert float(metrics['opaque_stage_leak_fraction']) <= 0.004, metrics
assert int(metrics['alpha_min']) == 0 and int(metrics['alpha_max']) == 255, metrics

print('V31_EDGE_TOUCHING_WHITE_FOREGROUND_PASS', metrics)
