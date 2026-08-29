from __future__ import annotations
from dataclasses import dataclass
import itertools, math
from .preset_authority import duration as preset_duration, preset as preset_def
from .projected_visible_ink import ProjectedVisibleInkModel

SAFE_X=(0.08,0.92)
SAFE_Y=(0.10,0.90)
PRIMARY_GAP=0.035
SUPPORT_GAP=0.022
MAX_SETTLED_OCCUPANCY=0.62
TARGET_OCCUPANCY=(0.35,0.56)
# Appearance preset reaches 110% scale and holds there. Layout is therefore solved
# against the real motion envelope, not only the nominal rest rectangle. A small extra
# margin absorbs raster/crop rounding and prevents the V30 'looks clean in plan, overlaps
# in pixels' failure class.
MOTION_ENVELOPE_SCALE=1.12
MIN_PRIMARY_LAYOUT_SCALE=0.40
MIN_SUPPORT_LAYOUT_SCALE=0.32
MIN_ATOMIC_LAYOUT_SCALE=0.30
MAX_PHASE_OBJECTS=5
_VISIBLE_INK_MODEL=ProjectedVisibleInkModel()

@dataclass(frozen=True)
class Footprint:
    event_id:str
    w:float
    h:float
    area:float
    fill:float
    visible_area:float
    primary:bool
    atomic:bool


def _norm(v):return str(v or '').strip().upper()

def _sid(e):return str(e.get('semantic_scope_id') or e.get('semantic_unit_id') or e.get('identity_key') or e.get('event_id'))

def _edge_sid(edge:dict,key:str)->str:
    return str(edge.get(key+'_scope_id') or edge.get(key) or '')

def _fp(e:dict)->Footprint:
    b=e.get('source_bbox_norm') or [0.35,0.30,0.30,0.40]
    w=max(0.035,min(0.92,float(b[2])));h=max(0.035,min(0.90,float(b[3])))
    cam=max(0.55,min(1.15,float(e.get('reference_camera_scale') or 1.0)))
    w*=cam;h*=cam
    # Collision geometry remains a bbox concern, while the solver's density
    # objective uses the source-backed visible support inside that geometry.
    fill=max(0.02,min(1.0,_VISIBLE_INK_MODEL.visible_fraction(e)))
    area=w*h
    visible_area=area*fill
    detail=int(e.get('source_grouped_detail_count') or 0)
    atomic=bool(e.get('composite_atomic')) or w>0.50 or h>0.58 or area>0.16 or detail>=5
    return Footprint(str(e.get('event_id')),w,h,area,fill,visible_area,_norm(e.get('attention_priority'))=='PRIMARY',atomic)

def _rect(center,fp:Footprint,scale:float):
    cx,cy=center;w=fp.w*scale;h=fp.h*scale
    return (cx-w/2,cy-h/2,w,h)

def _inflate(r,g):return (r[0]-g,r[1]-g,r[2]+2*g,r[3]+2*g)

def _inter(a,b):
    x=max(0.0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]));y=max(0.0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]));return x*y

def overlap_ratio(a,b):
    i=_inter(a,b);return i/max(1e-9,min(a[2]*a[3],b[2]*b[3]))

def _in_safe(r):
    return r[0]>=SAFE_X[0]-1e-6 and r[1]>=SAFE_Y[0]-1e-6 and r[0]+r[2]<=SAFE_X[1]+1e-6 and r[1]+r[3]<=SAFE_Y[1]+1e-6

