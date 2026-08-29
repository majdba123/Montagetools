import numpy as np, cv2
from hexa_v31.matting import refine_alpha

H,W=300,500
rgb=np.full((H,W,3),255,np.uint8)
# Colored object with a deliberately enclosed pure-white interior.
cv2.rectangle(rgb,(70,70),(250,230),(15,80,210),12)
cv2.rectangle(rgb,(92,92),(228,208),(255,255,255),-1)
# A second colored lobe connected by a thin colored bridge. The intentionally bad
# hard group below includes the full bounding rectangle and therefore includes a large
# white-stage pocket that must become transparent.
cv2.rectangle(rgb,(330,105),(430,195),(40,180,90),-1)
cv2.line(rgb,(250,150),(330,150),(40,120,220),4)
# Simulate the bug: a conservative group/binary mask accidentally includes every pixel
# in the bounding rectangle, including white stage around the connector.
gm=np.zeros((H,W),np.uint8);gm[65:236,65:436]=255
alpha,clean,m=refine_alpha(rgb,gm,(255,255,255),group_mask=gm)
# Border-connected white stage inside the group must be transparent.
assert int(alpha[75,300]) <= 8, (alpha[75,300],m)
assert int(alpha[220,300]) <= 8, (alpha[220,300],m)
# Enclosed white face/card remains opaque because its outline disconnects it from the stage.
assert int(alpha[150,150]) >= 245, (alpha[150,150],m)
# Colored source ink remains opaque.
assert int(alpha[150,380]) >= 245 and int(alpha[150,270]) >= 220, m
assert float(m['opaque_stage_leak_fraction']) <= 0.004, m
print('V31_STAGE_LEAK_MATTING_PASS',m)
