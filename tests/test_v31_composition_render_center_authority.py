from __future__ import annotations

import math
import tempfile
from pathlib import Path
from PIL import Image,ImageDraw

from hexa_v31.preview import _event_state
from hexa_v31.render.scene_media import prepare_composition_actor


def assert_center(actual,expected):
    assert len(actual)==2,actual
    assert math.isclose(float(actual[0]),float(expected[0]),rel_tol=0.0,abs_tol=1e-9),(actual,expected)
    assert math.isclose(float(actual[1]),float(expected[1]),rel_tol=0.0,abs_tol=1e-9),(actual,expected)


with tempfile.TemporaryDirectory(prefix='hexa_render_center_authority_') as raw:
    root=Path(raw)
    source=root/'actor.png'
    image=Image.new('RGBA',(640,360),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((250,110,390,250),18,fill=(45,95,220,255))
    image.save(source)

    event={
        'event_id':'GENERIC_ACTOR','source_path':str(source),'base_fit_scale_percent':100.0,
        'layout_scale_multiplier':1.0,'card_rest_position_norm':[0.31,0.67],
        'object_rest_position_px':[1510.0,220.0],'rest_position_px':[960.0,540.0],
        'start_position_px':[960.0,540.0],'end_position_px':[960.0,540.0],
        'exit_position_px':[960.0,540.0],'micro_position_px':[960.0,540.0],
        'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','sequence_width':1920.0,'sequence_height':1080.0,
        'start_seconds':0.0,'settle_seconds':0.0,'end_seconds':4.0,
        'physical_start_seconds':0.0,'physical_end_seconds':4.0,
        'motion_start_seconds':0.0,'motion_end_seconds':0.0,'position_animated':False,
        'preset_entry':None,'preset_exit':None,'preset_actions':[],
        'composition_states':[],'composition_participant_states':[],
    }
    runtime,crop=prepare_composition_actor(event,1920,1080)
    assert crop.shape[0]>0 and crop.shape[1]>0,crop.shape
    assert_center(runtime['object_rest_position_px'],[595.2,723.6])
    assert runtime['preset_coordinate_mode']=='ABSOLUTE_OBJECT_CENTER',runtime

    state=_event_state(runtime,1.0)
    assert state is not None,state
    assert_center(state[0],[595.2,723.6])
    assert math.isclose(float(state[1]),1.0,abs_tol=1e-9),state
    assert math.isclose(float(state[2]),1.0,abs_tol=1e-9),state

    moved=dict(event,card_rest_position_norm=[0.72,0.28])
    runtime2,_=prepare_composition_actor(moved,1920,1080)
    assert_center(runtime2['object_rest_position_px'],[1382.4,302.4])
    state2=_event_state(runtime2,1.0)
    assert state2 is not None,state2
    assert_center(state2[0],[1382.4,302.4])

print('V31_COMPOSITION_RENDER_CENTER_AUTHORITY_PASS')
