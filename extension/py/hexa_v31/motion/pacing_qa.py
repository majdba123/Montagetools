from __future__ import annotations

"""Card-level visual pacing diagnostics on the final authored motion clock.

This is deliberately read-only.  It measures semantic progression, readable holds,
front-loading and static tails after P3/P4 authoring so production replays can identify
whether a video feels rushed or stagnant without mistaking a legitimate hold for a bug.
"""

from collections import Counter

AUTHORITY='HEXA_FINAL_CARD_PACING_QA_V1'
_MEANINGFUL_BEATS={
    'ESTABLISH','OVERLAPPING_REVEAL','FOCUS_TRANSFER','COMPOSITION_REBUILD',
    'RESTORE_BEFORE_SEMANTIC_HANDOFF','SIMULTANEOUS_COHORT_DENSITY_FRAME',
    'SOLO_SOURCE_READABLE_FRAMING','RESTORE_SUPPORT_COMPOSITION',
}


def _physical_interval(event:dict)->tuple[float,float]:
    start=float(event.get('physical_start_seconds',event.get('start_seconds',0)))
    end=float(event.get('physical_end_seconds',event.get('end_seconds',start)))
    return start,max(start,end)


def _event_change_times(event:dict,card_start:float,card_end:float)->list[tuple[float,str]]:
    out=[]
    entry=event.get('preset_entry') or {}
    if entry:
        st=float(entry.get('start_seconds',event.get('start_seconds',card_start)))
        dur=float(entry.get('duration_seconds') or 0)
        out.append((max(card_start,min(card_end,st+max(0,dur))),'ENTRY_SETTLE'))
    hit=event.get('perceptual_hit_seconds')
    if hit is not None:
        out.append((max(card_start,min(card_end,float(hit))),'SEMANTIC_HIT'))
    for action in event.get('preset_actions') or []:
        if action.get('start_seconds') is not None:
            out.append((max(card_start,min(card_end,float(action['start_seconds']))),'PRESET_ACTION'))
    for key in ('composition_states','composition_participant_states'):
        for state in event.get(key) or []:
            beat=str(state.get('semantic_beat') or '')
            if beat not in _MEANINGFUL_BEATS:
                continue
            if state.get('start_seconds') is None:
                continue
            out.append((max(card_start,min(card_end,float(state['start_seconds']))),beat))
    return out


def _dedupe_times(rows:list[tuple[float,str]],epsilon:float=.12)->list[tuple[float,list[str]]]:
    if not rows:return []
    rows=sorted(rows,key=lambda x:(x[0],x[1]))
    groups=[]
    for t,kind in rows:
        if groups and abs(t-groups[-1][0])<=epsilon:
            groups[-1][1].append(kind)
        else:
            groups.append([t,[kind]])
    return [(round(float(t),6),sorted(set(kinds))) for t,kinds in groups]


def build_final_card_pacing_report(plan:dict)->dict:
    cards=list((plan.get('visual_cards') or {}).get('cards') or [])
    events=[e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density')]
    rows=[]
    counts=Counter()
    for card in cards:
        cid=str(card.get('card_id') or '')
        start=float(card.get('start_seconds',0));end=float(card.get('end_seconds',start));duration=max(.001,end-start)
        card_events=[e for e in events if str(e.get('visual_card_id') or '')==cid]
        changes=[]
        readable=[]
        semantic_anchor_count=0
        for event in card_events:
            changes.extend(_event_change_times(event,start,end))
            entry=event.get('preset_entry') or {}
            settled=max(float(event.get('settle_seconds',event.get('start_seconds',start))),
                        float(entry.get('start_seconds',event.get('start_seconds',start)))+float(entry.get('duration_seconds') or 0))
            ps,pe=_physical_interval(event)
            if pe>start and ps<end:readable.append(max(start,min(end,settled)))
            if event.get('perceptual_hit_seconds') is not None:semantic_anchor_count+=1
        beats=_dedupe_times(changes)
        beat_times=[t for t,_ in beats]
        first_readable=min(readable) if readable else start
        final_change=max(beat_times) if beat_times else start
        gaps=[]
        clock=[start]+beat_times+[end]
        for a,b in zip(clock,clock[1:]):gaps.append(max(0,b-a))
        largest=max(gaps or [duration]);static_tail=max(0,end-final_change)
        early_cut=start+duration*.45
        early_beats=sum(t<=early_cut for t in beat_times)
        front_ratio=early_beats/max(1,len(beat_times))
        flags=[]
        # Readable holds are healthy; only classify when the *distribution* is bad.
        if duration<1.35 and len(beat_times)>=3:
            flags.append('TOO_FAST')
        if duration>=2.8 and len(beat_times)>=2 and front_ratio>=.80 and static_tail>=max(1.15,duration*.28):
            flags.append('FRONT_LOADED')
        if duration>=3.0 and len(beat_times)<=1 and largest>=max(1.8,duration*.48):
            flags.append('TOO_SLOW')
        if duration>=2.8 and len(beat_times)>=2 and static_tail>=max(1.5,duration*.34):
            flags.append('STATIC_TAIL')
        classification=flags[0] if flags else 'HEALTHY'
        counts[classification]+=1
        for flag in flags[1:]:counts[flag]+=1
        rows.append({
            'card_id':cid,'duration_seconds':round(duration,6),'semantic_beat_count':len(beat_times),
            'first_readable_onset_seconds':round(first_readable,6),'final_meaningful_change_seconds':round(final_change,6),
            'static_tail_seconds':round(static_tail,6),'largest_no_progression_interval_seconds':round(largest,6),
            'audio_semantic_anchor_count':semantic_anchor_count,'front_loaded_beat_ratio':round(front_ratio,4),
            'classification':classification,'flags':flags,'beats':[{'time_seconds':t,'kinds':k} for t,k in beats],
        })
    return {
        'schema':'HEXA_FINAL_CARD_PACING_QA','version':AUTHORITY,'authority':AUTHORITY,
        'card_count':len(rows),'class_counts':dict(sorted(counts.items())),
        'healthy_count':sum(r['classification']=='HEALTHY' for r in rows),
        'review_required_count':sum(r['classification']!='HEALTHY' for r in rows),
        'cards':rows,'readable_hold_is_not_failure':True,
    }
