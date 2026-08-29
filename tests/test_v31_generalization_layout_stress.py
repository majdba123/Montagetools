import random
from hexa_v31.composition_solver import solve_card_layout, overlap_ratio, _in_safe
random.seed(3100)
archs=['SINGLE_FOCUS','HUB_AND_SPOKES','CAUSE_EFFECT','CHARACTER_EXPLAINS_OBJECT','COMPARISON','FLOW_PIPELINE','SOURCE_BLOCKER_RESULT']
passed=0
for arch in archs:
    for k in range(50):
        ev=[];roles={}
        nprim=2 if arch in {'COMPARISON','CHARACTER_EXPLAINS_OBJECT'} else 1
        for i in range(nprim):
            uid=f'P{i}';w=random.uniform(.12,.24);h=random.uniform(.14,.30)
            ev.append({'event_id':uid,'semantic_unit_id':uid,'attention_priority':'PRIMARY','source_bbox_norm':[0,0,w,h],'reference_camera_scale':random.uniform(.70,1.0),'source_grouped_detail_count':1})
            roles[uid]='LEAD' if i==0 else 'ACTOR'
        for i in range(3):
            uid=f'S{i}';w=random.uniform(.06,.14);h=random.uniform(.06,.16)
            ev.append({'event_id':uid,'semantic_unit_id':uid,'attention_priority':'SUPPORTING','source_bbox_norm':[0,0,w,h],'reference_camera_scale':random.uniform(.70,1.0),'source_grouped_detail_count':1})
            roles[uid]='SUPPORT'
        ids=[e['event_id'] for e in ev]
        r=solve_card_layout(ev,{'archetype':arch,'roles':roles},{'phases':[{'phase_id':'P','event_ids':ids}]})
        assert r['pass'],(arch,k,r)
        rects=[tuple(v['rect_norm']) for v in r['placements'].values()]
        assert all(_in_safe(x) for x in rects),(arch,k,rects)
        for i,a in enumerate(rects):
            for b in rects[i+1:]:assert overlap_ratio(a,b)<1e-8,(arch,k,a,b)
        passed+=1
print('V31_GENERALIZATION_LAYOUT_STRESS_PASS',passed)