def _slots(archetype:str,role:str)->list[tuple[float,float]]:
    # Slots are semantic destinations, not motion presets. Static placement is legal for
    # appearance/disappearance. Position-travel presets are selected later only if compatible.
    if archetype=='CHARACTER_EXPLAINS_OBJECT':
        if role in {'NARRATOR','ACTOR','LEAD'}:return [(0.27,0.56),(0.50,0.52),(0.73,0.56)]
        return [(0.72,0.30),(0.75,0.70),(0.52,0.24),(0.52,0.78),(0.28,0.26),(0.28,0.78)]
    if archetype=='CAUSE_EFFECT':
        if role in {'ACTOR','LEAD'}:return [(0.50,0.52),(0.27,0.52)]
        if role in {'TARGET','RESULT'}:return [(0.73,0.52),(0.50,0.52)]
        return [(0.50,0.24),(0.50,0.78),(0.24,0.25),(0.76,0.25),(0.24,0.78),(0.76,0.78)]
    if archetype=='SOURCE_BLOCKER_RESULT':
        if role in {'ACTOR','LEAD'}:return [(0.20,0.52),(0.50,0.52)]
        if role=='BLOCKER':return [(0.50,0.52),(0.50,0.28)]
        if role in {'TARGET','RESULT'}:return [(0.80,0.52),(0.50,0.52)]
        return [(0.32,0.25),(0.68,0.25),(0.32,0.78),(0.68,0.78)]
    if archetype=='COMPARISON':
        if role in {'LEAD','ACTOR','TARGET','RESULT','NARRATOR'}:return [(0.28,0.52),(0.72,0.52),(0.50,0.52)]
        return [(0.28,0.25),(0.72,0.25),(0.28,0.78),(0.72,0.78),(0.50,0.22),(0.50,0.80)]
    if archetype=='FLOW_PIPELINE':
        if role in {'LEAD','ACTOR','TARGET','RESULT'}:return [(0.22,0.52),(0.50,0.52),(0.78,0.52)]
        return [(0.22,0.25),(0.50,0.25),(0.78,0.25),(0.22,0.78),(0.50,0.78),(0.78,0.78)]
    if archetype=='HUB_AND_SPOKES':
        if role in {'LEAD','ACTOR','NARRATOR'}:return [(0.38,0.52),(0.50,0.52)]
        return [(0.73,0.27),(0.80,0.52),(0.73,0.76),(0.55,0.24),(0.55,0.80),(0.22,0.28),(0.22,0.76)]
    if role in {'LEAD','ACTOR','NARRATOR','TARGET','RESULT','BLOCKER'}:return [(0.50,0.52),(0.30,0.52),(0.70,0.52)]
    return [(0.73,0.30),(0.73,0.70),(0.27,0.30),(0.27,0.70),(0.50,0.24),(0.50,0.78)]

def _scale_candidates(fp:Footprint,primary:bool)->list[float]:
    """Return deterministic scales that always include a physical safe-frame fit."""
    base=[2.20,2.00,1.80,1.65,1.50,1.38,1.25,1.15,1.08,1.0,0.92,0.84,0.76,0.68,0.60,0.54,0.48,0.42,0.36,0.32]
    safe_w=SAFE_X[1]-SAFE_X[0];safe_h=SAFE_Y[1]-SAFE_Y[0]
    class_cap=2.20 if primary else 1.80
    fit=min(safe_w/max(1e-9,fp.w*MOTION_ENVELOPE_SCALE),safe_h/max(1e-9,fp.h*MOTION_ENVELOPE_SCALE),class_cap)
    floor=MIN_ATOMIC_LAYOUT_SCALE if fp.atomic else (MIN_PRIMARY_LAYOUT_SCALE if primary else MIN_SUPPORT_LAYOUT_SCALE)
    vals=[x for x in base if x<=fit+1e-9 and x>=floor-1e-9]
    # Include scales that deliberately use the canvas. A small source icon should not remain
    # tiny merely because 100% happens to be its authored bitmap scale.
    density_area=0.30 if primary else 0.13
    density_scale=math.sqrt(density_area/max(1e-9,fp.visible_area*MOTION_ENVELOPE_SCALE*MOTION_ENVELOPE_SCALE))
    vals.append(max(floor,min(fit,density_scale)))
    derived=max(0.22,min(class_cap,fit*0.985))
    vals.append(derived)
    if fit<floor:vals.append(max(0.22,fit*0.97))
    out=[]
    for x in vals:
        x=round(float(x),6)
        if x>0 and x not in out:out.append(x)
    return sorted(out,reverse=True)

def _adaptive_slots(archetype:str,role:str,fp:Footprint)->list[tuple[float,float]]:
    """Semantic anchors first; geometry-only universal fallbacks second."""
    preferred=list(_slots(archetype,role))
    generic=[
        (0.50,0.52),(0.50,0.50),(0.34,0.52),(0.66,0.52),
        (0.50,0.31),(0.50,0.73),(0.32,0.31),(0.68,0.31),
        (0.32,0.73),(0.68,0.73),(0.25,0.52),(0.75,0.52),
    ]
    if fp.atomic or fp.w>0.38 or fp.h>0.46:
        generic=[(0.50,0.52),(0.50,0.50),(0.42,0.52),(0.58,0.52),(0.50,0.42),(0.50,0.62)]+generic
    out=[]
    for c in preferred+generic:
        cc=(round(float(c[0]),6),round(float(c[1]),6))
        if cc not in out:out.append(cc)
    return out

