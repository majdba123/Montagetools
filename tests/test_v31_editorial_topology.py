from __future__ import annotations
import copy,pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.composition_solver import _progressive_plan,solve_phase_layouts

def event(eid,x,role='PRIMARY',semantic_role='PRIMARY'):
    return {'event_id':eid,'semantic_unit_id':eid,'semantic_scope_id':eid,
            'scene_id':'GENERIC_SCENE','attention_priority':role,
            'semantic_role':semantic_role,'render_mode':'ROOT_ATOMIC',
            'source_bbox_norm':[x-.055,.43,.11,.16],
            'reference_camera_scale':1.0,'visible_ink_fraction':.8,
            'translation_safe_after_occlusion':True,'animation_safe':True,
            'perceptual_hit_seconds':.8+x}

card={'card_id':'GENERIC_CARD','start_seconds':0.,'end_seconds':4.8}
a,b,c=event('A',.25),event('B',.50,'SUPPORTING','SUPPORTING'),event('C',.75,'SUPPORTING','RESULT')

def compile(archetype,roles,edges=()):
    grammar={'archetype':archetype,'roles':roles,'explicit_edges':list(edges)}
    plan=_progressive_plan(card,copy.deepcopy([a,b,c]),grammar)
    assert plan and plan['phase_count']>=3,plan
    layout=solve_phase_layouts(copy.deepcopy([a,b,c]),grammar,plan)
    assert layout['pass'],layout
    return plan,layout

def phase_scale_factor(layout,event_id,placement):
    """Measure hierarchy from shipping geometry, not deprecated diagnostic metadata."""
    base=float(layout['placements'][event_id]['scale'])
    assert base>1e-9,(event_id,layout['placements'][event_id])
    return float(placement['scale'])/base

flow_edges=[{'source':'A','target':'B'},{'source':'B','target':'C'}]
flow,flow_layout=compile('FLOW_PIPELINE',{'A':'ACTOR','B':'TARGET','C':'RESULT'},flow_edges)
comparison,comparison_layout=compile('COMPARISON',{'A':'LEAD','B':'LEAD','C':'SUPPORT'})
payoff,payoff_layout=compile('RESULT_PAYOFF',{'A':'LEAD','B':'SUPPORT','C':'RESULT'})

# Active topology is semantic: process advances, comparison retains its first
# term, and payoff delays the result until the concluding phase.
assert flow['phases'][0]['event_ids']==['A'],flow
assert 'A' not in flow['phases'][-1]['event_ids'],flow
assert all('A' in phase['event_ids'] for phase in comparison['phases']),comparison
assert 'C' not in payoff['phases'][0]['event_ids'] and payoff['phases'][-1]['focus_event_id']=='C',payoff
signatures={tuple(tuple(p['event_ids']) for p in plan['phases']) for plan in (flow,comparison,payoff)}
assert len(signatures)==3,signatures

# Focus is encoded as actual scale hierarchy, not a metadata-only label.
for plan,layout in ((flow,flow_layout),(comparison,comparison_layout),(payoff,payoff_layout)):
    for phase in plan['phases']:
        placements=layout['phase_placements'][phase['phase_id']]
        focus_id=phase['focus_event_id']
        focus_factor=phase_scale_factor(layout,focus_id,placements[focus_id])
        context_factors=[phase_scale_factor(layout,eid,row) for eid,row in placements.items() if eid!=focus_id]
        if context_factors:assert focus_factor-max(context_factors)>=.10,(phase,placements,focus_factor,context_factors)

# A genuinely solo card must materially claim the frame. Prefer scale expansion,
# but when the stable solve is already at the maximum source-safe scale, a strong
# recenter is the correct material change; forcing more scale would create clipping.
solo_plan={'choreography_authority':'SEMANTIC_ARCHETYPE_TEMPORAL_TOPOLOGY_V2','phases':[{'phase_id':'SOLO_P1','event_ids':['A'],'focus_event_id':'A'}]}
solo_layout=solve_phase_layouts([copy.deepcopy(a)],{'archetype':'HERO_STATEMENT','roles':{'A':'LEAD'}},solo_plan)
solo=solo_layout['phase_placements']['SOLO_P1']['A']
solo_base=solo_layout['placements']['A']
solo_scale_gain=phase_scale_factor(solo_layout,'A',solo)
solo_center_shift=max(abs(float(solo['center_norm'][0])-float(solo_base['center_norm'][0])),abs(float(solo['center_norm'][1])-float(solo_base['center_norm'][1])))
assert solo_layout['pass'] and (solo_scale_gain>1.1 or solo_center_shift>=.08),solo_layout

again,_=compile('FLOW_PIPELINE',{'A':'ACTOR','B':'TARGET','C':'RESULT'},flow_edges)
assert again==flow

presenter=event('PRESENTER',.22,'PRIMARY','PRIMARY');presenter['semantic_type']='MAIN_CHARACTER'
object_actor=event('OBJECT',.55,'PRIMARY','PRIMARY')
support=event('SUPPORT',.78,'SUPPORTING','SUPPORTING')
character_grammar={'archetype':'CHARACTER_EXPLAINS_OBJECT','roles':{'PRESENTER':'NARRATOR','OBJECT':'LEAD','SUPPORT':'SUPPORT'},'explicit_edges':[]}
character=_progressive_plan(card,[presenter,object_actor,support],character_grammar)
assert character['phases'][0]['focus_event_id']=='OBJECT',character
assert character['phases'][0]['event_ids']==['OBJECT'],character
print('V31_EDITORIAL_TOPOLOGY_PASS')
