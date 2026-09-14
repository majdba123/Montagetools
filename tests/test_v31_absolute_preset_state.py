from hexa_v31.preview import _event_state
from hexa_v31.preset_authority import duration
base={'start_seconds':0.0,'end_seconds':4.0,'sequence_width':1920,'sequence_height':1080,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','object_rest_position_px':[300,400],'preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':0.0,'duration_seconds':duration('ENTRY_LEFT_TO_MIDDLE')},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':3.0,'duration_seconds':duration('DISAPPEAR_DOWN_SCALE')},'preset_actions':[]}
p0=_event_state(base,0.0)[0];p1=_event_state(base,duration('ENTRY_LEFT_TO_MIDDLE'))[0]
assert abs(p0[0]-(-0.5457847714424133*1920))<2.0,p0
assert abs(p1[0]-960)<2.0 and abs(p1[1]-540)<2.0,p1
support={'start_seconds':0.0,'end_seconds':2.0,'sequence_width':1920,'sequence_height':1080,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','object_rest_position_px':[350,700],'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':0.0,'duration_seconds':duration('APPEAR_HIGH_SCALE')},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.3,'duration_seconds':duration('DISAPPEAR_DOWN_SCALE')},'preset_actions':[]}
s=_event_state(support,0.0);assert abs(s[0][0]-350)<1e-3 and s[2]<=.02,s
# Low-resolution render paths may materialize the same normalized center in output
# pixels before motion evaluation.  The shared preview facade must normalize that
# coordinate back to the canonical 1920x1080 preset-authority space exactly once.
low=dict(support);low['sequence_width']=640;low['sequence_height']=360;low['object_rest_position_px']=[350*(640/1920),700*(360/1080)]
for t in (0.0,duration('APPEAR_HIGH_SCALE'),1.5):
    canonical=_event_state(support,t);scaled=_event_state(low,t)
    assert canonical is not None and scaled is not None,(canonical,scaled,t)
    assert abs(canonical[0][0]-scaled[0][0])<1e-6 and abs(canonical[0][1]-scaled[0][1])<1e-6,(canonical,scaled,t)
    assert abs(canonical[1]-scaled[1])<1e-9 and abs(canonical[2]-scaled[2])<1e-9,(canonical,scaled,t)
print('V31_ABSOLUTE_PRESET_STATE_PASS')
