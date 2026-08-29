from __future__ import annotations
from dataclasses import dataclass, asdict


def _norm(v):
    return str(v or '').strip().upper().replace(' ','_').replace('-','_')


def _timing_map(alignment:dict)->dict[str,dict]:
    return {str(x.get('scene_id')):x for x in (alignment.get('scene_timings') or []) if x.get('scene_id')}


def _top_level_slots(v:dict)->int:
    slots=set()
    for u in v.get('units') or []:
        slot=str(u.get('composition_slot_id') or u.get('parent_semantic_unit_id') or u.get('semantic_unit_id') or u.get('physical_id') or '')
        if slot:slots.add(slot)
    return max(1,len(slots))


def _character_signature(v:dict)->tuple[bool,bool]:
    main=secondary=False
    for u in v.get('units') or []:
        t=_norm(u.get('semantic_type'))
        main |= t=='MAIN_CHARACTER'; secondary |= t=='SECONDARY_CHARACTER'
    return main,secondary


def build_visual_sequences(plan:dict, alignment:dict, vision_results:list[dict], *, fps:float=30.0)->dict:
    """Group audio scenes into continuity-aware *visual* sequences without changing narration timing.

    Scene boundaries remain immutable for audio/montage audit. A sequence is only a visual planning
    authority: micro beats may linger into the next scene, adjacent compatible scenes use an
    object-only bridge instead of a full-screen wash, and a short scene is not treated as an
    independent title card. No topic words or project-specific identifiers are used.
    """
    tm=_timing_map(alignment); vis={str(v.get('scene_id')):v for v in vision_results}; scenes=list(plan.get('scenes') or [])
    rows=[]; seqs=[]; current=[]; current_dur=0.0
    hard_break={'RESET','COMPARE','CONTRAST','CHAPTER','NEW_SECTION'}
    soft_join={'CONTINUE','ADD','REFLOW','CAUSE_EFFECT','PROCESS','FLOW','RESOLVE','UNSPECIFIED',''}

    def flush():
        nonlocal current,current_dur
        if not current:return
        seq_id=f'VSEQ_{len(seqs)+1:03d}'
        for i,r in enumerate(current):
            r['visual_sequence_id']=seq_id
            r['visual_sequence_index']=i
            r['visual_sequence_count']=len(current)
            r['visual_sequence_role']='SINGLE' if len(current)==1 else ('START' if i==0 else ('END' if i==len(current)-1 else 'BEAT'))
        seqs.append({'visual_sequence_id':seq_id,'scene_ids':[r['scene_id'] for r in current], 'duration_seconds':round(current_dur,6), 'scene_count':len(current), 'micro_scene_count':sum(1 for r in current if r['micro_scene'])})
        rows.extend(current);current=[];current_dur=0.0

    prev=None
    for i,s in enumerate(scenes):
        sid=str(s.get('scene_id')); t=tm.get(sid) or {}; start=float(t.get('start',0)); end=float(t.get('end',start+1/fps)); dur=max(1/fps,end-start); v=vis.get(sid,{})
        relation=_norm(s.get('relation_to_previous'))
        row={'scene_id':sid,'start_seconds':start,'end_seconds':end,'duration_seconds':dur,'relation_to_previous':relation,'top_level_slot_count':_top_level_slots(v),'micro_scene':dur<0.90,'short_scene':dur<1.35,'main_character':_character_signature(v)[0],'secondary_character':_character_signature(v)[1]}
        join=False
        if current:
            prevrow=current[-1]
            combined=current_dur+dur
            # Short beats and declared continuations belong to one visual sentence whenever the
            # sequence remains readable and not overcrowded. A hard semantic break always wins.
            if relation not in hard_break and len(current)<4 and combined<=6.4:
                if row['micro_scene'] or prevrow['micro_scene']:
                    join=True
                elif relation in soft_join and (prevrow['top_level_slot_count']+row['top_level_slot_count']<=6):
                    join=True
                elif dur<1.35 and prevrow['duration_seconds']<1.8:
                    join=True
        if not join:flush()
        current.append(row);current_dur+=dur;prev=row
    flush()

    by_id={r['scene_id']:r for r in rows}
    ordered=[by_id[str(s.get('scene_id'))] for s in scenes]
    for i,r in enumerate(ordered):
        same_prev=i>0 and ordered[i-1]['visual_sequence_id']==r['visual_sequence_id']
        same_next=i+1<len(ordered) and ordered[i+1]['visual_sequence_id']==r['visual_sequence_id']
        prev_dur=ordered[i-1]['duration_seconds'] if i>0 else 99.0
        incoming_hold=0.0
        if i>0 and same_prev and prev_dur<0.90:
            incoming_hold=min(0.38,max(0.14,0.78-prev_dur))
        r['incoming_carry_hold_seconds']=round(incoming_hold,6)
        r['outgoing_linger_requested']=bool(same_next and r['micro_scene'])
        r['boundary_strategy']='SEQUENCE_OBJECT_CARRY' if same_prev else ('OPEN_WHITE' if i==0 else 'OBJECT_MATCH_BLEND')
    for i,r in enumerate(ordered):
        next_hold=float(ordered[i+1].get('incoming_carry_hold_seconds',0.0)) if i+1<len(ordered) else 0.0
        r['minimum_perceived_exposure_seconds']=round(max(r['duration_seconds'],r['duration_seconds']+next_hold),6)
    return {
        'schema':'HEXA_VISUAL_SEQUENCE_PLAN_V31','version':'1.0','sequences':seqs,'scenes':ordered,
        'scene_count':len(ordered),'visual_sequence_count':len(seqs),'micro_scene_count':sum(1 for r in ordered if r['micro_scene']),
        'policy':'AUDIO_SCENE_BOUNDARIES_IMMUTABLE__VISUAL_SENTENCES_MAY_SPAN_SHORT_BEATS__NO_TOPIC_HARDCODING'
    }
