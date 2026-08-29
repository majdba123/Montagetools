from hexa_v31.visual_choreography import build_visual_choreography_report

def event(i,start,hit,end,primary=False,action=False):
    return {'event_id':f'E{i}','visual_instance_id':f'VI{i}','visual_card_id':'C1','start_seconds':start,'perceptual_hit_seconds':hit,'end_seconds':end,
            'attention_priority':'PRIMARY' if primary else 'SUPPORTING','semantic_type':'OBJECT','card_rest_position_norm':[.35+.2*i,.5],
            'layout_scale_multiplier':1.0,'source_bbox_norm':[0,0,.2,.2],'matting':{'opaque_foreground_fraction':.7},
            'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':start,'duration_seconds':max(.1,hit-start)},
            'preset_actions':[{'name':'WITHIN_MIDDLE_TO_RIGHT','start_seconds':hit+.2,'duration_seconds':.5}] if action else []}

motion={'fps':30,'events':[event(1,0,.3,4,True,True),event(2,.8,1.1,4)],'visual_cards':{'cards':[{'card_id':'C1','start_seconds':0,'end_seconds':4,'duration_seconds':4,'universal_scene_grammar':{'archetype':'CAUSE_EFFECT'}}]}}
text={'opportunity_count':2,'events':[{'text_id':'T1','unit_id':'U1','text':'نتيجة واضحة','style':'STATUS_BADGE','start_seconds':1.1,'end_seconds':2.5,'slot':'MID_RIGHT','semantic_source':'UNIT_TRIGGER_LITERAL_SUBPHRASE'}]}
r=build_visual_choreography_report(motion,text)
assert r['independent_motion_unit_count']==2,r
assert r['typography_unit_count']==1 and r['available_viewer_text_opportunities']==2,r
assert r['progressive_reveal_count']>=1,r
assert r['within_frame_recomposition_count']==1,r
assert r['hard_invariants']['semantic_timing_mutated'] is False,r
print('V31_0_21_VISUAL_CHOREOGRAPHY_DIAGNOSTICS_PASS')
