import tempfile
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
from hexa_v31.render.scene_media import _prescale_visible_source, prepare_composition_actor
from hexa_v31.render.preview import _prescale

source=np.zeros((1080,1920,4),np.uint8)
source[410:680,830:1090]=[20,70,130,255]
for factor in (2.,3.13,4.5):
    actual,virtual,origin=_prescale_visible_source(source,factor*100,1920)
    assert actual.nbytes<virtual[0]*virtual[1]*4*.15,(actual.shape,virtual)
    expected=_prescale(source,factor*100,1920)
    crop=expected[origin[1]:origin[1]+actual.shape[0],origin[0]:origin[0]+actual.shape[1]]
    # Global-grid geometry is exact; OpenCV remap quantizes interpolation to
    # 1/32 pixel, unlike resize. Only fractional edge rasterization may differ.
    assert actual.shape==crop.shape
    assert np.mean(np.abs(actual.astype(float)-crop.astype(float)))<.10
    assert np.max(np.abs(actual.astype(float)-crop.astype(float)))<=6
    a=cv2.boundingRect((actual[:,:,3]>127).astype(np.uint8))
    b=cv2.boundingRect((crop[:,:,3]>127).astype(np.uint8))
    assert a==b,(a,b)
with tempfile.TemporaryDirectory() as raw:
    path=Path(raw)/'source.png';Image.fromarray(source).save(path)
    event=dict(source_path=str(path),layout_scale_multiplier=4.5,card_rest_position_norm=[.4,.6])
    runtime,image=prepare_composition_actor(event,1920,1080)
    assert runtime['object_rest_position_px']==[768.,648.]
    assert image.nbytes<10_000_000
    # Sparse high-scale path must never call the full-canvas prescaler.
    with patch('hexa_v31.render.scene_media._prescale',side_effect=AssertionError('giant raster')):
        prepare_composition_actor(event,1920,1080)
print('V31_SPARSE_SOURCE_PREPARATION_PASS')
