from __future__ import annotations
import math
import statistics
from hexa_v31.composition_qa import _state
from hexa_v31.composition_solver import SAFE_X, SAFE_Y
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel

SAFE_AREA=(SAFE_X[1]-SAFE_X[0])*(SAFE_Y[1]-SAFE_Y[0])

def _clip(r):
    x0=max(SAFE_X[0],float(r[0]));y0=max(SAFE_Y[0],float(r[1]))
    x1=min(SAFE_X[1],float(r[0])+float(r[2]));y1=min(SAFE_Y[1],float(r[1])+float(r[3]))
    return (x0,y0,max(0.0,x1-x0),max(0.0,y1-y0))

def _union_area(rects):
    xs=sorted({x for r in rects for x in (r[0],r[0]+r[2])})
    area=0.0
    for a,b in zip(xs,xs[1:]):
        if b<=a:continue
        ys=[]
        for r in rects:
            if r[0]<b and r[0]+r[2]>a:ys.append((r[1],r[1]+r[3]))
        ys.sort();merged=[]
        for y0,y1 in ys:
            if not merged or y0>merged[-1][1]:merged.append([y0,y1])
            else:merged[-1][1]=max(merged[-1][1],y1)
        area+=(b-a)*sum(max(0.0,y1-y0) for y0,y1 in merged)
    return area

def _islands(rects,gap=0.065):
    n=len(rects)
    if not n:return 0
    graph=[set() for _ in rects]
    for i,a in enumerate(rects):
        ax0=a[0]-gap;ay0=a[1]-gap;ax1=a[0]+a[2]+gap;ay1=a[1]+a[3]+gap
        for j,b in enumerate(rects[i+1:],i+1):
            if min(ax1,b[0]+b[2]+gap)>max(ax0,b[0]-gap) and min(ay1,b[1]+b[3]+gap)>max(ay0,b[1]-gap):graph[i].add(j);graph[j].add(i)
    seen=set();count=0
    for i in range(n):
        if i in seen:continue
        count+=1;stack=[i];seen.add(i)
        while stack:
            for j in graph[stack.pop()]:
                if j not in seen:seen.add(j);stack.append(j)
    return count

