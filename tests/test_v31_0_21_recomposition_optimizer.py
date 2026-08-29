from hexa_v31.preset_story_planner import _recomposition_optimize

c={'card_id':'C','start_seconds':0.,'end_seconds':5.}
def e(i,st,hit,en,x):return {'event_id':f'E{i}','visual_card_id':'C','start_seconds':st,'perceptual_hit_seconds':hit,'end_seconds':en,'attention_priority':'PRIMARY','card_rest_position_norm':[x,.493],'planned_rect_norm':[x-.08,.41,.16,.18],'source_bbox_norm':[0,0,.16,.18],'layout_scale_multiplier':1.,'preset_actions':[],'preset_entry':None,'preset_exit':None}
a=e(1,0.,.4,4.8,.487);b=e(2,2.,3.,4.8,.75)
s=_recomposition_optimize([a,b],{'cards':[c]},30.)
assert s['candidates_committed']==1,s
assert a['preset_actions'][0]['name']=='WITHIN_MIDDLE_TO_LEFT',a
assert a['premium_within_frame_recomposition'] is True,a
print('V31_0_21_RECOMPOSITION_OPTIMIZER_PASS')
