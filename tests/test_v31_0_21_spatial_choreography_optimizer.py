from hexa_v31.preset_story_planner import _spatial_choreography_optimize

c={'card_id':'C','start_seconds':0.,'end_seconds':5.,'duration_seconds':5.}
e={'event_id':'P','visual_card_id':'C','start_seconds':1.,'end_seconds':4.8,'attention_priority':'PRIMARY','planned_rect_norm':[.4,.4,.2,.2],
   'card_rest_position_norm':[.5,.5],'source_bbox_norm':[0,0,.2,.2],'layout_scale_multiplier':1.,'preset_actions':[],
   'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':1.,'duration_seconds':.8},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':4.2,'duration_seconds':.6}}
old_hit=e['preset_entry']['start_seconds']+.55*e['preset_entry']['duration_seconds']
s=_spatial_choreography_optimize([e],{'cards':[c]},30.)
assert s['candidates_committed']==1,s
assert e['preset_entry']['name']=='ENTRY_LEFT_TO_MIDDLE',e
assert abs(e['preset_entry']['start_seconds']+.72*e['preset_entry']['duration_seconds']-old_hit)<1e-5,e
assert e['premium_spatial_handoff']=='ENTRY_AND_EXIT',e
print('V31_0_21_SPATIAL_CHOREOGRAPHY_OPTIMIZER_PASS')
