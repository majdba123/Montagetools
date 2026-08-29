import random
from hexa_v31.composition_solver import solve_card_layout,repair_story_phases
random.seed(3101)
archs=['SINGLE_FOCUS','HUB_AND_SPOKES','CAUSE_EFFECT','CHARACTER_EXPLAINS_OBJECT','COMPARISON','FLOW_PIPELINE','SOURCE_BLOCKER_RESULT']
passed=0
for arch in archs:
 for k in range(80):
  ev=[];roles={};n=random.randint(2,6)
  for i in range(n):
   primary=i<min(2,n);w=random.uniform(.12,.72);h=random.uniform(.12,.68);uid=f'U{i}'
   ev.append({'event_id':uid,'semantic_unit_id':uid,'attention_priority':'PRIMARY' if primary else 'SUPPORTING','source_bbox_norm':[0,0,w,h],'reference_camera_scale':random.uniform(.68,1.0),'source_grouped_detail_count':6 if random.random()<.22 else 1,'perceptual_hit_seconds':.4+i*.55,'semantic_type':'CONCEPT' if primary else 'ICON'})
   roles[uid]='LEAD' if i==0 else ('ACTOR' if primary else 'SUPPORT')
  g={'archetype':arch,'roles':roles,'explicit_edges':[]};card={'card_id':'C','start_seconds':0.0,'end_seconds':4.8}
  p=repair_story_phases(card,ev,g);kept={x for ph in p['phases'] for x in ph['event_ids']};rows=[x for x in ev if x['event_id'] in kept]
  r=solve_card_layout(rows,g,p);assert r['pass'],(arch,k,p,r);passed+=1
print('V31_0_1_LARGE_GEOMETRY_STRESS_PASS',passed)
