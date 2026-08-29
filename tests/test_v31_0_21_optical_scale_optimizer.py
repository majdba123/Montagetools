from hexa_v31.preset_story_planner import _optical_scale_optimize

card={'card_id':'C','start_seconds':0.,'end_seconds':4.,'duration_seconds':4.}
e={'event_id':'P','visual_card_id':'C','start_seconds':0.,'end_seconds':4.,'attention_priority':'PRIMARY','planned_rect_norm':[.40,.35,.20,.25],
   'collision_envelope_rect_norm':[.40,.35,.20,.25],'card_rest_position_norm':[.5,.475],'source_bbox_norm':[0,0,.20,.25],'layout_scale_multiplier':1.,
   'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':0.,'duration_seconds':.8},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':3.4,'duration_seconds':.6},'preset_actions':[]}
stats=_optical_scale_optimize([e],{'cards':[card]},30.)
assert stats['candidates_committed']==1,stats
assert e['layout_scale_multiplier']>1.0,e
assert e['premium_optical_scale_factor']>=1.08,e
print('V31_0_21_OPTICAL_SCALE_OPTIMIZER_PASS')