def _placement_cost(rect,center,scale,fp,role,archetype,placed):
    if not _in_safe(rect):return 1e6
    cost=max(0.0,1.0-scale)*4.0-max(0.0,scale-1.0)*0.55
    # prefer central focal object but preserve authored semantic topology.
    if fp.primary:cost+=abs(center[1]-0.52)*0.6
    occ=rect[2]*rect[3]*fp.fill
    if occ>0.42:cost+=(occ-0.42)*9.0
    for _,pr,pfp,_ in placed:
        gap=PRIMARY_GAP if (fp.primary or pfp.primary) else SUPPORT_GAP
        if _inter(_inflate(rect,gap),_inflate(pr,gap))>1e-8:return 1e6
    return cost

def solve_static_layout(events:list[dict], grammar:dict)->dict:
    """Backtracking layout solver with hard non-overlap and safe-frame constraints.

    It solves actual object footprints, not point centers. Large composite illustrations are
    treated as atomic and are never packed beside another large composite in the same state.
    """
    roles=grammar.get('roles') or {};arch=str(grammar.get('archetype') or 'SINGLE_FOCUS')
    items=[]
    for e in events:
        if e.get('suppressed_by_card_density'):continue
        fp=_fp(e);role=roles.get(_sid(e),'LEAD' if fp.primary else 'SUPPORT')
        items.append((e,fp,role))
    # Hardest first; this dramatically improves deterministic search quality.
    items.sort(key=lambda z:(0 if z[1].atomic else 1,0 if z[1].primary else 1,-z[1].area,str(z[0].get('event_id'))))
    best=None
    def rec(i,placed,cost):
        nonlocal best
        if best is not None and cost>=best[0]:return
        if i>=len(items):
            occ=sum(r[2]*r[3] for _,r,_,_ in placed)
            # Occupancy is a soft preference because opaque silhouettes may overlap bbox whitespace,
            # but hard pairwise collision already guarantees readable separation.
            c=cost+max(0,occ-TARGET_OCCUPANCY[1])*12.0+max(0,TARGET_OCCUPANCY[0]-occ)*1.5
            best=(c,list(placed));return
        e,fp,role=items[i]
        for center in _adaptive_slots(arch,role,fp):
            for sc in _scale_candidates(fp,fp.primary):
                r=_rect(center,fp,sc*MOTION_ENVELOPE_SCALE)
                c=_placement_cost(r,center,sc,fp,role,arch,placed)
                if c>=1e5:continue
                rec(i+1,placed+[(e,r,fp,(center,sc,role))],cost+c)
    rec(0,[],0.0)
    if best is None:
        return {'pass':False,'reason':'NO_COLLISION_FREE_LAYOUT','placements':{},'archetype':arch}
    placements={}
    for e,r,fp,meta in best[1]:
        center,sc,role=meta
        placements[str(e.get('event_id'))]={
            'center_norm':[round(center[0],6),round(center[1],6)],'scale':round(sc,6),
            'rect_norm':[round(x,6) for x in r],'role':role,'atomic':fp.atomic,
            'footprint_norm':[round(fp.w,6),round(fp.h,6)],
        }
    return {'pass':True,'placements':placements,'archetype':arch,'score':round(best[0],6)}

def _phase_order(events:list[dict],grammar:dict)->list[dict]:
    roles=grammar.get('roles') or {};edges=grammar.get('explicit_edges') or []
    bysid={_sid(e):e for e in events if not e.get('suppressed_by_card_density')}
    ordered=[]
    # explicit story edges first
    for ed in edges:
        for sid in (_edge_sid(ed,'source'),_edge_sid(ed,'target')):
            e=bysid.get(sid)
            if e and e not in ordered:ordered.append(e)
    # narrator/lead, then supports/results
    rank={'NARRATOR':0,'LEAD':1,'ACTOR':1,'BLOCKER':2,'TARGET':3,'RESULT':3,'SUPPORT':4}
    for e in sorted(bysid.values(),key=lambda x:(rank.get(roles.get(_sid(x),'SUPPORT'),5),float(x.get('perceptual_hit_seconds',0)),str(x.get('event_id')))):
        if e not in ordered:ordered.append(e)
    return ordered

