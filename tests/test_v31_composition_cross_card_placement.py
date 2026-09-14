import copy
from hexa_v31.composition_solver import certify_cross_card_placements
from hexa_v31.composition_qa import card_motion_conflicts,viewport_clipping_qa


def event(eid,card,start,end):
    return {'event_id':eid,'visual_card_id':card,'render_mode':'ROOT_ATOMIC',
        'source_bbox_norm':[0,0,.22,.3],'visible_ink_fraction':.6,
        'attention_priority':'PRIMARY','composition_role':'LEAD','layout_scale_multiplier':1,
        'card_rest_position_norm':[.5,.52],'planned_rect_norm':[.39,.37,.22,.3],
        'start_seconds':start,'end_seconds':end,'physical_start_seconds':start,'physical_end_seconds':end,
        'motion_start_seconds':start,'motion_end_seconds':end,'settle_seconds':start,
        'preset_entry':None,'preset_exit':None,'preset_actions':[],
        'translation_safe_after_occlusion':False,'animation_safe':False,
        'composition_states':[{'state_id':eid+'::A','start_seconds':start,'transition_duration_seconds':0,
            'center_norm':[.5,.52],'scale_multiplier':1,'visibility':1,'translation_safe':False}]}


events=[event('OUTGOING','EARLIER_CARD',0,3),event('INCOMING','LATER_CARD',2,5)]
cards={'cards':[{'card_id':'EARLIER_CARD','start_seconds':0,'end_seconds':2.5},
                {'card_id':'LATER_CARD','start_seconds':2.5,'end_seconds':5}]}
before=copy.deepcopy(events)
assert card_motion_conflicts(events,0,5,30)
report=certify_cross_card_placements(events,cards,30)
assert report['pass'] and report['repairs'],report
assert not card_motion_conflicts(events,0,5,30),events
assert viewport_clipping_qa(events,30)['pass']
for old,new in zip(before,events):
    for key in ('start_seconds','end_seconds','physical_start_seconds','physical_end_seconds',
                'motion_start_seconds','motion_end_seconds','preset_entry','preset_exit','preset_actions',
                'render_mode','translation_safe_after_occlusion','animation_safe'):
        assert old[key]==new[key],(key,old,new)
    assert new['layout_scale_multiplier']<=old['layout_scale_multiplier']
    assert new['composition_states'][0]['center_norm']==new['card_rest_position_norm']
again=certify_cross_card_placements(events,cards,30)
assert not again['repairs'],again
print('V31_COMPOSITION_CROSS_CARD_PLACEMENT_PASS')
