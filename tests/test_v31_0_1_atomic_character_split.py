from hexa_v31.composition_solver import build_story_phases,_fp
card={'card_id':'C','start_seconds':0.0,'end_seconds':4.8}
def e(i,typ):return {'event_id':f'E{i}','semantic_unit_id':f'U{i}','attention_priority':'PRIMARY','source_bbox_norm':[0,0,.58,.66],'reference_camera_scale':1.0,'source_grouped_detail_count':6,'perceptual_hit_seconds':i*.5,'semantic_type':typ}
ev=[e(1,'CONCEPT'),e(2,'MAIN_CHARACTER')]
g={'archetype':'CHARACTER_EXPLAINS_OBJECT','roles':{'U1':'LEAD','U2':'NARRATOR'},'explicit_edges':[]}
p=build_story_phases(card,ev,g)
assert any(set(ph['event_ids'])=={'E1','E2'} for ph in p['phases']),p
print('V31_0_3_ATOMIC_CHARACTER_COEXISTENCE_PASS',p)
