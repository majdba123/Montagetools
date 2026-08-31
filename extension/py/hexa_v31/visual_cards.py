from __future__ import annotations
import math
from functools import lru_cache
from .preset_authority import is_primary_semantic


def _tm(alignment:dict):
    return {str(x['scene_id']):x for x in (alignment.get('scene_timings') or [])}


def _relation(scene:dict)->str:
    return str(scene.get('relation_to_previous') or '').strip().upper().replace(' ','_').replace('-','_')


def _semantic_identity(unit:dict)->str:
    typ=str(unit.get('semantic_type') or unit.get('type') or '').strip().upper()
    role=str(unit.get('semantic_role') or unit.get('role') or '').strip().upper()
    name=str(unit.get('semantic_name') or unit.get('name') or '').strip().upper()
    uid=str(unit.get('unit_id') or unit.get('semantic_unit_id') or '').strip().upper()
    if typ=='MAIN_CHARACTER':
        return 'MAIN_CHARACTER::'+(name or 'NARRATOR')
    if typ=='SECONDARY_CHARACTER':
        return 'SECONDARY_CHARACTER::'+(name or uid or 'CHARACTER')
    return f'{typ or role or "VISUAL"}::{name or uid or "UNNAMED"}'


def _counts(scene:dict, vr:dict)->tuple[int,int,int,int,int,set[str],set[str]]:
    """Return semantic/physical density without authorizing extra cutouts.

    V31 distinguishes *visible supporting detail* from *independent animation layers*.
    The user's 3-8 secondary rule is a visual-composition rule. A composite may contain
    several physically visible secondary details that must remain grouped to preserve
    clean edges. ``grouped_detail_count`` is therefore allowed to satisfy density QA, but
    it never creates a new movable layer.
    """
    units=list(scene.get('units') or [])
    p_units=[u for u in units if is_primary_semantic(u)]
    s_units=[u for u in units if not is_primary_semantic(u)]
    primary=len(p_units); secondary=len(s_units)
    raw=max(0,int(vr.get('raw_component_count') or 0))
    detail=max(0,int(vr.get('grouped_detail_count') or (vr.get('artifacts') or {}).get('grouped_detail_count') or 0))
    physical_top=max(0,len([u for u in (vr.get('units') or []) if int(u.get('hierarchy_level') or 0)==0]))
    visual_secondary=max(secondary,max(0,raw-primary),max(0,physical_top-primary),max(0,detail-primary))
    pkeys={_semantic_identity(u) for u in p_units}
    skeys={_semantic_identity(u) for u in s_units}
    return primary,secondary,visual_secondary,raw,detail,pkeys,skeys


def _make_rows(plan:dict,alignment:dict,vision_results:list[dict])->list[dict]:
    scenes=list(plan.get('scenes') or [])
    timing=_tm(alignment);vis={str(v['scene_id']):v for v in vision_results};rows=[]
    for i,s in enumerate(scenes):
        sid=str(s['scene_id']);t=timing[sid];vr=vis[sid]
        p,ss,sv,raw,detail,pkeys,skeys=_counts(s,vr)
        rows.append({
            'idx':i,'scene_id':sid,'scene':s,'start':float(t['start']),'end':float(t['end']),
            'duration':float(t['end'])-float(t['start']),'primary':p,'secondary_semantic':ss,
            'secondary_visual':sv,'raw_component_count':raw,'grouped_detail_count':detail,
            'primary_keys':pkeys,'secondary_keys':skeys,'relation':_relation(s),
        })
    return rows


def _required_primary_duration(primary_count:int)->float:
    """Lower bound for exact user preset families with <=2 concurrent primaries.

    Dense cards use the legal 0.8s Appearance + 0.6s Disappearance pair. Primaries are
    scheduled in two lanes, so each wave costs about 1.46s including a small safety gap.
    """
    n=max(1,int(primary_count))
    if n<=2:return 3.0
    waves=int(math.ceil(n/2.0))
    return min(5.01,0.18+waves*1.46+0.12)


def _candidate_stats(rows:list[dict],i:int,j:int):
    pkeys=set();skeys=set();secondary_visual=0
    for r in rows[i:j+1]:
        pkeys.update(r['primary_keys']);skeys.update(r['secondary_keys'])
        secondary_visual+=max(0,int(r['secondary_visual']))
    return pkeys,skeys,min(8,secondary_visual)


