from hexa_v31.composition_qa import composition_plan_qa
# Two primaries deliberately occupy the same middle point while both visible. The hard QA
# must reject it even though the data shape itself is syntactically valid.
def e(i):
    return {'event_id':f'E{i}','visual_card_id':'C','attention_priority':'PRIMARY','source_bbox_norm':[0,0,.24,.28],'reference_camera_scale':1.0,'layout_scale_multiplier':1.0,'card_rest_position_norm':[.5,.52],'start_seconds':0,'end_seconds':4,'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':.1,'duration_seconds':.8},'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':3.1,'duration_seconds':.8},'preset_actions':[]}
m={'fps':30,'visual_cards':{'cards':[{'card_id':'C','start_seconds':0,'end_seconds':4,'story_phase_plan':{'phases':[{'phase_id':'P','event_ids':['E1','E2']}]}}]},'events':[e(1),e(2)]}
q=composition_plan_qa(m);assert not q['pass'] and q['bad_pair_count']>0,q
assert any('overlap' in x for x in q['failures'])
print('V31_MOTION_PATH_COLLISION_GUARD_PASS')
