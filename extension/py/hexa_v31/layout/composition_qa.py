from __future__ import annotations
import math
from hexa_v31.composition_solver import overlap_ratio, _fp, _rect, _in_safe
from hexa_v31.preset_authority import preset as preset_def, progress as preset_progress, scale as preset_scale, opacity as preset_opacity


def _norm(v):return str(v or '').strip().upper()

def _lerp(a,b,q):return float(a)+(float(b)-float(a))*float(q)

def _state(e:dict,t:float):
    st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st))
    # Visual lifetimes are half-open [start,end): the boundary frame belongs\n    # to the incoming state only. This matches timeline/card ownership and prevents\n    # a false one-frame collision when one source ends exactly as the next begins.\n    if t<st-1e-6 or t>=en-1e-6:return None
    rest=e.get('card_rest_position_norm') or [0.5,0.5];pos=[float(rest[0]),float(rest[1])];sc=1.0;op=1.0
    pe=e.get('preset_entry')
    if pe:
        name=str(pe.get('name'));ps=float(pe.get('start_seconds',st));pd=float(pe.get('duration_seconds') or 0.8);d=preset_def(name);q=max(0.0,min(1.0,(t-ps)/max(1e-6,pd)))
        fam=str(d.get('family') or '')
        if fam in {'ENTRY_EXIT','WITHIN_FRAME'}:
            a=d.get('start_norm') or [0.5,0.5];b=d.get('end_norm') or [0.5,0.5];pg=preset_progress(name,q);pos=[_lerp(a[0],b[0],pg),_lerp(a[1],b[1],pg)]
        elif fam=='APPEARANCE':sc*=preset_scale(name,q);op*=preset_opacity(name,q)
    held=None
    for a in sorted(e.get('preset_actions') or [],key=lambda x:float(x.get('start_seconds',0))):
        name=str(a.get('name'));ast=float(a.get('start_seconds',0));ad=float(a.get('duration_seconds') or 0.8);d=preset_def(name)
        if t<ast:continue
        if str(d.get('family'))=='WITHIN_FRAME':
            aa=d.get('start_norm') or [0.5,0.5];bb=d.get('end_norm') or [0.5,0.5]
            if t>=ast+ad:held=[float(bb[0]),float(bb[1])]
            else:
                q=max(0.0,min(1.0,(t-ast)/max(1e-6,ad)));pg=preset_progress(name,q);held=[_lerp(aa[0],bb[0],pg),_lerp(aa[1],bb[1],pg)]
    if held is not None:pos=held
    px=e.get('preset_exit')
    if px:
        name=str(px.get('name'));xs=float(px.get('start_seconds',en));xd=float(px.get('duration_seconds') or 0.6)
        if t>=xs:
            q=max(0.0,min(1.0,(t-xs)/max(1e-6,xd)));d=preset_def(name);fam=str(d.get('family') or '')
            if fam=='ENTRY_EXIT':
                aa=d.get('start_norm') or [0.5,0.5];bb=d.get('end_norm') or [0.5,0.5];pg=preset_progress(name,q);pos=[_lerp(aa[0],bb[0],pg),_lerp(aa[1],bb[1],pg)]
            elif fam=='DISAPPEARANCE':
                dd=d.get('position_delta_norm') or [0,0];pos=[pos[0]+float(dd[0])*q,pos[1]+float(dd[1])*q];sc*=preset_scale(name,q);op*=preset_opacity(name,q)
    fp=_fp(e);scale=float(e.get('layout_scale_multiplier') or 1.0)*sc;return pos,scale,op,_rect(pos,fp,scale)

def _settled_rect(e:dict):
    fp=_fp(e);c=e.get('card_rest_position_norm') or [0.5,0.5];s=float(e.get('layout_scale_multiplier') or 1.0)
    pe=e.get('preset_entry') or {}
    if str(pe.get('name') or '')=='APPEAR_HIGH_SCALE':
        # The supplied appearance preset holds at 110%, so this is the real settled footprint.
        s*=1.10
    return _rect((float(c[0]),float(c[1])),fp,s)

def card_motion_conflicts(events:list[dict],start_seconds:float,end_seconds:float,fps:float=30.0)->list[dict]:
    """Return deterministic first-class trajectory conflicts for planner recovery and QA."""
    conflicts=[];step=1.0/max(12.0,min(20.0,float(fps)));t=float(start_seconds)
    while t<=float(end_seconds)+1e-6:
        states=[]
        for e in events:
            if e.get('suppressed_by_card_density'):continue
            s=_state(e,t)
            if s and s[2]>0.22:states.append((e,s[3]))
        for i,(a,ra) in enumerate(states):
            for b,rb in states[i+1:]:
                ov=overlap_ratio(ra,rb);pa=_norm(a.get('attention_priority'))=='PRIMARY';pb=_norm(b.get('attention_priority'))=='PRIMARY';limit=0.015 if pa and pb else (0.035 if pa or pb else 0.07)
                if ov>limit:
                    conflicts.append({'event_a':str(a.get('event_id')),'event_b':str(b.get('event_id')),'time_seconds':round(t,6),'overlap_ratio':round(ov,6),'limit':limit})
        t+=step
    first={}
    for row in conflicts:
        key=tuple(sorted((row['event_a'],row['event_b'])))
        if key not in first:first[key]=row
    return list(first.values())