def _partition(rows:list[dict],min_seconds:float,max_seconds:float,target_seconds:float=3.65)->list[tuple[int,int]]:
    """Global semantic-density-aware partition into 3-5 second visual cards."""
    n=len(rows)
    if not n:return []
    eps=1e-6
    @lru_cache(maxsize=None)
    def solve(i:int):
        if i>=n:return (0.0,())
        best=None
        for j in range(i,n):
            dur=rows[j]['end']-rows[i]['start']
            if dur>max_seconds+eps:break
            if dur<min_seconds-eps:continue
            pkeys,skeys,secondary_pool=_candidate_stats(rows,i,j)
            required=_required_primary_duration(len(pkeys))
            if required>max_seconds+eps or dur+0.08<required:
                continue
            reset_cross=sum(1 for r in rows[i+1:j+1] if r['relation'] in {'RESET','START','NEW','NEW_SCENE'})
            density_deficit=max(0,3-secondary_pool);density_over=max(0,secondary_pool-8)
            # Hard-prefer cards that can satisfy visual support density from physical/grouped detail.
            cost=(dur-target_seconds)**2 + reset_cross*1.3
            cost+=density_deficit*5.0+density_over*0.12
            cost+=max(0,len(pkeys)-4)*2.0
            cost+=max(0,(j-i+1)-5)*0.18
            tail=solve(j+1)
            if tail is None:continue
            total=cost+tail[0]
            if best is None or total<best[0]:best=(total,((i,j),)+tail[1])
        return best
    ans=solve(0)
    if ans is None:raise ValueError('No legal semantic-density-aware 3-5 second card partition exists at source boundaries.')
    return list(ans[1])


def _time_window_groups(rows:list[dict],min_seconds:float,max_seconds:float,target_seconds:float=3.65):
    """Boundary-independent fallback; chooses the least-dense legal equal-window plan."""
    if not rows:return []
    start=float(rows[0]['start']);end=float(rows[-1]['end']);total=end-start
    kmin=max(1,int(math.ceil(total/max_seconds-1e-9)));kmax=max(kmin,int(math.floor(total/min_seconds+1e-9)))
    candidates=[]
    for k in range(kmin,kmax+1):
        card_dur=total/float(k)
        if not(min_seconds-1e-6<=card_dur<=max_seconds+1e-6):continue
        buckets=[[] for _ in range(k)]
        for r in rows:
            mid=(float(r['start'])+float(r['end']))/2.0
            idx=min(k-1,max(0,int((mid-start)/card_dur)));buckets[idx].append(r)
        if any(not b for b in buckets):continue
        score=0.0;legal=True
        for b in buckets:
            pkeys=set();sec=0
            for r in b:pkeys.update(r['primary_keys']);sec+=max(0,int(r['secondary_visual']))
            req=_required_primary_duration(len(pkeys))
            if req>card_dur+0.08:legal=False;break
            score+=(card_dur-target_seconds)**2+max(0,3-min(8,sec))*5.0+max(0,len(pkeys)-4)*2.0
        if legal:candidates.append((score,k,card_dur,buckets))
    if not candidates:raise ValueError(f'Cannot derive legal visual-card windows for total duration {total:.3f}s and primary preset capacity.')
    _,k,card_dur,buckets=min(candidates,key=lambda x:x[0])
    out=[]
    for i,b in enumerate(buckets):
        b.sort(key=lambda r:r['idx']);cs=start+i*card_dur;ce=end if i==k-1 else start+(i+1)*card_dur
        out.append({'rows':b,'card_start':cs,'card_end':ce,'partition_mode':'TIME_WINDOW_SEMANTIC_DENSITY'})
    return out


