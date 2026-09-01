from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import math

@dataclass
class StoryNode:
    node_id: str
    physical_id: str
    semantic_unit_id: str | None
    semantic_type: str
    semantic_role: str
    narrative_function: str
    semantic_intent: str
    center_norm: tuple[float,float]
    bbox_norm: tuple[float,float,float,float]
    hierarchy_level: int
    subobject_role: str
    animation_safe: bool
    reveal_safe: bool
    animation_mode: str
    occlusion_class: str
    appear_time: float | None = None
    focus_time: float | None = None

@dataclass
class StoryEdge:
    source: str
    target: str
    relation: str
    authority: str
    priority: int
    confidence: float
    causal: bool
    actionable: bool
    action_mode: str


def _norm(v:Any)->str:
    return str(v or '').strip().upper().replace(' ','_').replace('-','_').replace('/','_')


def _sem_map(scene:dict)->dict[str,dict]:
    return {str(u.get('unit_id')):u for u in (scene.get('units') or []) if u.get('unit_id')}


def _representative(nodes:list[StoryNode],sem_id:str,*,prefer_role:str|None=None)->StoryNode|None:
    cand=[n for n in nodes if str(n.semantic_unit_id or '')==str(sem_id)]
    if not cand:return None
    if prefer_role:
        pr=[n for n in cand if n.subobject_role==prefer_role]
        if pr:return sorted(pr,key=lambda n:n.bbox_norm[2]*n.bbox_norm[3],reverse=True)[0]
    return sorted(cand,key=lambda n:(0 if n.animation_safe else 1,0 if n.reveal_safe else 1,-n.bbox_norm[2]*n.bbox_norm[3]))[0]


def _spatial_order(nodes:list[StoryNode])->tuple[list[StoryNode],str,float]:
    if len(nodes)<2:return nodes,'X',0.0
    xs=[n.center_norm[0] for n in nodes];ys=[n.center_norm[1] for n in nodes];xr=max(xs)-min(xs);yr=max(ys)-min(ys);axis='X' if xr>=yr else 'Y';spread=max(xr,yr)
    return sorted(nodes,key=lambda n:n.center_norm[0] if axis=='X' else n.center_norm[1]),axis,spread


def _ordered(nodes:list[StoryNode])->tuple[list[StoryNode],str,float]:
    timed=[n for n in nodes if n.appear_time is not None]
    if len(timed)>=2:
        ts=[float(n.appear_time) for n in timed]
        if max(ts)-min(ts)>=0.08:
            return sorted(nodes,key=lambda n:(10**9 if n.appear_time is None else float(n.appear_time),n.center_norm[0],n.center_norm[1])),'NARRATION_TIME',max(ts)-min(ts)
    role_rank={'CONTEXT':0,'ACTOR':1,'TARGET':2,'RESULT':3,'':4}
    if any(n.subobject_role in {'ACTOR','TARGET','RESULT'} for n in nodes):
        return sorted(nodes,key=lambda n:(role_rank.get(n.subobject_role,4),n.center_norm[0],n.center_norm[1])),'MOTION_ROLE',_spatial_order(nodes)[2]
    return _spatial_order(nodes)


def _causal_hint(scene:dict,sems:list[dict])->bool:
    rel=_norm(scene.get('relation_to_previous'))
    if rel in {'CAUSE_EFFECT','CAUSE','FLOW','PROCESS','TRANSFER','RESOLVE'}:return True
    vals=[]
    for s in sems:vals.extend([_norm(s.get('narrative_function')),_norm(s.get('semantic_intent')),_norm(s.get('relationship'))])
    stems=('CAUSE','EFFECT','FLOW','TRANSFER','PROCESS','REQUEST','RESPONSE','RESULT','STATE_CHANGE','SEQUENCE','SEND','RECEIVE')
    return any(any(st in v for st in stems) for v in vals if v)


def _progression_targets(scene:dict)->list[list[str]]:
    out=[]
    for row in scene.get('visual_progression') or []:
        if not isinstance(row,dict):continue
        t=[str(x) for x in (row.get('targets') or []) if x]
        if t:out.append(t)
    return out


