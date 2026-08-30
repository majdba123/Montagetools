import os
from hexa_v31.semantic_beats import normalize_scene_beats
s={'scene_id':'S1','script_span':{'text':'ما يسمح بتمريرها'},'semantic_beat':{'action':'ACCEPT','anchor_text':'ما يسمح بتمريرها'}}
b=normalize_scene_beats(s,{'scene_intervals':{'S1':{'start_seconds':1,'end_seconds':5}}})
assert len(b)==1 and b[0]['action']=='REJECT' and b[0]['polarity']=='NEGATED' and b[0]['perceptual_hit_seconds']==1
s['semantic_beats']=[{'action':'READ','anchor_text':'ما'},{'action':'REJECT','anchor_text':'يسمح'}]
b=normalize_scene_beats(s,{'scene_intervals':{'S1':{'start_seconds':1,'end_seconds':5}},'word_timings':[{'word':'يسمح','start_seconds':2.0}]})
assert len(b)==2 and all(x['source']=='PACKAGE' for x in b) and b[1]['perceptual_hit_seconds']==2.0
print('V31_V11_SEMANTIC_BEATS_PASS')
