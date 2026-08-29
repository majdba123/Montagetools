from __future__ import annotations
import statistics
from .composition_qa import _state
from .composition_solver import SAFE_X, SAFE_Y

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
    rows=[];all_cov=[];all_ink=[];all_pop=[];all_islands=[];near_blank=0.0;static=0;transitions=0
    for card in cards:
        cid=str(card.get('card_id'));cs=float(card.get('start_seconds',0));ce=float(card.get('end_seconds',cs))
        # Physical lifetime overlap is the committed timeline authority. An
        # instance held across a phase/card boundary must be seen by density in
        # exactly the same interval consumed by the renderer and collision QA.
        evs=[e for e in active if float(e.get('start_seconds',0))<ce-1e-9 and float(e.get('end_seconds',0))>cs+1e-9]
        total_valid=sum(1 for e in events if str(e.get('visual_card_id'))==cid)
        covs=[];inks=[];pops=[];islands=[];primary_area=[];support_area=[];prev=None;blank=0.0;t=cs
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
                fill=float((e.get('matting') or {}).get('opaque_foreground_fraction') or 0.62)
                a=r[2]*r[3]*max(0.12,min(1.0,fill))*op/SAFE_AREA;ink+=a
                if str(e.get('attention_priority') or '').upper()=='PRIMARY':pa+=a
                else:sa+=a
            pop=sum(1 for _,_,op,_ in states if op>0.22);isl=_islands(rects)
            covs.append(cov);inks.append(ink);pops.append(pop);islands.append(isl)
            primary_area.append(pa);support_area.append(sa)
            # "Blank" means the safe frame has effectively no visible geometry.
            # Ink alone is not a reliable blank test for deliberately sparse SVGs/icons.
            if not states:blank+=sample_step
            sig=(round(cov,3),round(ink,3),pop,tuple(sorted((str(e.get('event_id')),round(op,2),round(sc,2)) for e,_,op,sc in states)))
            if prev is not None:
                transitions+=1
                if sig==prev:static+=1
            prev=sig;t+=sample_step
        median_cov=statistics.median(covs) if covs else 0.0;median_ink=statistics.median(inks) if inks else 0.0;peak=max(pops or [0])
        multi=total_valid>=2
        rows.append({'card_id':cid,'archetype':(card.get('universal_scene_grammar') or {}).get('archetype'),'source_valid_object_count':total_valid,'active_object_count':len(evs),'peak_visible_object_count':peak,'mean_temporal_population':round(statistics.mean(pops) if pops else 0.0,4),'median_safe_frame_union_coverage':round(median_cov,6),'median_estimated_alpha_coverage':round(median_ink,6),'negative_space_ratio':round(1.0-median_cov,6),'largest_object_dominance':round(max((float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[2])*float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[3]) for e in evs),default=0.0)/max(1e-9,sum((float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[2])*float((card.get('constraint_layout') or {}).get('placements',{}).get(e.get('event_id'),{}).get('rect_norm',[0,0,0,0])[3]) for e in evs))),6),'mean_visual_island_count':round(statistics.mean(islands) if islands else 0.0,4),'max_visual_island_count':max(islands or [0]),'primary_secondary_balance':round(statistics.mean(primary_area)/max(1e-9,statistics.mean(primary_area)+statistics.mean(support_area)),6) if primary_area else 0.0,'near_blank_duration_seconds':round(min(max(0.0,ce-cs),blank),3),'hard_under_density':bool(multi and peak<2),'soft_under_density':bool(multi and median_cov<0.24)})
        all_cov.extend(covs);all_ink.extend(inks);all_pop.extend(pops);all_islands.extend(islands);near_blank+=blank
    severe=[r['card_id'] for r in rows if r['hard_under_density']]
    soft=[r['card_id'] for r in rows if r['soft_under_density']]
    return {'schema':'HEXA_V31_VISUAL_DENSITY_REPORT','version':'31.0.25','sample_step_seconds':sample_step,'card_count':len(cards),'active_object_count':len(active),'source_object_count':len(events),'median_safe_frame_union_coverage':round(statistics.median(all_cov) if all_cov else 0.0,6),'median_estimated_alpha_coverage':round(statistics.median(all_ink) if all_ink else 0.0,6),'mean_temporal_population':round(statistics.mean(all_pop) if all_pop else 0.0,6),'mean_visual_island_count':round(statistics.mean(all_islands) if all_islands else 0.0,6),'near_blank_duration_seconds':round(near_blank,3),'near_blank_ratio':round(near_blank/max(1e-9,sum(float(c.get('duration_seconds') or 0) for c in cards)),6),'static_hold_ratio':round(static/max(1,transitions),6),'hard_under_density_cards':severe,'soft_under_density_cards':soft,'cards':rows,'pass':not severe}

def temporal_population_report(density_report:dict)->dict:
    return {'schema':'HEXA_V31_TEMPORAL_POPULATION_REPORT','version':'31.0.25','mean_temporal_population':density_report.get('mean_temporal_population'),'near_blank_duration_seconds':density_report.get('near_blank_duration_seconds'),'near_blank_ratio':density_report.get('near_blank_ratio'),'static_hold_ratio':density_report.get('static_hold_ratio'),'cards':[{'card_id':r.get('card_id'),'source_valid_object_count':r.get('source_valid_object_count'),'active_object_count':r.get('active_object_count'),'peak_visible_object_count':r.get('peak_visible_object_count'),'mean_temporal_population':r.get('mean_temporal_population'),'near_blank_duration_seconds':r.get('near_blank_duration_seconds')} for r in density_report.get('cards') or []]}