def _add_edge(edges:list[StoryEdge],edge:StoryEdge):
    if edge.source==edge.target:return
    for i,e in enumerate(edges):
        if e.source==edge.source and e.target==edge.target:
            if edge.priority>e.priority:edges[i]=edge
            return
    edges.append(edge)


def _transfer_geometry_feasible(src:StoryNode,tgt:StoryNode)->bool:
    """Return True only when a real Position transfer can be shown without collision/teleport.

    V31.0.1 classified TRANSFER from semantic safety alone. On real projects this produced
    causal TRANSFER edges whose objects were already touching/overlapping, so the state compiler
    correctly refused to move them and pre-render QA failed. V31.0.1 makes geometry part of the
    single story truth: TRANSFER means a legal, visible spatial travel is physically available.
    """
    if not (src.animation_safe and src.animation_mode=='TRANSLATE_SAFE'):return False
    sx,sy=src.center_norm;tx,ty=tgt.center_norm;vx,vy=tx-sx,ty-sy;dist=math.hypot(vx,vy)
    if dist<0.08:return False
    ux,uy=vx/dist,vy/dist
    sb=src.bbox_norm;tb=tgt.bbox_norm
    src_extent=abs(ux)*sb[2]*0.5+abs(uy)*sb[3]*0.5
    tgt_extent=abs(ux)*tb[2]*0.5+abs(uy)*tb[3]*0.5
    free=max(0.0,dist-src_extent-tgt_extent)
    breathing=max(0.008,min(src_extent,tgt_extent)*0.10)
    travel=max(0.0,free-breathing)
    return travel>=0.035


def _mode_for(src:StoryNode,tgt:StoryNode,causal:bool,scene_duration_seconds:float|None=None)->str:
    # A legal Position move needs >=12 frames plus enough time to establish the object first.
    # Short beats still tell a causal story through staged reveal/handoff instead of an impossible
    # or rushed transfer. This is generic and independent of scene/topic IDs.
    duration_ok=scene_duration_seconds is None or float(scene_duration_seconds)>=1.55
    if causal and duration_ok and _transfer_geometry_feasible(src,tgt):return 'TRANSFER'
    if tgt.reveal_safe or src.reveal_safe:return 'REVEAL_HANDOFF'
    return 'ATTENTION_HANDOFF'


