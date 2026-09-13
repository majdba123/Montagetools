from __future__ import annotations
import pathlib,sys
import cv2
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.extraction.matting import refine_alpha

# A very light illustrated object may be visually defined mostly by a thin dark
# contour.  Stage-leak repair must not tunnel through that contour and classify
# its enclosed white interior as the white stage.
h=w=128
rgb=np.full((h,w,3),255,dtype=np.uint8)
hard=np.zeros((h,w),dtype=np.uint8)
group=np.zeros((h,w),dtype=np.uint8)
center=(64,64);radius=42
cv2.circle(hard,center,radius,255,-1,lineType=cv2.LINE_AA)
cv2.circle(group,center,radius,255,-1,lineType=cv2.LINE_AA)
# One-pixel contour intentionally stresses the same antialias/topology case that
# broad white morphology used to bridge across.
cv2.circle(rgb,center,radius,(28,72,126),1,lineType=cv2.LINE_AA)
# Add a small colored source-backed accent so this remains representative of
# light illustrated UI/object art rather than a synthetic all-white disk.
cv2.line(rgb,(84,60),(94,60),(35,126,192),2,lineType=cv2.LINE_AA)

alpha,clean,metrics=refine_alpha(rgb,hard,(255,255,255),group_mask=group,feather_px=1.4)

yy,xx=np.ogrid[:h,:w]
interior=((xx-64)**2+(yy-64)**2)<=24**2
assert float(np.mean(alpha[interior]))>=248.0,metrics
assert float(np.mean(alpha[interior]<245))<=0.01,metrics
assert int(alpha[0,0])==0,metrics
assert clean.shape==rgb.shape

# The contour itself must also survive as opaque source ink rather than a pale
# ghost on the canonical white stage.
ring=np.abs(np.sqrt((xx-64)**2+(yy-64)**2)-radius)<=1.5
assert int(np.percentile(alpha[ring],50))>=220,metrics

print('V31_ENCLOSED_LIGHT_FOREGROUND_INTEGRITY_PASS',metrics)
