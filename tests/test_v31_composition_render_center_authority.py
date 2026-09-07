from __future__ import annotations

import tempfile
from pathlib import Path
from PIL import Image,ImageDraw

from hexa_v31.render.scene_media import prepare_composition_actor


with tempfile.TemporaryDirectory(prefix='hexa_render_center_authority_') as raw:
    root=Path(raw)
    source=root/'actor.png'
    image=Image.new('RGBA',(640,360),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((250,110,390,250),18,fill=(45,95,220,255))
    image.save(source)

    event={
        'event_id':'GENERIC_ACTOR',
        'source_path':str(source),
        'base_fit_scale_percent':100.0,
        'layout_scale_multiplier':1.0,
        'card_rest_position_norm':[0.31,0.67],
        # Deliberately stale integration metadata. Final planner layout must win.
        'object_rest_position_px':[1510.0,220.0],
        'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER',
    }
    runtime,crop=prepare_composition_actor(event,1920,1080)
    assert crop.shape[0]>0 and crop.shape[1]>0,crop.shape
    assert runtime['object_rest_position_px']==[595.2,723.6],runtime
    assert runtime['preset_coordinate_mode']=='ABSOLUTE_OBJECT_CENTER',runtime

    # Moving only the final planner center must move the runtime actor center.
    moved=dict(event,card_rest_position_norm=[0.72,0.28])
    runtime2,_=prepare_composition_actor(moved,1920,1080)
    assert runtime2['object_rest_position_px']==[1382.4,302.4],runtime2

print('V31_COMPOSITION_RENDER_CENTER_AUTHORITY_PASS')
