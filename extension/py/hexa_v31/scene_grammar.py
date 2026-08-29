from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable


def _norm(v):
    return str(v or '').strip().upper().replace(' ','_').replace('-','_').replace('/','_')


def _metadata_text(e:dict)->str:
    vals=[e.get('semantic_type'),e.get('semantic_role'),e.get('narrative_function'),e.get('semantic_intent'),e.get('relationship')]
    return ' '.join(_norm(v) for v in vals if v)


def _semantic_id(e:dict)->str:
    return str(e.get('semantic_scope_id') or e.get('semantic_unit_id') or e.get('identity_key') or e.get('event_id') or '')


def _explicit_edges(source_scenes:list[dict])->list[dict]:
    edges=[]
    seen=set()
    for scene in source_scenes:
        scene_id=str(scene.get('scene_id') or '')
        def scoped(unit_id):return (scene_id+'::'+str(unit_id)) if scene_id else str(unit_id)
        units={str(u.get('unit_id')):u for u in (scene.get('units') or []) if u.get('unit_id')}
        for row in scene.get('visual_progression') or []:
            if not isinstance(row,dict):
                continue
            ids=[str(x) for x in (row.get('targets') or []) if x]
            for a,b in zip(ids,ids[1:]):
                k=(a,b,'DECLARED_VISUAL_PROGRESSION')
                if a!=b and k not in seen:
                    seen.add(k);edges.append({'source':a,'target':b,'source_scope_id':scoped(a),'target_scope_id':scoped(b),'scene_id':scene_id or None,'authority':'DECLARED_VISUAL_PROGRESSION','confidence':1.0,'causal':False})
        for sid,u in units.items():
            tgt=u.get('interaction_target') or u.get('target_unit_id') or u.get('relationship_target')
            if tgt and str(tgt) in units:
                k=(sid,str(tgt),'EXPLICIT_INTERACTION_TARGET')
                if k not in seen:
                    seen.add(k);edges.append({'source':sid,'target':str(tgt),'source_scope_id':scoped(sid),'target_scope_id':scoped(tgt),'scene_id':scene_id or None,'authority':'EXPLICIT_INTERACTION_TARGET','confidence':1.0,'causal':True})
    return edges


def _role_map(events:list[dict], edges:list[dict])->dict[str,str]:
    role={_semantic_id(e):'SUPPORT' for e in events}
    for e in events:
        sid=_semantic_id(e);typ=_norm(e.get('semantic_type'));semrole=_norm(e.get('semantic_role'));text=_metadata_text(e)
        if typ=='MAIN_CHARACTER':role[sid]='NARRATOR'
        elif typ=='SECONDARY_CHARACTER':role[sid]='ACTOR'
        elif semrole=='PRIMARY':role[sid]='LEAD'
        if any(k in text for k in ('BLOCK','ERROR','FAIL','DENY','GATE','LIMIT','STOP','REJECT')):role[sid]='BLOCKER'
        elif any(k in text for k in ('RESULT','STATUS','NUMBER','PRICE','LABEL','OUTCOME','SUCCESS')) and role[sid]=='SUPPORT':role[sid]='RESULT'
    confidence={_semantic_id(e):float(e.get('semantic_mapping_confidence') or 0.0) for e in events}
    for ed in edges:
        s=str(ed.get('source_scope_id') or ed['source']);t=str(ed.get('target_scope_id') or ed['target'])
        # A relationship may be semantically explicit while the flat-image component mapping is
        # uncertain. Never let that uncertainty become a spatial role assignment.
        if confidence.get(s,0.0)<0.85 or confidence.get(t,0.0)<0.85:continue
        if s in role and role[s] in {'SUPPORT','LEAD'}:role[s]='ACTOR'
        if t in role and role[t]=='SUPPORT':role[t]='TARGET' if ed.get('causal') else 'RESULT'
    return role


def _has_character(events:list[dict])->bool:
    return any(_norm(e.get('semantic_type')) in {'MAIN_CHARACTER','SECONDARY_CHARACTER'} for e in events)


def _primary_ids(events:list[dict])->list[str]:
    out=[]
    for e in events:
        if _norm(e.get('semantic_role'))=='PRIMARY' or _norm(e.get('semantic_type')) in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}:
            sid=_semantic_id(e)
            if sid not in out:out.append(sid)
    return out


def _chain_length(edges:list[dict])->int:
    if not edges:return 0
    adj={}
    for e in edges:adj.setdefault(str(e.get('source_scope_id') or e['source']),set()).add(str(e.get('target_scope_id') or e['target']))
    best=1
    def dfs(n,seen):
        nonlocal best
        best=max(best,len(seen))
        for m in adj.get(n,()):
            if m not in seen:dfs(m,seen|{m})
    for n in adj:dfs(n,{n})
    return best


def classify_card(card:dict, events:list[dict], source_scenes:list[dict])->dict:
    """Classify a visual card using only structural/semantic metadata.

    No topic words, project IDs, scene numbers, or current-script literals participate.
    The result is a universal composition grammar used by the V31 constraint solver.
    """
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    edges=_explicit_edges(source_scenes)
    roles=_role_map(active,edges)
    prim=_primary_ids(active)
    chain=_chain_length(edges)
    blockers=[sid for sid,r in roles.items() if r=='BLOCKER']
    characters=[_semantic_id(e) for e in active if _norm(e.get('semantic_type')) in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}]

    if blockers and edges:
        archetype='SOURCE_BLOCKER_RESULT'
    elif chain>=3:
        archetype='FLOW_PIPELINE'
    elif _has_character(active) and len(active)>=2:
        archetype='CHARACTER_EXPLAINS_OBJECT'
    elif len(prim)>=2 and not edges:
        archetype='COMPARISON'
    elif edges:
        archetype='CAUSE_EFFECT'
    elif len(prim)==1 and len(active)>=4:
        archetype='HUB_AND_SPOKES'
    else:
        archetype='SINGLE_FOCUS'

    return {
        'schema':'HEXA_UNIVERSAL_SCENE_GRAMMAR_V31','version':'31.0.9',
        'card_id':card.get('card_id'),'archetype':archetype,'roles':roles,'explicit_edges':edges,
        'primary_ids':prim,'character_ids':characters,'blocker_ids':blockers,'chain_length':chain,
        'topic_specific_rules':False,
        'authority':'SEMANTIC_STRUCTURE_ONLY__NO_SCRIPT_SPECIFIC_LAYOUT_RULES',
    }
