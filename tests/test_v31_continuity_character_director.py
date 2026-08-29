from hexa_v31.continuity_character import SemanticCharacterDirector,VisualContinuityQA

events=[{'event_id':'P','visual_card_id':'C','semantic_type':'CONCEPT','attention_priority':'PRIMARY','card_rest_position_norm':[.3,.5],'start_seconds':0.,'end_seconds':3.,'source_bbox_norm':[0,0,.2,.2],'matting':{'opaque_foreground_fraction':1.0}}, {'event_id':'C','visual_card_id':'C','semantic_type':'SECONDARY_CHARACTER','semantic_intent':'COMPARE','card_rest_position_norm':[.7,.5],'start_seconds':0.,'end_seconds':3.,'source_bbox_norm':[0,0,.2,.4],'matting':{'opaque_foreground_fraction':1.0}}]
result=SemanticCharacterDirector().direct(events)
assert result['synthetic_character_insertions']==0 and events[1]['character_editorial_purpose']=='COMPARE' and events[1]['character_opposite_half_composition']
plan={'events':events,'visual_cards':{'cards':[{'card_id':'C','start_seconds':0.,'end_seconds':3.,'duration_seconds':3.,'constraint_layout':{'placements':{}},'universal_scene_grammar':{}}]}}
a=VisualContinuityQA().assess(plan);b=VisualContinuityQA().assess(plan);assert a==b and a['handoff_readability_pass']
print('V31_CONTINUITY_CHARACTER_DIRECTOR_PASS')
