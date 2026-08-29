from hexa_v31.visual_density import build_visual_density_report

def event(eid, rect):
    return {'event_id':eid,'visual_card_id':'C1','start_seconds':0.0,'end_seconds':4.0,
            'settled_start_seconds':0.0,'settled_end_seconds':4.0,
            'card_rest_position_norm':[rect[0]+rect[2]/2,rect[1]+rect[3]/2],
            'source_bbox_norm':[0,0,rect[2],rect[3]],'reference_camera_scale':1.0,
            'layout_scale_multiplier':1.0,'attention_priority':'PRIMARY' if eid=='A' else 'SUPPORTING',
            'matting':{'opaque_foreground_fraction':0.62},'suppressed_by_card_density':False,
            'preset_actions':[]}

card={'card_id':'C1','start_seconds':0.0,'end_seconds':4.0,'duration_seconds':4.0,
      'constraint_layout':{'placements':{'A':{'rect_norm':[.08,.16,.38,.56]},'B':{'rect_norm':[.54,.20,.36,.50]}}},
      'universal_scene_grammar':{'archetype':'COMPARISON'}}
events=[event('A',[.08,.16,.38,.56]),event('B',[.54,.20,.36,.50])]
plan={'visual_cards':{'cards':[card]},'events':events}
a=build_visual_density_report(plan);b=build_visual_density_report(plan)
assert a==b,(a,b)
assert a['version']=='31.0.25',a
assert a['visible_ink_authority']=='HEXA_PROJECTED_VISIBLE_INK_V1',a
assert a['pass'],a
assert a['active_object_count']==2 and a['cards'][0]['peak_visible_object_count']==2
assert a['cards'][0]['median_safe_frame_union_coverage']>=.35
under={'visual_cards':{'cards':[card]},'events':[events[0],dict(events[1],suppressed_by_card_density=True)]}
u=build_visual_density_report(under)
assert not u['pass'] and u['hard_under_density_cards']==['C1']
print('V31_0_9_VISUAL_DENSITY_PASS')