def viewport_clipping_qa(events,fps=30.0):
    """Certify partial visibility is brief, monotonic, and only entry/exit."""
    failures=[];samples=0
    for e in events:
        if e.get('suppressed_by_card_density'):continue
        st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st));step=1.0/max(12.,min(20.,fps));vals=[];t=st
        while t<=en+1e-6:
            state=_state(e,t)
            if state and state[2]>.22:
                r=state[3];visible=max(0.,min(1.,r[0]+r[2])-max(0.,r[0]))*max(0.,min(1.,r[1]+r[3])-max(0.,r[1]));vals.append((t,visible/max(1e-9,r[2]*r[3])));samples+=1
            t+=step
        clipped=[x for x in vals if x[1]<.995]
        if not clipped:continue
        duration=clipped[-1][0]-clipped[0][0]+step;entry=bool(e.get('preset_entry'));exit=bool(e.get('preset_exit'))
        if not (entry or exit) or duration>.95:failures.append(f"{e.get('event_id')}: sustained viewport clipping {duration:.3f}s")
        fractions=[x[1] for x in clipped]
        if entry and not exit and any(b+1e-4<a for a,b in zip(fractions,fractions[1:])):failures.append(f"{e.get('event_id')}: nonmonotonic entry clipping")
        if exit and not entry and any(b>a+1e-4 for a,b in zip(fractions,fractions[1:])):failures.append(f"{e.get('event_id')}: nonmonotonic exit clipping")
    return {'pass':not failures,'failures':failures,'sample_count':samples,'authority':'FINAL_COMMITTED_VISIBLE_FRACTION_OVER_TIME'}

def composition_plan_qa(motion_plan:dict)->dict:
    failures=[];warnings=[];cards=(motion_plan.get('visual_cards') or {}).get('cards') or [];events=motion_plan.get('events') or [];fps=float(motion_plan.get('fps') or 30.0)
    by_card={str(c.get('card_id')):[] for c in cards}
    for e in events:
        if not e.get('suppressed_by_card_density'):by_card.setdefault(str(e.get('visual_card_id')),[]).append(e)
    total_pairs=bad_pairs=dynamic_samples=0
    for c in cards:
        cid=str(c.get('card_id'));evs=by_card.get(cid,[]);phase_plan=c.get('story_phase_plan') or {};phases=phase_plan.get('phases') or []
        if not phases:failures.append(f'{cid}: no visual story phases compiled');continue
        em={str(e.get('event_id')):e for e in evs}
        # Settled phase geometry is a hard readability contract.
        for ph in phases:
            rows=[em[x] for x in ph.get('event_ids') or [] if x in em]
            rects=[]
            for e in rows:
                r=_settled_rect(e)
                if not _in_safe(r):failures.append(f"{cid}/{ph.get('phase_id')}:{e.get('event_id')}: settled bbox outside safe frame")
                rects.append((e,r))
            for i,(a,ra) in enumerate(rects):
                for b,rb in rects[i+1:]:
                    total_pairs+=1;ov=overlap_ratio(ra,rb);pa=_norm(a.get('attention_priority'))=='PRIMARY';pb=_norm(b.get('attention_priority'))=='PRIMARY';limit=0.002 if pa and pb else (0.01 if pa or pb else 0.025)
                    if ov>limit:bad_pairs+=1;failures.append(f"{cid}/{ph.get('phase_id')}: settled overlap {a.get('event_id')} x {b.get('event_id')}={ov:.3f}>{limit:.3f}")
            occ=sum(r[2]*r[3] for _,r in rects)
            if occ>0.62:warnings.append(f"{cid}/{ph.get('phase_id')}: bbox occupancy {occ:.3f}>0.62; visual density high")
        # Joint layout+motion gate: sample exact supplied preset curves. This catches clean rest
        # layouts whose entry/exit paths still sweep through another object.
        cs=float(c.get('start_seconds',0));ce=float(c.get('end_seconds',cs));step=1.0/max(12.0,min(20.0,fps))
        dynamic_samples+=int(max(0.0,ce-cs)/step+1)*max(0,len(evs)*(len(evs)-1)//2)
        for row in card_motion_conflicts(evs,cs,ce,fps):
            bad_pairs+=1;failures.append(f"{cid}@{row['time_seconds']:.2f}s: motion-path overlap {row['event_a']} x {row['event_b']}={row['overlap_ratio']:.3f}>{row['limit']:.3f}")
    # dedupe messages while preserving order
    failures=list(dict.fromkeys(failures));warnings=list(dict.fromkeys(warnings))
    viewport=viewport_clipping_qa(events,fps);failures.extend(viewport['failures'])
    return {'pass':not failures,'failures':failures,'warnings':warnings,'checked_pair_count':total_pairs,'dynamic_pair_samples':dynamic_samples,'bad_pair_count':bad_pairs,'visual_card_count':len(cards),'viewport_clipping_qa':viewport,'authority':'V31_CONSTRAINT_SOLVED_COMPOSITION__SETTLED_AND_MOTION_PATH_HARD_GATE'}