def build_story_phases(card:dict,events:list[dict],grammar:dict)->dict:
    """Create a sparse visual sentence; density changes over time instead of stacking all assets."""
    cs=float(card['start_seconds']);ce=float(card['end_seconds']);dur=ce-cs
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    order=_phase_order(active,grammar)
    primary=[e for e in order if _norm(e.get('attention_priority'))=='PRIMARY']
    support=[e for e in order if _norm(e.get('attention_priority'))!='PRIMARY']
    # Atomic means indivisible artwork, never automatic isolation. Start with the richest
    # semantically legal simultaneous state; the feasibility solver/recovery ladder may split it.
    arch=str(grammar.get('archetype'));edges=grammar.get('explicit_edges') or []
    bysid={_sid(e):e for e in order}
    max_phases=3 if dur>=4.55 else 2
    if edges and arch in {'CAUSE_EFFECT','FLOW_PIPELINE','SOURCE_BLOCKER_RESULT'}:
        first=edges[0];src=bysid.get(_edge_sid(first,'source'));dst=bysid.get(_edge_sid(first,'target'))
        blockers=[e for e in order if (grammar.get('roles') or {}).get(_sid(e))=='BLOCKER']
        bridge=blockers[0] if blockers else None
        core=[]
        for e in (src,bridge,dst):
            if e is not None and e not in core:core.append(e)
        companions=[e for e in support if e not in core][:max(0,MAX_PHASE_OBJECTS-len(core))]
        if len(order)<=MAX_PHASE_OBJECTS and sum(1 for e in order if _norm(e.get('attention_priority'))=='PRIMARY')<=2:
            phases=[order]
        elif len(core)<=2:
            phases=[(core+companions)[:MAX_PHASE_OBJECTS]]
        else:
            phases=[[core[0],core[1]], [core[1],core[2]]]
            for e in companions[:2]:phases[-1].append(e)
    elif arch in {'COMPARISON','CHARACTER_EXPLAINS_OBJECT','HUB_AND_SPOKES'}:
        characters=[e for e in primary if _norm(e.get('semantic_type')) in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}]
        anchor=next((e for e in characters if _norm(e.get('semantic_type'))=='MAIN_CHARACTER'),characters[0] if characters else (primary[0] if primary else None))
        other_primary=[e for e in primary if e is not anchor]
        if len(order)<=MAX_PHASE_OBJECTS and len(primary)<=2:phases=[order]
        else:
            phases=[]
            for i in range(max_phases):
                row=[anchor] if anchor is not None else []
                if i<len(other_primary):row.append(other_primary[i])
                room=MAX_PHASE_OBJECTS-len(row);row.extend(support[i*room:(i+1)*room])
                if row:phases.append(row)
    elif primary:
        phases=[(primary[:2]+support[:3])[:MAX_PHASE_OBJECTS]]
    else:
        phases=[support[:min(MAX_PHASE_OBJECTS,len(support))]] if support else []
    # Populate existing states before creating another phase. Never exceed two primaries;
    # supports fill negative space around the semantic anchors.
    used={id(e) for p in phases for e in p}
    remaining=[e for e in order if id(e) not in used]
    continuity_anchor=next((e for e in reversed(phases[-1] if phases else []) if _norm(e.get('attention_priority'))=='PRIMARY'),None)
    for e in remaining:
        primary_e=_norm(e.get('attention_priority'))=='PRIMARY';placed=False
        for p in sorted(phases,key=lambda row:(len(row),sum(1 for x in row if _norm(x.get('attention_priority'))=='PRIMARY'))):
            if len(p)>=MAX_PHASE_OBJECTS:continue
            if primary_e and sum(1 for x in p if _norm(x.get('attention_priority'))=='PRIMARY')>=2:continue
            p.append(e);placed=True;break
        if not placed and len(phases)<max_phases:
            row=[]
            if continuity_anchor is not None and continuity_anchor is not e:row.append(continuity_anchor)
            if (not primary_e) or sum(1 for x in row if _norm(x.get('attention_priority'))=='PRIMARY')<2:row.append(e)
            if row:phases.append(row)
    phases=[p for p in phases if p]
    # Preset durations are physical authority: short cards cannot carry three complete
    # appearance/disappearance sentences without rushed overlap. Two states are the default;
    # a third is legal only on long cards.
    if len(phases)>max_phases:
        if max_phases==2: phases=phases[:1]+[[e for group in phases[1:] for e in group][:1]]
        else: phases=phases[:2]+[[e for group in phases[2:] for e in group][:1]]
    n=max(1,len(phases));bounds=[]
    # Explicit two-state cause/flow handoffs get a physically realistic first window:
    # appearance (0.8s) + within movement (~0.9s) + disappearance (0.6s) needs ~2.3s.
    # Other cards remain evenly partitioned. No timing is script-specific.
    if n==2 and (grammar.get('explicit_edges') or []) and str(grammar.get('archetype')) in {'CAUSE_EFFECT','FLOW_PIPELINE','SOURCE_BLOCKER_RESULT'} and dur>=3.95:
        first=min(max(2.50,dur*0.57),dur-1.45)
        cuts=[cs,cs+first,ce]
    else:
        cuts=[cs+i*dur/n for i in range(n)]+[ce]
    for i,p in enumerate(phases):
        st=cuts[i];en=cuts[i+1]
        bounds.append({'phase_id':f"{card.get('card_id')}_P{i+1}",'start_seconds':st,'end_seconds':en,'event_ids':[str(e.get('event_id')) for e in p]})
    return {'schema':'HEXA_VISUAL_STORY_PHASES_V31','phases':bounds,'phase_count':len(bounds),'max_independent_support_concurrency':3,'atomic_asset_indivisibility':True,'atomic_composite_coexistence_allowed':True}

