from hexa_v31.preset_story_planner import _finalize_secondary_character_geometry
from hexa_v31.composition_solver import _in_safe

event={'event_id':'EDGE_CHARACTER','semantic_type':'SECONDARY_CHARACTER','semantic_role':'SUPPORTING','source_bbox_norm':[.638158,.281615,.310407,.569607],'source_center_norm':[.793361,.566419],'card_rest_position_norm':[.793361,.566419],'layout_scale_multiplier':1.25,'planned_rect_norm':[.60,.20,.44,.80]}
changed=_finalize_secondary_character_geometry([event])
assert changed==['EDGE_CHARACTER']
assert _in_safe(event['planned_rect_norm']),event
assert event['layout_scale_multiplier']>=1.20,event
assert event['card_rest_position_norm'][0]<.793361,event
assert event['final_settled_geometry_authority']=='SECONDARY_CHARACTER_SAFE_ENVELOPE'
print('V31_SECONDARY_CHARACTER_SAFE_GEOMETRY_PASS')