def build_visual_density_report(motion_plan:dict,sample_step:float=0.10)->dict:
    cards=list((motion_plan.get('visual_cards') or {}).get('cards') or []);events=list(motion_plan.get('events') or [])
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    model=ProjectedVisibleInkModel()
    rows=[];all_cov=[];all_ink=[];all_pop=[];all_islands=[];near_blank=0.0;static=0;transitions=0
    for card in cards:
        cid=str(card.get('card_id'));cs=float(card.get('start_seconds',0));ce=float(card.get('end_seconds',cs))
        # Density sees the same physical + source-scene ownership interval as the
        # renderer. Cross-scene actors may share a visual card for editorial
        # bookkeeping, but they are never a legitimate simultaneous-density cohort.
        def owned_window(event):
            ps=float(event.get('physical_start_seconds',event.get('start_seconds',0)))
            pe=float(event.get('physical_end_seconds',event.get('end_seconds',ps)))
            os=float(event.get('scene_ownership_start_seconds',ps))
            oe=float(event.get('scene_ownership_end_seconds',pe))
            return max(ps,os),min(pe,oe)
        evs=[e for e in active if owned_window(e)[0]<ce-1e-9 and owned_window(e)[1]>cs+1e-9]
        # Source-valid density candidates include actors later suppressed by the
        # density planner itself. Otherwise serialization can hide the fact that
        # the same source scene had multiple usable visual units available.
        actor_events=[e for e in events if str(e.get('visual_card_id'))==cid
                      and str(e.get('render_mode') or '').upper()!='RESIDUAL_SUPPORT']
        # Pixel-presence evidence is broader than the density cohort: an outgoing
        # scene may legally hold its exact last material pose across a card boundary
        # even though its normal owned/physical window no longer overlaps this card.
        # Such a carrier prevents white/blank pixels but never counts as an actor.
        pixel_evs=[e for e in active if (
            (owned_window(e)[0]<ce-1e-9 and owned_window(e)[1]>cs+1e-9)
            or (
                e.get('scene_boundary_carrier_authority')=='OUTGOING_LAST_MATERIAL_PIXEL_HOLD'
                and e.get('scene_boundary_carrier_start_seconds') is not None
                and e.get('scene_boundary_carrier_end_seconds') is not None
                and float(e.get('scene_boundary_carrier_start_seconds'))<ce-1e-9
                and float(e.get('scene_boundary_carrier_end_seconds'))>cs+1e-9
            )
        )]
        source_counts={}
        for event in actor_events:
            sid=str(event.get('scene_id') or f'__CARD_SOURCE__:{cid}')
            source_counts[sid]=source_counts.get(sid,0)+1
        multi_scene_ids=sorted(sid for sid,count in source_counts.items() if count>=2)
        total_valid=len(actor_events)
        covs=[];inks=[];pops=[];islands=[];primary_area=[];support_area=[];prev=None;coarse_blank=0.0;t=cs
        scene_peaks={sid:0 for sid in source_counts}
        while t<ce-1e-9:
            states=[]
            for e in evs:
                s=_state(e,t)
                if not s or s[2]<=0.08:continue
                r=_clip(s[3]);area=r[2]*r[3]
                if area<=0:continue
                states.append((e,r,float(s[2]),float(s[1])))
            rects=[r for _,r,_,_ in states];cov=_union_area(rects)/SAFE_AREA if rects else 0.0
            ink=0.0;pa=sa=0.0
            for e,r,op,_ in states:
                # Projected alpha/mask support is the density authority; rectangle
                # union above remains only a collision/layout measurement.
                a=model.project(e,r,op,clip_rect=(SAFE_X[0],SAFE_Y[0],SAFE_X[1]-SAFE_X[0],SAFE_Y[1]-SAFE_Y[0]))/SAFE_AREA;ink+=a
                if str(e.get('attention_priority') or '').upper()=='PRIMARY':pa+=a
                else:sa+=a
            pop=sum(1 for e,_,op,_ in states if op>0.22 and str(e.get('render_mode') or '').upper()!='RESIDUAL_SUPPORT');isl=_islands(rects)
            visible_scene_pop={}
            for event,_,op,_ in states:
                if op<=0.22 or str(event.get('render_mode') or '').upper()=='RESIDUAL_SUPPORT':continue
                sid=str(event.get('scene_id') or f'__CARD_SOURCE__:{cid}')
                visible_scene_pop[sid]=visible_scene_pop.get(sid,0)+1
            for sid,count in visible_scene_pop.items():scene_peaks[sid]=max(scene_peaks.get(sid,0),count)
            covs.append(cov);inks.append(ink);pops.append(pop);islands.append(isl)
            primary_area.append(pa);support_area.append(sa)
            if not states:coarse_blank+=sample_step
            sig=(round(cov,3),round(ink,3),pop,tuple(sorted((str(e.get('event_id')),round(op,2),round(sc,2)) for e,_,op,sc in states)))
            if prev is not None:
                transitions+=1
                if sig==prev:static+=1
            prev=sig;t+=sample_step
        # Preserve the historical coarse density clock for ordinary cards. Only
        # cards that actually contain a certified pixel-only scene-boundary carrier
        # need encoded-frame certification, because the carrier is intentionally not
        # part of the actor/density cohort.
        carrier_evs=[e for e in pixel_evs if e.get('scene_boundary_carrier_authority')=='OUTGOING_LAST_MATERIAL_PIXEL_HOLD']
        if carrier_evs:
            fps=max(1.0,float(motion_plan.get('fps') or 30.0));eps=1e-9
            first_frame=max(0,int(math.ceil(cs*fps-eps)));end_frame=max(first_frame,int(math.ceil(ce*fps-eps)))
            blank_frames=0
            for frame in range(first_frame,end_frame):
                ft=frame/fps;visible=False
                for e in pixel_evs:
                    state=_state(e,ft)
                    if state is not None and float(state[2])>0.08:
                        visible=True;break
                    if e.get('scene_boundary_carrier_authority')!='OUTGOING_LAST_MATERIAL_PIXEL_HOLD':
                        continue
                    carrier_start=e.get('scene_boundary_carrier_start_seconds');carrier_end=e.get('scene_boundary_carrier_end_seconds')
                    sample=e.get('scene_boundary_carrier_sample_seconds')
                    if carrier_start is None or carrier_end is None or sample is None:
                        continue
                    if float(carrier_start)-eps<=ft<float(carrier_end)-eps:
                        held=_state(e,float(sample),ignore_scene_ownership=True)
                        if held is not None and float(held[2])>0.08:
                            visible=True;break
                if not visible:blank_frames+=1
            blank=blank_frames/fps
        else:
            blank=coarse_blank
        median_cov=statistics.median(covs) if covs else 0.0;median_ink=statistics.median(inks) if inks else 0.0;peak=max(pops or [0])
        hard_scene_ids=sorted(sid for sid in multi_scene_ids if scene_peaks.get(sid,0)<2)
        multi=bool(multi_scene_ids)
        rows.append({'card_id':cid,'archetype':(card.get('universal_scene_grammar') or {}).get('archetype'),'source_valid_object_count':total_valid,'active_object_count':len(evs),'peak_visible_object_count':peak,'same_scene_source_valid_object_counts':dict(sorted(source_counts.items())),'same_scene_peak_visible_object_counts':dict(sorted(scene_peaks.items())),'same_scene_multi_object_scene_ids':multi_scene_ids,'hard_under_density_scene_ids':hard_scene_ids,'mean_temporal_population':round(statistics.mean(pops) if pops else 0.0,4),'median_safe_frame_union_coverage':round(median_cov,6),'median_estimated_alpha_coverage':round(median_ink,6),'negative_space_ratio':round(1.0-median_cov,6),'largest_object_dominance':round(max((float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[2])*float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[3]) for e in evs),default=0.0)/max(1e-9,sum((float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[2])*float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[3]) for e in evs))),6),'mean_visual_island_count':round(statistics.mean(islands) if islands else 0.0,4),'max_visual_island_count':max(islands or [0]),'primary_secondary_balance':round(statistics.mean(primary_area)/max(1e-9,statistics.mean(primary_area)+statistics.mean(support_area)),6) if primary_area else 0.0,'near_blank_duration_seconds':round(min(max(0.0,ce-cs),blank),3),'hard_under_density':bool(hard_scene_ids),'soft_under_density':bool(multi and median_ink<0.24)})
        all_cov.extend(covs);all_ink.extend(inks);all_pop.extend(pops);all_islands.extend(islands);near_blank+=blank
    severe=[r['card_id'] for r in rows if r['hard_under_density']]
    soft=[r['card_id'] for r in rows if r['soft_under_density']]
    return {'schema':'HEXA_V31_VISUAL_DENSITY_REPORT','version':'31.0.25','visible_ink_authority':model.algorithm_version,'sample_step_seconds':sample_step,'card_count':len(cards),'active_object_count':len(active),'source_object_count':len(events),'median_safe_frame_union_coverage':round(statistics.median(all_cov) if all_cov else 0.0,6),'median_estimated_alpha_coverage':round(statistics.median(all_ink) if all_ink else 0.0,6),'mean_temporal_population':round(statistics.mean(all_pop) if all_pop else 0.0,6),'mean_visual_island_count':round(statistics.mean(all_islands) if all_islands else 0.0,6),'near_blank_duration_seconds':round(near_blank,3),'near_blank_ratio':round(near_blank/max(1e-9,sum(float(c.get('duration_seconds') or 0) for c in cards)),6),'static_hold_ratio':round(static/max(1,transitions),6),'hard_under_density_cards':severe,'soft_under_density_cards':soft,'cards':rows,'pass':not severe}

def temporal_population_report(density_report:dict)->dict:
    return {'schema':'HEXA_V31_TEMPORAL_POPULATION_REPORT','version':'31.0.25','mean_temporal_population':density_report.get('mean_temporal_population'),'near_blank_duration_seconds':density_report.get('near_blank_duration_seconds'),'near_blank_ratio':density_report.get('near_blank_ratio'),'static_hold_ratio':density_report.get('static_hold_ratio'),'cards':[{'card_id':r.get('card_id'),'source_valid_object_count':r.get('source_valid_object_count'),'active_object_count':r.get('active_object_count'),'peak_visible_object_count':r.get('peak_visible_object_count'),'mean_temporal_population':r.get('mean_temporal_population'),'near_blank_duration_seconds':r.get('near_blank_duration_seconds')} for r in density_report.get('cards') or []]}