def build_visual_cards(plan:dict, alignment:dict, vision_results:list[dict], *, min_seconds:float=3.0, max_seconds:float=5.0)->dict:
    rows=_make_rows(plan,alignment,vision_results); expanded=[];long_scene_segmented=False
    # V1.1 source scenes may intentionally outlast one editorial card. Keep their
    # identity while presenting legal interval rows to the existing card compiler.
    for row in rows:
        dur=float(row['duration'])
        if dur<=max_seconds+1e-6: expanded.append(row); continue
        long_scene_segmented=True;count=max(2,int(round(dur/max_seconds))); step=dur/count
        while step<min_seconds and count>1: count-=1;step=dur/count
        for i in range(count):
            r=dict(row);r['start']=float(row['start'])+i*step;r['end']=float(row['start'])+(i+1)*step;r['duration']=r['end']-r['start'];r['source_scene_segment_index']=i;r['source_scene_segment_count']=count;expanded.append(r)
    rows=expanded;partition_mode='SCENE_BOUNDARY_SEMANTIC_DP'
    try:
        if long_scene_segmented:
            partition_mode='V11_LONG_SCENE_INTERVAL_SEGMENTS'
            compiled=[{'rows':[r],'card_start':r['start'],'card_end':r['end'],'partition_mode':partition_mode} for r in rows]
        else:
            groups=_partition(rows,min_seconds,max_seconds)
            compiled=[{'rows':rows[a:b+1],'card_start':rows[a]['start'],'card_end':rows[b]['end'],'partition_mode':partition_mode} for a,b in groups]
    except ValueError:
        partition_mode='TIME_WINDOW_SEMANTIC_DENSITY'
        try:compiled=_time_window_groups(rows,min_seconds,max_seconds)
        except ValueError as exc:return {'schema':'HEXA_VISUAL_CARD_PLAN_V31','version':'31.0.9','cards':[],'scene_to_card':{},'hard_failures':[str(exc)],'pass':False}

    cards=[]
    for group in compiled:
        cr=group['rows'];card_start=float(group['card_start']);card_end=float(group['card_end']);dur=card_end-card_start
        pkeys=set();skeys=set();secondary_sem=0;secondary_visual=0
        for r in cr:
            pkeys.update(r['primary_keys']);skeys.update(r['secondary_keys'])
            secondary_sem+=max(0,int(r['secondary_semantic']));secondary_visual+=max(0,int(r['secondary_visual']))
        secondary_visual_pool=min(8,secondary_visual)
        beats=[{
            'source_scene_id':r['scene_id'],'audio_start_seconds':r['start'],'audio_end_seconds':r['end'],
            'audio_duration_seconds':r['duration'],'relation_to_previous':r['relation'],
            'primary_authority_count':r['primary'],'semantic_secondary_count':r['secondary_semantic'],
            'grouped_visual_secondary_count':r['secondary_visual'],'raw_component_count':r['raw_component_count'],
            'grouped_detail_count':r['grouped_detail_count'],
        } for r in cr]
        cards.append({
            'card_id':f'VCARD_{len(cards)+1:03d}','source_scene_ids':[r['scene_id'] for r in cr],
            'start_seconds':card_start,'end_seconds':card_end,'duration_seconds':dur,'beat_count':len(cr),'beats':beats,
            'distinct_primary_authority_count':len(pkeys),'primary_identity_keys':sorted(pkeys),
            'primary_count_estimate':min(2,max(1,max([int(r['primary']) for r in cr] or [1]))),
            'secondary_semantic_pool_count':secondary_sem,'secondary_identity_keys':sorted(skeys),
            'secondary_count_estimate':secondary_visual_pool,
            'source_secondary_shortfall':max(0,3-secondary_visual_pool),
            'duration_rule_pass':min_seconds-1e-6<=dur<=max_seconds+1e-6,
            'primary_capacity_rule_pass':_required_primary_duration(len(pkeys))<=dur+0.08,
            'authority':'USER_RULES_PDF__3_TO_5_SECONDS__MAX_2_CONCURRENT_PRIMARY__3_TO_8_VISIBLE_SECONDARY_DETAILS',
            'card_compiler':group.get('partition_mode') or partition_mode,
        })

    scene_to_card={}
    for c in cards:
        for sid in c['source_scene_ids']:
            scene_to_card.setdefault(sid,[]).append(c['card_id'])
    scene_to_card={sid:(ids[0] if len(ids)==1 else ids) for sid,ids in scene_to_card.items()};hard=[]
    for c in cards:
        if not c['duration_rule_pass']:hard.append(f"{c['card_id']}: duration {c['duration_seconds']:.3f}s outside 3-5s")
        if not c['primary_capacity_rule_pass']:hard.append(f"{c['card_id']}: too many distinct primary handoffs for supplied preset durations")
    return {
        'schema':'HEXA_VISUAL_CARD_PLAN_V31','version':'31.0.9','cards':cards,'scene_to_card':scene_to_card,
        'hard_failures':hard,'pass':not hard,
        'compiler_summary':{'source_scene_count':len(rows),'visual_card_count':len(cards),'min_card_seconds':min_seconds,
            'max_card_seconds':max_seconds,'concurrency_rule':'MAX_TWO_PRIMARY_VISIBLE_AT_ONCE__TWO_LANE_WAVE_SCHEDULER',
            'secondary_rule':'VISIBLE_DETAILS_MAY_REMAIN_GROUPED__NO_BAD_CUTOUTS','partition_mode':partition_mode}
    }