def build_semantic_object_graph(scene:dict,physical_units:list[dict],trigger_times:dict[str,dict[str,float|None]]|None=None,scene_duration_seconds:float|None=None)->dict:
    """Build one single source of truth for semantic acting.

    V31 separates *causality* from *actionability*. A scene may deserve visual acting even when
    the package does not declare a causal relationship. This closes V26's zero-story gap without
    inventing false cause/effect: explicit/strong structural evidence can create TRANSFER edges;
    narration/progression/hierarchy can create REVEAL_HANDOFF edges that still produce a temporal
    story. No topic words, project IDs, scene numbers, or payment-specific rules participate.
    """
    sem_by_id=_sem_map(scene);nodes=[]
    for p in physical_units or []:
        sid=str(p.get('semantic_unit_id') or '');sem=sem_by_id.get(sid,{});tt=(trigger_times or {}).get(sid) or {};pid=str(p.get('physical_id') or f'PHYS_{len(nodes)+1:02d}')
        nodes.append(StoryNode(
            node_id=pid,physical_id=pid,semantic_unit_id=sid or None,semantic_type=_norm(p.get('semantic_type') or sem.get('type')),semantic_role=_norm(p.get('semantic_role') or sem.get('role')),narrative_function=_norm(sem.get('narrative_function')),semantic_intent=_norm(sem.get('semantic_intent')),
            center_norm=tuple(float(x) for x in (p.get('center_norm') or [0.5,0.5])[:2]),bbox_norm=tuple(float(x) for x in (p.get('bbox_norm') or [0.25,0.25,0.5,0.5])[:4]),hierarchy_level=int(p.get('hierarchy_level') or 0),subobject_role=_norm(p.get('subobject_role')), 
            animation_safe=bool(p.get('translation_safe_after_occlusion',p.get('animation_safe',True))),reveal_safe=bool(p.get('reveal_safe',True)),animation_mode=_norm(p.get('animation_mode') or ('TRANSLATE_SAFE' if p.get('translation_safe_after_occlusion',p.get('animation_safe',True)) else 'GROUP_ONLY')),occlusion_class=_norm(p.get('occlusion_class') or ('CLEAN_SEPARABLE' if p.get('translation_safe_after_occlusion',p.get('animation_safe',True)) else 'GROUP_ONLY')),appear_time=tt.get('appear'),focus_time=tt.get('focus')
        ))
    edges=[]

    # 1) Explicit package interaction is absolute authority.
    for sid,sem in sem_by_id.items():
        tgt=str(sem.get('interaction_target') or '')
        if not tgt:continue
        src=_representative(nodes,sid,prefer_role='ACTOR') or _representative(nodes,sid);dst=_representative(nodes,tgt,prefer_role='TARGET') or _representative(nodes,tgt)
        if src and dst:_add_edge(edges,StoryEdge(src.node_id,dst.node_id,_norm(sem.get('relationship') or sem.get('narrative_function') or 'INTERACTION'),'EXPLICIT_INTERACTION_TARGET',100,1.0,True,True,_mode_for(src,dst,True,scene_duration_seconds)))

    # 2) Declared visual progression is a temporal story authority. It is not silently upgraded to causality.
    for targets in _progression_targets(scene):
        reps=[_representative(nodes,sid) for sid in targets];reps=[x for x in reps if x]
        for a,b in zip(reps,reps[1:]):_add_edge(edges,StoryEdge(a.node_id,b.node_id,'DECLARED_PROGRESSION','DECLARED_VISUAL_PROGRESSION',88,0.96,False,True,_mode_for(a,b,False,scene_duration_seconds)))

    # 3) Hierarchical children are an animation sequence even without causal vocabulary.
    # Connected children become reveal-only; only physically detached children can travel.
    by_sem={}
    for n in nodes:
        if n.semantic_unit_id:by_sem.setdefault(n.semantic_unit_id,[]).append(n)
    for sid,grp in by_sem.items():
        children=[n for n in grp if n.hierarchy_level>0 and n.reveal_safe]
        if len(children)<2:continue
        ordered,axis,spread=_ordered(children);sem=sem_by_id.get(str(sid),{});causal=_causal_hint(scene,[sem]) and spread>=0.09
        for a,b in zip(ordered,ordered[1:]):
            if causal:
                conf=min(0.90,0.70+min(0.18,spread*0.45));auth='HIERARCHICAL_PROCESS_INFERENCE';rel='INFERRED_SUBOBJECT_FLOW'
            else:
                conf=min(0.86,0.66+min(0.16,spread*0.38));auth='HIERARCHICAL_TEMPORAL_SEQUENCE';rel='SUBOBJECT_STORY_SEQUENCE'
            _add_edge(edges,StoryEdge(a.node_id,b.node_id,rel,auth,82 if causal else 74,round(conf,3),causal,True,_mode_for(a,b,causal,scene_duration_seconds)))

    # 4) Distinct semantic units: narration order itself is enough for a story handoff.
    # It becomes causal only when the scene metadata independently says process/flow.
    reps=[]
    for sid in sem_by_id:
        n=_representative(nodes,sid,prefer_role='ACTOR') or _representative(nodes,sid)
        if n and n.reveal_safe:reps.append(n)
    if len(reps)>=2:
        ordered,axis,spread=_ordered(reps);causal=_causal_hint(scene,list(sem_by_id.values())) and spread>=0.12
        timed=[n for n in ordered if n.appear_time is not None];timed_distinct=len(timed)>=2 and max(float(n.appear_time) for n in timed)-min(float(n.appear_time) for n in timed)>=0.08
        for a,b in zip(ordered[:4],ordered[1:4]):
            # Do not duplicate stronger explicit/hierarchical edges.
            if causal:
                auth='SEMANTIC_NARRATION_CAUSAL_INFERENCE' if timed_distinct else 'SEMANTIC_STRUCTURAL_CAUSAL_INFERENCE';rel='INFERRED_NARRATION_FLOW';priority=70;conf=0.76 if timed_distinct else 0.70
            else:
                auth='SEMANTIC_NARRATION_SEQUENCE' if timed_distinct else 'SEMANTIC_COMPOSITION_SEQUENCE';rel='NARRATION_HANDOFF' if timed_distinct else 'COMPOSITION_HANDOFF';priority=60 if timed_distinct else 46;conf=0.76 if timed_distinct else 0.62
            _add_edge(edges,StoryEdge(a.node_id,b.node_id,rel,auth,priority,conf,causal,True,_mode_for(a,b,causal,scene_duration_seconds)))

    # 5) Last-resort neutral order is non-causal but still useful for staggered entrances.
    if not edges and len(nodes)>=2:
        ordered=sorted([n for n in nodes if n.reveal_safe],key=lambda n:(0 if n.semantic_role=='PRIMARY' else 1,10**9 if n.appear_time is None else n.appear_time,n.center_norm[0],n.center_norm[1]))
        for a,b in zip(ordered,ordered[1:]):_add_edge(edges,StoryEdge(a.node_id,b.node_id,'ATTENTION_HANDOFF','NEUTRAL_VISUAL_ORDER',20,0.55,False,True,'REVEAL_HANDOFF'))

    role_by_node={n.node_id:'CONTEXT' for n in nodes}
    for n in nodes:
        if n.semantic_type=='MAIN_CHARACTER':role_by_node[n.node_id]='NARRATOR'
        elif n.semantic_type=='SECONDARY_CHARACTER':role_by_node[n.node_id]='SECONDARY_ACTOR'
        elif n.semantic_type in {'STATUS','NUMBER','PRICE','LABEL'}:role_by_node[n.node_id]='RESULT'
        elif n.subobject_role in {'ACTOR','TARGET','RESULT','CONTEXT'}:role_by_node[n.node_id]=n.subobject_role
    for e in sorted(edges,key=lambda x:-x.priority):
        if e.actionable and role_by_node.get(e.source,'CONTEXT')=='CONTEXT':role_by_node[e.source]='ACTOR'
        if e.actionable and role_by_node.get(e.target,'CONTEXT')=='CONTEXT':role_by_node[e.target]='TARGET' if e.causal else 'RESULT'

    actionable=[e for e in edges if e.actionable];causal=[e for e in actionable if e.causal]
    eligible=bool(actionable) or len([n for n in nodes if n.reveal_safe])>=2
    reasons=[]
    if causal:reasons.append('CAUSAL_EDGE')
    if any(e.authority=='DECLARED_VISUAL_PROGRESSION' for e in actionable):reasons.append('DECLARED_PROGRESSION')
    if any(n.hierarchy_level>0 for n in nodes):reasons.append('HIERARCHICAL_SUBOBJECTS')
    if any(e.authority in {'SEMANTIC_NARRATION_SEQUENCE','SEMANTIC_COMPOSITION_SEQUENCE','NEUTRAL_VISUAL_ORDER'} for e in actionable):reasons.append('SEMANTIC_SEQUENCE')
    return {
        'schema':'HEXA_SEMANTIC_ACTING_GRAPH_V31','version':'4.0','nodes':[asdict(n)|{'motion_role':role_by_node[n.node_id]} for n in nodes],'edges':[asdict(e) for e in edges],
        'explicit_edge_count':sum(1 for e in edges if e.authority=='EXPLICIT_INTERACTION_TARGET'),'inferred_causal_edge_count':sum(1 for e in causal if e.authority!='EXPLICIT_INTERACTION_TARGET'),'causal_edge_count':len(causal),'actionable_edge_count':len(actionable),'attention_edge_count':sum(1 for e in edges if not e.causal),
        'hierarchical_node_count':sum(1 for n in nodes if n.hierarchy_level>0),'translation_safe_node_count':sum(1 for n in nodes if n.animation_safe),'reveal_only_node_count':sum(1 for n in nodes if n.reveal_safe and not n.animation_safe),
        'story_eligible':eligible,'story_eligibility_reasons':reasons,'topic_specific_rules':False,'inference_policy':'SINGLE_STORY_TRUTH__CONTEXT_ESTABLISH__ROLE_DRIVEN_SUBOBJECT_SEQUENCE__EXPLICIT_OR_GENERIC_STRUCTURAL_CAUSALITY__NO_TOPIC_LEXICON'
    }
