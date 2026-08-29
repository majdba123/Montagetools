from hexa_v31.composition_solver import build_story_phases,_fp
card={'card_id':'C','start_seconds':0.0,'end_seconds':4.8}
def e(i,b):return {'event_id':f'E{i}','semantic_unit_id':f'U{i}','attention_priority':'PRIMARY' if i==1 else 'SUPPORTING','source_bbox_norm':b,'reference_camera_scale':1.0,'source_grouped_detail_count':6 if i in (1,2) else 1,'perceptual_hit_seconds':i*.4,'semantic_type':'CONCEPT'}
ev=[e(1,[0,0,.55,.55]),e(2,[0,0,.52,.50]),e(3,[0,0,.12,.12])]
g={'archetype':'SINGLE_FOCUS','roles':{'U1':'LEAD','U2':'SUPPORT','U3':'SUPPORT'},'explicit_edges':[]}
p=build_story_phases(card,ev,g)
atomic={x['event_id'] for x in ev if _fp(x).atomic}
assert atomic=={'E1','E2'}
assert any(atomic.issubset(set(ph['event_ids'])) for ph in p['phases']),p
assert all(set(ph['event_ids']).issubset({'E1','E2','E3'}) for ph in p['phases'])
print('V31_ATOMIC_COMPOSITE_COEXISTENCE_PASS')
