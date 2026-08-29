from hexa_v31.composition_solver import solve_card_layout,_in_safe
e={'event_id':'BIG_SUPPORT','semantic_unit_id':'BIG_SUPPORT','attention_priority':'SUPPORTING','source_bbox_norm':[0,0,.72,.68],'reference_camera_scale':1.0,'source_grouped_detail_count':6}
g={'archetype':'CHARACTER_EXPLAINS_OBJECT','roles':{'BIG_SUPPORT':'SUPPORT'},'explicit_edges':[]}
p={'phases':[{'phase_id':'P','event_ids':['BIG_SUPPORT']}]}
r=solve_card_layout([e],g,p);assert r['pass'],r
rect=tuple(r['placements']['BIG_SUPPORT']['rect_norm']);assert _in_safe(rect),rect
print('V31_0_1_LARGE_SUPPORT_CENTER_FALLBACK_PASS',r['placements']['BIG_SUPPORT'])
