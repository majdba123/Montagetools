from hexa_v31.preview import _event_state
from hexa_v31.preset_authority import duration
base={'start_seconds':0.0,'end_seconds':4.0,'sequence_width':1920,'sequence_height':1080,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','object_rest_position_px':[300,400],'preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':0.0,'duration_seconds':duration('ENTRY_LEFT_TO_MIDDLE')},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':3.0,'duration_seconds':duration('DISAPPEAR_DOWN_SCALE')},'preset_actions':[]}
p0=_event_state(base,0.0)[0];p1=_event_state(base,duration('ENTRY_LEFT_TO_MIDDLE'))[0]
assert abs(p0[0]-(-0.5457847714424133*1920))<2.0,p0
assert abs(p1[0]-960)<2.0 and abs(p1[1]-540)<2.0,p1
support={'start_seconds':0.0,'end_seconds':2.0,'sequence_width':1920,'sequence_height':1080,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER','object_rest_position_px':[350,700],'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':0.0,'duration_seconds':duration('APPEAR_HIGH_SCALE')},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.3,'duration_seconds':duration('DISAPPEAR_DOWN_SCALE')},'preset_actions':[]}
s=_event_state(support,0.0);assert abs(s[0][0]-350)<1e-3 and s[2]<=.02,s
print('V31_ABSOLUTE_PRESET_STATE_PASS')
