from hexa_v31.composition_solver import repair_story_phases,solve_card_layout,_fp
card={'card_id':'C','start_seconds':0.0,'end_seconds':4.7}
def e(i,w,h,primary,typ='ICON'):
 return {'event_id':f'E{i}','semantic_unit_id':f'U{i}','attention_priority':'PRIMARY' if primary else 'SUPPORTING','source_bbox_norm':[0,0,w,h],'reference_camera_scale':1.0,'source_grouped_detail_count':6 if w>.5 else 1,'perceptual_hit_seconds':.5+i*.55,'semantic_type':typ}
ev=[e(1,.58,.62,True,'CONCEPT'),e(2,.54,.64,True,'MAIN_CHARACTER'),e(3,.42,.46,False),e(4,.22,.20,False),e(5,.18,.18,False)]
g={'archetype':'CHARACTER_EXPLAINS_OBJECT','roles':{'U1':'LEAD','U2':'NARRATOR','U3':'SUPPORT','U4':'SUPPORT','U5':'SUPPORT'},'explicit_edges':[]}
p=repair_story_phases(card,ev,g)
kept={x for ph in p['phases'] for x in ph['event_ids']};rows=[x for x in ev if x['event_id'] in kept]
r=solve_card_layout(rows,g,p);assert r['pass'],(p,r)
for ph in p['phases']:
 q=[x for x in rows if x['event_id'] in ph['event_ids']]
 assert sum(1 for x in q if x['attention_priority']=='PRIMARY')<=2
print('V31_0_3_ADAPTIVE_PHASE_RECOVERY_PASS',p)