def repartition_story_phases(card:dict,events:list[dict],conflicts:list[dict])->dict:
    """Create legal anchor-bounded internal phases for a physically conflicting card.

    This runs before the second geometry solve. Every required event receives a
    phase; events separated in time may reuse geometry. Boundaries are midpoints
    between semantic hits, constrained by the card—not raw collision timestamps.
    """
    active=sorted([e for e in events if not e.get('suppressed_by_card_density')],key=lambda e:(float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id'))))
    if not active:return {'schema':'HEXA_VISUAL_STORY_PHASES_V31','phases':[],'phase_count':0,'repartitioned':True}
    cs,ce=float(card['start_seconds']),float(card['end_seconds']);groups=[]
    # Same persistent identity is one carrier state; distinct required semantic
    # events become sequential states after a physical conflict is observed.
    for e in active:
        group_primary=sum(1 for x in (groups[-1] if groups else []) if _norm(x.get('attention_priority'))=='PRIMARY')
        incoming_primary=_norm(e.get('attention_priority'))=='PRIMARY'
        same_hit=groups and abs(float(e.get('perceptual_hit_seconds',0))-float(groups[-1][0].get('perceptual_hit_seconds',0)))<=.08 and (not incoming_primary or group_primary<2) and len(groups[-1])<MAX_PHASE_OBJECTS
        same_carrier=groups and str(e.get('persistent_master_event_id'))==str(groups[-1][0].get('persistent_master_event_id'))
        if same_hit or same_carrier:groups[-1].append(e)
        else:groups.append([e])
    hits=[max(cs,min(ce,float(g[0].get('perceptual_hit_seconds',(cs+ce)/2)))) for g in groups]
    cuts=[cs]
    for i in range(1,len(hits)):
        midpoint=(hits[i-1]+hits[i])/2.0
        # Reserve the calibrated appearance lead-in for the incoming state.
        # The boundary remains semantic (between adjacent anchors), but may move
        # earlier than the midpoint to keep the next perceptual hit legal.
        cut=max(cuts[-1]+.72,min(midpoint,hits[i]-.55));cuts.append(max(cs,min(ce,cut)))
    cuts.append(ce)
    phases=[]
    for i,g in enumerate(groups):
        phases.append({'phase_id':f"{card.get('card_id')}_R{i+1}",'start_seconds':round(cuts[i],6),'end_seconds':round(cuts[i+1],6),'event_ids':[str(e.get('event_id')) for e in g],'semantic_boundary_authority':'ADJACENT_ANCHOR_MIDPOINT'})
    # A same-concept phase cannot be a support-only blank interval. Preserve a
    # source-backed narrative carrier when the state itself has no primary.
    carriers=[e for e in active if _norm(e.get('attention_priority'))=='PRIMARY']
    carrier=carriers[0] if carriers else None
    if carrier:
        carrier_id=str(carrier.get('event_id'))
        for phase in phases:
            present=[next((e for e in active if str(e.get('event_id'))==eid),None) for eid in phase['event_ids']]
            if not any(e is not None and _norm(e.get('attention_priority'))=='PRIMARY' for e in present):
                phase['event_ids'].insert(0,carrier_id);phase['carrier_handoff']=True
    # When adjacent states are both primaries, hold the completed primary into
    # the next state for one legal phase. This is a two-primary handoff, not a
    # role relabel: it prevents serialized multi-object cards and preserves a
    # readable carrier until the incoming primary is established.
    for i in range(1,len(phases)):
        prev=phases[i-1]['event_ids'];cur=phases[i]['event_ids']
        prev_primary=next((eid for eid in prev if _norm(next((e for e in active if str(e.get('event_id'))==eid),{}).get('attention_priority'))=='PRIMARY'),None)
        cur_primary=sum(1 for eid in cur if _norm(next((e for e in active if str(e.get('event_id'))==eid),{}).get('attention_priority'))=='PRIMARY')
        if prev_primary and cur_primary==1 and prev_primary not in cur:
            cur.insert(0,prev_primary);phases[i]['primary_handoff_from_previous']=True
    durations=[p['end_seconds']-p['start_seconds'] for p in phases]
    return {'schema':'HEXA_VISUAL_STORY_PHASES_V31_0_9','phases':phases,'phase_count':len(phases),'repartitioned':True,'detected_conflict_count':len(conflicts),'minimum_phase_duration':round(min(durations),6),'average_phase_duration':round(sum(durations)/len(durations),6),'phase_splits_rejected_as_too_short':sum(d<.72 for d in durations),'temporal_spatial_reuse':True}

def _preset_end_rect(e:dict,name:str,scale:float):
    fp=_fp(e);d=preset_def(name);b=d.get('end_norm') or [0.5,0.5]
    return _rect((float(b[0]),float(b[1])),fp,scale)

def within_preset_safe(e:dict,name:str,scale:float)->bool:
    """Only authorize fixed-position within-frame presets when the actual object fits."""
    r=_preset_end_rect(e,name,scale)
    return _in_safe(r)

def solve_card_layout(events:list[dict], grammar:dict, phase_plan:dict)->dict:
    """Deterministic phase-aware layout solver with co-occurrence decomposition.

    Events that never share a visual phase are mathematically independent and may reuse the
    same screen coordinates. V31.0.0 searched all events in one Cartesian tree, which could
    incorrectly exhaust/prune valid combinations on dense cards. V31.0.1 solves connected
    components of the phase co-occurrence graph independently, then merges the placements.
    """
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    phase_sets=[set(str(x) for x in (p.get('event_ids') or [])) for p in (phase_plan.get('phases') or [])]
    roles=grammar.get('roles') or {};arch=str(grammar.get('archetype') or 'SINGLE_FOCUS')
    if not active:return {'pass':True,'placements':{},'archetype':arch,'score':0.0,'phase_aware':True,'search_mode':'COOCCURRENCE_COMPONENT_BEAM'}
    byid={str(e.get('event_id')):e for e in active}
    graph={eid:set() for eid in byid}
    for ss in phase_sets:
        ids=[x for x in ss if x in byid]
        for i,a in enumerate(ids):
            for b in ids[i+1:]:graph[a].add(b);graph[b].add(a)
    components=[];seen=set()
    for eid in sorted(graph):
        if eid in seen:continue
        stack=[eid];seen.add(eid);comp=[]
        while stack:
            x=stack.pop();comp.append(x)
            for y in sorted(graph[x]):
                if y not in seen:seen.add(y);stack.append(y)
        components.append(comp)

    def candidates(fp,role):
        semantic=set(_slots(arch,role));rows=[]
        for center in _adaptive_slots(arch,role,fp):
            fallback=0 if center in semantic else 1;valid=[]
            for sc in _scale_candidates(fp,fp.primary):
                r=_rect(center,fp,sc*MOTION_ENVELOPE_SCALE)
                if not _in_safe(r):continue
                cost=max(0.0,1.0-sc)*4.0-max(0.0,sc-1.0)*0.55+(abs(center[1]-0.52)*0.5 if fp.primary else 0.0)+fallback*0.20
                occ=r[2]*r[3]
                if occ>0.44:cost+=(occ-0.44)*8.0
                valid.append((cost,center,sc,r))
            valid.sort(key=lambda x:(x[0],-x[2]));rows.extend(valid[:4]+valid[-2:])
        rows.sort(key=lambda x:(x[0],-x[2],x[1][1],x[1][0]))
        best=rows[:48]
        compact=sorted(rows,key=lambda x:(x[2],x[0],x[1][1],x[1][0]))[:16]
        out=[];seen=set()
        for row in best+compact:
            key=(row[1],row[2])
            if key not in seen:seen.add(key);out.append(row)
        return out

    placements={};total_score=0.0;BEAM_WIDTH=max(32,min(512,int(phase_plan.get('beam_width') or 512)))
    for comp in components:
        items=[]
        for eid in comp:
            e=byid[eid];fp=_fp(e);role=roles.get(_sid(e),'LEAD' if fp.primary else 'SUPPORT');items.append((e,fp,role))
        items.sort(key=lambda z:(0 if z[1].atomic else 1,0 if z[1].primary else 1,-z[1].area,str(z[0].get('event_id'))))
        cand_cache={id(e):candidates(fp,role) for e,fp,role in items}
        if any(not cand_cache[id(e)] for e,_,_ in items):
            return {'pass':False,'reason':'NO_SAFE_FRAME_CANDIDATE','placements':{},'archetype':arch}
        comp_set=set(comp)
        comp_phases=[ss.intersection(comp_set) for ss in phase_sets if ss.intersection(comp_set)]
        def cooccur(a,b):
            aa=str(a.get('event_id'));bb=str(b.get('event_id'));return any(aa in ss and bb in ss for ss in comp_phases)
        states=[(0.0,[])]
        for e,fp,role in items:
            nxt=[]
            for base_cost,placed in states:
                for cc,center,sc,r in cand_cache[id(e)]:
                    ok=True
                    for pe,pr,pfp,_ in placed:
                        if not cooccur(e,pe):continue
                        gap=PRIMARY_GAP if (fp.primary or pfp.primary) else SUPPORT_GAP
                        if _inter(_inflate(r,gap),_inflate(pr,gap))>1e-8:ok=False;break
                    if ok:nxt.append((base_cost+cc,placed+[(e,r,fp,(center,sc,role))]))
            if not nxt:return {'pass':False,'reason':'NO_COLLISION_FREE_PHASE_AWARE_LAYOUT','placements':{},'archetype':arch}
            nxt.sort(key=lambda x:x[0])
            # Retain both density-optimal and compact partial layouts. Without this
            # diversity branch, early large-object choices can consume the whole beam
            # before later supporting details are considered.
            best=nxt[:384]
            compact=sorted(nxt,key=lambda x:(sum(r[2]*r[3] for _,r,_,_ in x[1]),x[0]))[:128]
            states=[];seen_states=set()
            for state in best+compact:
                key=tuple((str(e.get('event_id')),round(r[0],5),round(r[1],5),round(r[2],5),round(r[3],5)) for e,r,_,_ in state[1])
                if key not in seen_states:seen_states.add(key);states.append(state)
        scored=[]
        for cost,placed in states:
            phase_penalty=0.0
            for ss in comp_phases:
                rows=[(e,r,fp,meta) for e,r,fp,meta in placed if str(e.get('event_id')) in ss]
                if not rows:continue
                occ=sum(r[2]*r[3]*fp.fill for _,r,fp,_ in rows)
                count=len(rows);ideal=0.40 if count>=2 else 0.34;low=0.24 if count>=2 else 0.20;high=0.60 if count>=2 else 0.56
                phase_penalty+=max(0.0,ideal-occ)*22.0+max(0.0,occ-high)*18.0
                if occ<low:phase_penalty+=(low-occ)*18.0
                if count>=2:
                    largest=max(r[2]*r[3]*fp.fill for _,r,fp,_ in rows)/max(1e-9,occ)
                    phase_penalty+=max(0.0,largest-0.82)*5.0
                    cx=sum((r[0]+r[2]/2)*r[2]*r[3]*fp.fill for _,r,fp,_ in rows)/max(1e-9,occ)
                    cy=sum((r[1]+r[3]/2)*r[2]*r[3]*fp.fill for _,r,fp,_ in rows)/max(1e-9,occ)
                    phase_penalty+=(abs(cx-0.5)+abs(cy-0.52))*1.4
            scored.append((cost+phase_penalty,placed))
        best=min(scored,key=lambda x:x[0]);total_score+=best[0]
        for e,r,fp,meta in best[1]:
            center,sc,role=meta
            placements[str(e.get('event_id'))]={'center_norm':[round(center[0],6),round(center[1],6)],'scale':round(sc,6),'rect_norm':[round(x,6) for x in r],'role':role,'atomic':fp.atomic,'footprint_norm':[round(fp.w,6),round(fp.h,6)]}
    return {'pass':True,'placements':placements,'archetype':arch,'score':round(total_score,6),'phase_aware':True,'search_mode':'COOCCURRENCE_COMPONENT_BEAM_512_DENSITY_OBJECTIVE','component_count':len(components)}

def repair_story_phases(card:dict,events:list[dict],grammar:dict)->dict:
    """Geometry-aware universal recovery for an infeasible story phase plan.

    The same algorithm is used for every topic. It consumes only semantic priority,
    explicit relationship endpoints and real physical footprints. Decorative supports
    may be suppressed only after all collision-free temporal placements are exhausted.
    """
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    if not active:
        return {'schema':'HEXA_VISUAL_STORY_PHASES_V31_0_9','phases':[],'phase_count':0,'rescue_mode':'EMPTY'}
    cs=float(card['start_seconds']);ce=float(card['end_seconds']);dur=max(0.01,ce-cs)
    max_phases=3 if dur>=4.35 else (2 if dur>=2.82 else 1)
    edge_ids=set()
    for ed in (grammar.get('explicit_edges') or []):
        edge_ids.add(_edge_sid(ed,'source'));edge_ids.add(_edge_sid(ed,'target'))
    ordered=_phase_order(active,grammar)
    def importance(e):
        sid=_sid(e);primary=_norm(e.get('attention_priority'))=='PRIMARY'
        return (0 if sid in edge_ids else 1,0 if primary else 1,0 if _fp(e).atomic else 1,float(e.get('perceptual_hit_seconds',cs)),str(e.get('event_id')))
    retention=sorted(ordered,key=importance)
    phases=[[] for _ in range(max_phases)];suppressed=[]

    def legal(group):
        if not group:return True
        if sum(1 for e in group if _norm(e.get('attention_priority'))=='PRIMARY')>2:return False
        if len(group)>MAX_PHASE_OBJECTS:return False
        tmp={'phases':[{'phase_id':'FIT','event_ids':[str(e.get('event_id')) for e in group]}]}
        return bool(solve_card_layout(group,grammar,tmp).get('pass'))

    for e in retention:
        hit=float(e.get('perceptual_hit_seconds',cs+dur/2))
        pref=min(max_phases-1,max(0,int(((hit-cs)/dur)*max_phases)))
        candidates=sorted(range(max_phases),key=lambda i:(abs(i-pref),len(phases[i]),i))
        placed=False
        for i in candidates:
            trial=phases[i]+[e]
            if legal(trial):phases[i]=trial;placed=True;break
        if placed:continue
        must_keep=(_norm(e.get('attention_priority'))=='PRIMARY' or _sid(e) in edge_ids)
        if must_keep:
            for i in candidates:
                victims=[v for v in phases[i] if _norm(v.get('attention_priority'))!='PRIMARY' and _sid(v) not in edge_ids]
                for v in reversed(victims):
                    trial=[x for x in phases[i] if x is not v]+[e]
                    if legal(trial):
                        phases[i]=trial;suppressed.append(v);placed=True;break
                if placed:break
        if not placed:suppressed.append(e)

    phases=[p for p in phases if p]
    if not phases:
        e=retention[0];phases=[[e]];suppressed=[x for x in retention[1:]]
    order_index={id(e):i for i,e in enumerate(ordered)}
    for p in phases:p.sort(key=lambda e:order_index.get(id(e),10**9))
    n=len(phases);cuts=[cs+i*dur/n for i in range(n)]+[ce];rows=[]
    for i,p in enumerate(phases):
        rows.append({'phase_id':f"{card.get('card_id')}_AR{i+1}",'start_seconds':cuts[i],'end_seconds':cuts[i+1],'event_ids':[str(e.get('event_id')) for e in p]})
    return {
        'schema':'HEXA_VISUAL_STORY_PHASES_V31_0_9','phases':rows,'phase_count':len(rows),
        'rescue_mode':'ADAPTIVE_GEOMETRY_PHASE_REPACK','suppressed_event_ids':[str(e.get('event_id')) for e in suppressed],
        'max_independent_support_concurrency':3,'atomic_asset_indivisibility':True,'atomic_composite_coexistence_allowed':True,
    }
