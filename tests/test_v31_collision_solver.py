from hexa_v31.composition_solver import solve_card_layout, overlap_ratio, _fp, _rect, _in_safe

def e(i,primary,bbox):
    return {'event_id':f'E{i}','semantic_unit_id':f'U{i}','attention_priority':'PRIMARY' if primary else 'SUPPORTING','source_bbox_norm':bbox,'reference_camera_scale':1.0,'source_grouped_detail_count':1}
evs=[e(1,True,[.1,.1,.32,.42]),e(2,False,[.1,.1,.18,.18]),e(3,False,[.1,.1,.16,.16]),e(4,False,[.1,.1,.15,.15])]
g={'archetype':'HUB_AND_SPOKES','roles':{'U1':'LEAD','U2':'SUPPORT','U3':'SUPPORT','U4':'SUPPORT'}}
ph={'phases':[{'phase_id':'P1','event_ids':['E1']},{'phase_id':'P2','event_ids':['E1','E2','E3','E4']}]}
r=solve_card_layout(evs,g,ph);assert r['pass'],r
for p in r['placements'].values():assert _in_safe(tuple(p['rect_norm'])),p
rows=[(k,tuple(v['rect_norm'])) for k,v in r['placements'].items()]
for i,(a,ra) in enumerate(rows):
    for b,rb in rows[i+1:]:
        if a=='E1' or b=='E1' or (a in {'E2','E3','E4'} and b in {'E2','E3','E4'}):
            assert overlap_ratio(ra,rb)<1e-8,(a,b,ra,rb)
print('V31_COLLISION_SOLVER_PASS')
