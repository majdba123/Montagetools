"""Backward-compatible composition solver facade.

Production planning imports this module, while the implementation lives under
``hexa_v31.layout``. The facade is also the compatibility boundary for V31's
pre-layout editorial phase policy: geometry remains owned by the existing
solver, but eligible same-scene actors are presented to it as progressive
co-occurrence states instead of one permanent poster state.
"""
from __future__ import annotations

import copy

from .layout import composition_solver as _implementation

globals().update({
    key: value
    for key, value in vars(_implementation).items()
    if key not in {'__name__', '__package__', '__loader__', '__spec__', '__file__', '__cached__'}
})

_BASE_BUILD_STORY_PHASES = _implementation.build_story_phases
_BASE_REPARTITION_STORY_PHASES = _implementation.repartition_story_phases
_PROGRESSIVE_AUTHORITY = 'PRE_LAYOUT_PROGRESSIVE_SCENE_BEATS_V1'
_MIN_BEAT_SECONDS = 0.72
_MIN_FINAL_REVEAL_SECONDS = 1.28
_EDITORIAL_TOPOLOGY_AUTHORITY = 'SEMANTIC_ARCHETYPE_TEMPORAL_TOPOLOGY_V2'


def _protected_react_semantics(event: dict) -> bool:
    """Protect only explicit P2 reaction semantics, not prose labels mentioning reaction.

    `SHOW_CUSTOMER_CONTEXT_OR_REACTION` is a broad narrative-function label used by
    ordinary context actors. Treating the substring REACTION as a hard P2 signal made
    those actors permanently bypass editorial staging even when their actual semantic
    intent is INTRODUCE/EXPLAIN. P2 remains protected when an explicit semantic field
    itself declares REACT/REACTION/RESPOND.
    """
    explicit = {
        str(event.get('semantic_intent') or '').strip().upper(),
        str(event.get('relationship') or '').strip().upper(),
        str(event.get('interaction_action') or '').strip().upper(),
        str(event.get('semantic_action') or '').strip().upper(),
    }
    return bool(explicit.intersection({'REACT','REACTION','RESPOND'}))


def _presenter_like(event:dict, roles:dict|None=None)->bool:
    role=str((roles or {}).get(_implementation._sid(event)) or '').upper()
    semantic_type=str(event.get('semantic_type') or '').upper()
    return role in {'NARRATOR','PRESENTER'} or 'CHARACTER' in semantic_type


def _progressive_same_scene_candidates(events: list[dict]) -> list[dict]:
    active = [e for e in events if not e.get('suppressed_by_card_density')]
    if not 2 <= len(active) <= 5:
        return []
    # Certified partitions/residuals are source-survival structures. Their
    # independent motion policy is already owned by P1/P2 and must not be
    # repartitioned here. This path is deliberately for independent roots.
    if any(str(e.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC' for e in active):
        return []
    if any(e.get('partition_group_id') for e in active):
        return []
    scenes = {str(e.get('scene_id') or '') for e in active}
    if len(scenes) != 1:
        return []
    # Explicit REACT is not a reason to collapse the whole scene into one poster.
    # P2 protects *causal order*: stimulus/object first, reaction subject second.
    # A progressive topology is therefore legal when at least one non-reaction
    # carrier exists; the reaction actor is forced into a later reveal below.
    reactions=[e for e in active if _protected_react_semantics(e)]
    if reactions and len(reactions)==len(active):
        return []
    return active


def _progressive_phase_count(duration: float, event_count: int) -> int:
    if event_count <= 1:
        return 1
    # A final support/result must have enough time to become readable and hold;
    # earlier boundaries may be tighter because retained actors span multiple
    # phases. Reduce beat count instead of squeezing the final reveal.
    upper = min(event_count, 4)
    for count in range(upper, 1, -1):
        required = (count - 1) * _MIN_BEAT_SECONDS + _MIN_FINAL_REVEAL_SECONDS
        if duration + 1e-9 >= required:
            return count
    return 1


def _progressive_cuts(card: dict, buckets: list[list[dict]]) -> list[float]:
    cs = float(card['start_seconds'])
    ce = float(card['end_seconds'])
    count = len(buckets)
    if count <= 1:
        return [cs, ce]
    duration = ce - cs
    cuts = [cs]
    for index in range(1, count):
        uniform = cs + duration * index / count
        incoming = buckets[index]
        voice_hits = [
            float(e.get('perceptual_hit_seconds'))
            for e in incoming
            if e.get('perceptual_hit_seconds') is not None
            and str(e.get('perceptual_hit_source') or '') == 'VOICE_TRIGGER'
        ]
        # APPEAR_HIGH_SCALE reaches its visual impact around 70% of 0.8s.
        # Open the beat before a trustworthy voice anchor; otherwise use an
        # even spoken-clock distribution rather than the old ~60ms burst.
        target = min(voice_hits) - 0.56 if voice_hits else uniform
        future_intermediate = max(0, count - index - 1)
        lo = cuts[-1] + _MIN_BEAT_SECONDS
        hi = ce - _MIN_FINAL_REVEAL_SECONDS - future_intermediate * _MIN_BEAT_SECONDS
        cuts.append(max(lo, min(hi, target)))
    cuts.append(ce)
    return cuts



def _phase_editorial_archetype(events:list[dict], grammar:dict)->str:
    """Classify one temporal phase instead of inheriting the whole card archetype.

    Adjacent narration scenes frequently share one 3-5s visual card. A character in the
    first scene must not force a later result/process/comparison scene into the same
    CHARACTER_EXPLAINS_OBJECT staging. This classifier uses only existing semantic roles,
    explicit edges and structural intent; it never reads project IDs or script literals.
    """
    if not events:return str((grammar or {}).get('archetype') or 'SINGLE_FOCUS')
    roles=(grammar or {}).get('roles') or {}
    semantic_ids={_implementation._sid(e) for e in events}
    edges=[ed for ed in ((grammar or {}).get('explicit_edges') or [])
           if str(ed.get('source_scope_id') or ed.get('source') or '') in semantic_ids
           and str(ed.get('target_scope_id') or ed.get('target') or '') in semantic_ids]
    phase_roles=[str(roles.get(_implementation._sid(e)) or 'SUPPORT').upper() for e in events]
    intents={str(e.get('semantic_intent') or e.get('narrative_function') or '').strip().upper() for e in events}
    characters=[e for e in events if 'CHARACTER' in str(e.get('semantic_type') or '').upper()]
    primary=[e for e in events if str(e.get('attention_priority') or '').upper()=='PRIMARY']
    blockers=any(r=='BLOCKER' for r in phase_roles)
    results=any(r in {'RESULT','TARGET'} for r in phase_roles)
    if blockers and edges:return 'SOURCE_BLOCKER_RESULT'
    if {'BEFORE','AFTER'}.issubset(intents):return 'BEFORE_AFTER'
    if ({'QUESTION','ANSWER'}.issubset(intents) or {'ASK','ANSWER'}.issubset(intents)):return 'QUESTION_ANSWER'
    if results and len(events)>=2:return 'RESULT_PAYOFF'
    if len(primary)>=2 and not characters and not edges:return 'COMPARISON'
    if len(edges)>=2 and len(semantic_ids)>=3:return 'FLOW_PIPELINE'
    if edges:return 'CAUSE_EFFECT'
    if characters and len(events)>=2:return 'CHARACTER_EXPLAINS_OBJECT'
    if len(primary)==1 and len(events)>=4:return 'HUB_AND_SPOKES'
    return 'SINGLE_FOCUS'


def _phase_focus_event(events:list[dict], grammar:dict, archetype:str)->dict|None:
    """Choose one semantic focus for an anchor-owned phase without inventing content."""
    if not events:return None
    roles=(grammar or {}).get('roles') or {}
    def role(event):return str(roles.get(_implementation._sid(event)) or '').upper()
    if archetype in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT','CAUSE_EFFECT'}:
        row=next((e for e in events if role(e) in {'RESULT','TARGET'}),None)
        if row is not None:return row
    if archetype=='CHARACTER_EXPLAINS_OBJECT':
        row=next((e for e in events if not _presenter_like(e,roles)
                  and str(e.get('attention_priority') or '').upper()=='PRIMARY'),None)
        if row is not None:return row
        row=next((e for e in events if not _presenter_like(e,roles)),None)
        if row is not None:return row
    if archetype=='FLOW_PIPELINE':
        row=next((e for e in reversed(events) if role(e) in {'RESULT','TARGET','LEAD','ACTOR'}),None)
        if row is not None:return row
    row=next((e for e in reversed(events) if str(e.get('attention_priority') or '').upper()=='PRIMARY'),None)
    return row or events[-1]


def _annotate_fallback_editorial_phases(plan:dict, events:list[dict], grammar:dict)->dict:
    """Add focus/hierarchy to legacy anchor timing while preserving P1 geometry."""
    out=copy.deepcopy(plan)
    by_id={str(e.get('event_id')):e for e in events}
    editorial_count=0
    for phase in out.get('phases') or []:
        phase_events=[by_id[str(eid)] for eid in (phase.get('event_ids') or []) if str(eid) in by_id]
        if not phase_events:continue
        arch=_phase_editorial_archetype(phase_events,grammar)
        phase.setdefault('editorial_archetype',arch)
        root_events=[e for e in phase_events if str(e.get('render_mode') or 'ROOT_ATOMIC')=='ROOT_ATOMIC'
                     and not e.get('partition_group_id')]
        if len(root_events)!=len(phase_events):continue
        focus=_phase_focus_event(phase_events,grammar,arch)
        if focus is not None:phase.setdefault('focus_event_id',str(focus.get('event_id')))
        phase.setdefault('semantic_beat','ESTABLISH' if len(phase_events)==1 else 'RELATIONSHIP_READ')
        phase['choreography_authority']=_PROGRESSIVE_AUTHORITY
        editorial_count+=1
    if editorial_count:
        out['choreography_authority']=_EDITORIAL_TOPOLOGY_AUTHORITY
        out['fallback_editorial_phase_count']=editorial_count
        out['fallback_editorial_authority']='ANCHOR_TIMING_PLUS_SEMANTIC_PHASE_GEOMETRY_V1'
    return out

def _progressive_plan(
    card: dict,
    events: list[dict],
    grammar: dict | None = None,
    *,
    validate_layout: bool = True,
) -> dict | None:
    active = _progressive_same_scene_candidates(events)
    if not active:
        return None
    cs = float(card['start_seconds'])
    ce = float(card['end_seconds'])
    duration = ce - cs
    phase_grammar = grammar or {'archetype': 'GENERIC', 'roles': {}, 'explicit_edges': []}
    ordered = list(_implementation._phase_order(active, phase_grammar))
    if len(ordered) < 2:
        return None

    roles = phase_grammar.get('roles') or {}
    archetype = str(phase_grammar.get('archetype') or 'SINGLE_FOCUS')
    def role(event: dict) -> str:
        return str(roles.get(_implementation._sid(event)) or 'SUPPORT')
    presenter = next((e for e in ordered if _presenter_like(e,roles)), None)
    result = next((e for e in ordered if role(e) in {'RESULT','TARGET'}), None)
    reactions=[e for e in ordered if _protected_react_semantics(e)]
    causal_sources=[e for e in ordered if e not in reactions]
    non_presenter_primary = next((e for e in ordered if e is not presenter and str(e.get('attention_priority') or '').upper() == 'PRIMARY'), None)
    if reactions and causal_sources:
        # P2 semantic authority: establish the stimulus/object before the reaction.
        anchor=next((e for e in causal_sources if str(e.get('attention_priority') or '').upper()=='PRIMARY'),causal_sources[0])
    elif archetype=='CHARACTER_EXPLAINS_OBJECT':
        # Establish the explained idea/object; the presenter enters as context. A main
        # character is not automatically the visual hero simply because it is primary.
        anchor = next((e for e in ordered if not _presenter_like(e,roles) and str(e.get('attention_priority') or '').upper()=='PRIMARY'),None)
        anchor = anchor or next((e for e in ordered if not _presenter_like(e,roles)),presenter or ordered[0])
    elif archetype in {'RESULT_PAYOFF','QUESTION_ANSWER'}:
        anchor = non_presenter_primary or next((e for e in ordered if e is not presenter), presenter or ordered[0])
    else:
        anchor = next((e for e in ordered if str(e.get('attention_priority') or '').upper() == 'PRIMARY'), ordered[0])
    ordered = [anchor] + [e for e in ordered if e is not anchor]
    phase_count = _progressive_phase_count(duration, len(ordered))
    if phase_count < 2:
        return None

    buckets: list[list[dict]] = [[] for _ in range(phase_count)]
    buckets[0].append(anchor)
    remaining = ordered[1:]
    if reactions:
        # Cause/stimulus carriers always precede protected reaction subjects.
        remaining=[e for e in remaining if e not in reactions]+[e for e in reactions if e in remaining]
    elif archetype in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'} and result in remaining:
        remaining=[e for e in remaining if e is not result]+[result]
    elif archetype=='CHARACTER_EXPLAINS_OBJECT' and presenter in remaining:
        remaining=[e for e in remaining if e is not presenter]+[presenter]
    slots = phase_count - 1
    for index, event in enumerate(remaining):
        # Spread later actors across the available clock. If actor count exceeds
        # beat capacity, only later beats may pair; never collapse into beat 1.
        slot = 1 + min(slots - 1, int(index * slots / max(1, len(remaining))))
        buckets[slot].append(event)

    cuts = _progressive_cuts(card, buckets)
    introduced: list[dict] = []
    rows = []
    reveal_order = []
    for index, newcomers in enumerate(buckets):
        for event in newcomers:
            if event not in introduced:
                introduced.append(event)
                reveal_order.append(str(event.get('event_id')))

        # Retention is archetype-owned. A process advances its carrier instead
        # of pinning stage one forever; comparisons retain the first term;
        # payoff structures keep context until the result assumes focus.
        if archetype=='FLOW_PIPELINE':
            prior=[] if index==0 else [event for event in buckets[index-1][-1:] if event not in newcomers]
            phase_events=(prior+newcomers) or [anchor]
        elif archetype=='BEFORE_AFTER' and index==phase_count-1:
            phase_events=([introduced[-2]] if len(introduced)>1 else [])+newcomers
        else:
            phase_events = [anchor]
            primary_count = 1 if str(anchor.get('attention_priority') or '').upper() == 'PRIMARY' else 0
            for event in reversed(introduced):
                if event is anchor:
                    continue
                incoming_primary = str(event.get('attention_priority') or '').upper() == 'PRIMARY'
                if incoming_primary and primary_count >= 2:
                    continue
                phase_events.append(event)
                primary_count += int(incoming_primary)
                if len(phase_events) >= 3:
                    break
        phase_events.sort(key=lambda e: ordered.index(e))
        focus = newcomers[-1] if newcomers else phase_events[-1]
        # A narrator entering an explanatory composition is supporting context, not an
        # automatic new hero. Keep the explained object/idea as focus unless semantic
        # grammar explicitly classifies a result/payoff actor. This prevents the repeated
        # 'object shrinks -> presenter owns the side' pattern seen across unrelated cards.
        if archetype=='CHARACTER_EXPLAINS_OBJECT' and presenter is not None and focus is presenter:
            focus=anchor if anchor is not presenter else next((e for e in phase_events if e is not presenter),focus)
        if archetype in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'} and result in phase_events and index==phase_count-1:
            focus=result
        beat = 'ESTABLISH' if index == 0 else ('COMPOSITION_REBUILD' if index == phase_count-1 else 'SUPPORT_REVEAL')
        if archetype=='FLOW_PIPELINE':beat='PROCESS_ESTABLISH' if index==0 else ('PROCESS_RESULT' if index==phase_count-1 else 'PROCESS_ADVANCE')
        elif archetype=='COMPARISON':beat='COMPARE_ESTABLISH' if index==0 else ('COMPARE_CONCLUDE' if index==phase_count-1 else 'COMPARE_REVEAL')
        elif archetype in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'}:beat='PAYOFF' if index==phase_count-1 else ('CONTEXT_ESTABLISH' if index==0 else 'CONTEXT_DEVELOP')
        elif archetype=='BEFORE_AFTER':beat='BEFORE_ESTABLISH' if index==0 else ('AFTER_REVEAL' if index==phase_count-1 else 'TRANSITION')
        rows.append({
            'phase_id': f"{card.get('card_id')}_PB{index + 1}",
            'start_seconds': round(cuts[index], 6),
            'end_seconds': round(cuts[index + 1], 6),
            'event_ids': [str(e.get('event_id')) for e in phase_events],
            'entering_event_ids': [str(e.get('event_id')) for e in newcomers],
            'retained_event_ids': [
                str(e.get('event_id')) for e in phase_events if e not in newcomers
            ],
            'semantic_beat': beat,
            'focus_event_id': str(focus.get('event_id')),
            'editorial_archetype': archetype,
            'choreography_authority': _EDITORIAL_TOPOLOGY_AUTHORITY,
        })

    candidate = {
        'schema': 'HEXA_VISUAL_STORY_PHASES_V31_PROGRESSIVE',
        'phases': rows,
        'phase_count': len(rows),
        'progressive_reveal_compiled': True,
        'choreography_authority': _EDITORIAL_TOPOLOGY_AUTHORITY,
        'reveal_order_event_ids': reveal_order,
        'max_simultaneous_actor_count': max(len(row['event_ids']) for row in rows),
        'audio_anchor_policy': 'VOICE_TRIGGER_WHEN_AVAILABLE__EVEN_SPOKEN_CLOCK_FALLBACK',
        'retention_policy': 'FOCAL_PLUS_TWO_MOST_RECENT_SOURCE_ACTORS',
        'minimum_final_reveal_seconds': _MIN_FINAL_REVEAL_SECONDS,
        'atomic_asset_indivisibility': True,
    }
    if validate_layout and not _implementation.solve_card_layout(active, phase_grammar, candidate).get('pass'):
        return None
    return candidate


def _progressivize_repartitioned_plan(
    card: dict,
    events: list[dict],
    grammar: dict,
    fallback: dict,
) -> dict | None:
    """Split eligible same-scene cohorts inside a multi-scene card.

    Production cards commonly contain several short source scenes. Treating
    the whole card as the eligibility scope made the progressive compiler skip
    every same-scene pair as soon as an adjacent scene shared the card. The
    legacy repartitioner already owns those semantic scene windows, so refine
    only a sufficiently long window and leave all cross-scene handoffs intact.
    """
    by_id = {str(e.get('event_id')): e for e in events}
    def _reveal_group_key(event:dict)->str:
        # Certified child/residual pixels that reconstruct one source root reveal as one
        # editorial group. This stages source evidence without pretending one partition
        # fragment is an independent semantic idea or altering its protected geometry.
        mode=str(event.get('render_mode') or 'ROOT_ATOMIC')
        root=str(event.get('partition_root_id') or event.get('partition_group_id') or '')
        if mode in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} and root:
            return 'PARTITION_ROOT::'+root
        return 'EVENT::'+str(event.get('event_id'))

    scene_group_counts: dict[str, set[str]] = {}
    for event in events:
        sid=str(event.get('scene_id') or '')
        scene_group_counts.setdefault(sid,set()).add(_reveal_group_key(event))
    rows: list[dict] = []
    reveal_order: list[str] = []
    split_count = 0
    source_phases = copy.deepcopy(fallback.get('phases') or [])
    for phase_index, phase in enumerate(source_phases):
        phase_events = [by_id[eid] for eid in phase.get('event_ids') or [] if eid in by_id]
        groups: dict[str, list[dict]] = {}
        for event in phase_events:
            # P1 partition members reveal as indivisible source groups. Explicit P2
            # reaction actors remain eligible for temporal staging because the compiler
            # below enforces cause-before-reaction rather than simultaneous poster timing.
            groups.setdefault(str(event.get('scene_id') or ''), []).append(event)
        cohorts=[]
        for sid,group in groups.items():
            reveal_groups={_reveal_group_key(event) for event in group}
            if 2<=len(reveal_groups)<=5 and len(group)<=8 and len(scene_group_counts.get(sid,set()))<=5:
                cohorts.append(group)
        duration = float(phase.get('end_seconds', 0.0)) - float(phase.get('start_seconds', 0.0))
        cohort = cohorts[0] if len(cohorts) == 1 else None
        if cohort is None:
            row = dict(phase)
            row.setdefault('entering_event_ids', list(row.get('event_ids') or []))
            row.setdefault('retained_event_ids', [])
            ids=list(row.get('event_ids') or [])
            if ids:
                row.setdefault('focus_event_id', ids[-1])
                row.setdefault('editorial_archetype', _phase_editorial_archetype(phase_events,grammar))
            rows.append(row)
            for eid in row.get('event_ids') or []:
                if eid not in reveal_order:
                    reveal_order.append(eid)
            continue

        ordered = list(_implementation._phase_order(cohort, grammar))
        cohort_archetype=_phase_editorial_archetype(cohort,grammar)
        reactions=[e for e in ordered if _protected_react_semantics(e)]
        causal=[e for e in ordered if e not in reactions]
        if reactions and causal:
            anchor=next((e for e in causal if str(e.get('attention_priority') or '').upper()=='PRIMARY'),causal[0])
            ordered=[anchor]+[e for e in ordered if e is not anchor and e not in reactions]+reactions
        elif cohort_archetype=='CHARACTER_EXPLAINS_OBJECT':
            roles=grammar.get('roles') or {}
            anchor=next((e for e in ordered if not _presenter_like(e,roles) and str(e.get('attention_priority') or '').upper()=='PRIMARY'),None)
            anchor=anchor or next((e for e in ordered if not _presenter_like(e,roles)),ordered[0])
            ordered=[anchor]+[e for e in ordered if e is not anchor]
        else:
            anchor = next((e for e in ordered if str(e.get('attention_priority') or '').upper() == 'PRIMARY'), ordered[0])
        anchor_group=_reveal_group_key(anchor)
        # Keep every certified fragment of the chosen source root together. Other roots
        # enter later, but once revealed all source evidence remains retained.
        first_group=[e for e in ordered if _reveal_group_key(e)==anchor_group]
        later_groups=[];seen_groups={anchor_group}
        for event in ordered:
            key=_reveal_group_key(event)
            if key in seen_groups:continue
            seen_groups.add(key);later_groups.append([e for e in ordered if _reveal_group_key(e)==key])
        ordered=[*first_group,*[e for group in later_groups for e in group]]
        delayed_ids=[str(e.get('event_id')) for group in later_groups for e in group]
        anchor_id=str(anchor.get('event_id'))
        start = float(phase['start_seconds'])
        end = float(phase['end_seconds'])
        next_phase = source_phases[phase_index + 1] if phase_index + 1 < len(source_phases) else None
        handoff_extension = bool(
            next_phase and anchor_id in (next_phase.get('event_ids') or [])
            and delayed_ids and delayed_ids[-1] not in (next_phase.get('event_ids') or [])
        )
        short_final=max(.72,min(_MIN_FINAL_REVEAL_SECONDS,duration-_MIN_BEAT_SECONDS))
        if duration + 1e-9 < (_MIN_BEAT_SECONDS + (0.10 if handoff_extension else short_final)):
            row = dict(phase)
            row.setdefault('entering_event_ids', list(row.get('event_ids') or []))
            row.setdefault('retained_event_ids', [])
            ids=list(row.get('event_ids') or [])
            if ids:
                row.setdefault('focus_event_id', ids[-1])
                row.setdefault('editorial_archetype', _phase_editorial_archetype(phase_events,grammar))
            rows.append(row)
            for eid in row.get('event_ids') or []:
                if eid not in reveal_order:
                    reveal_order.append(eid)
            continue
        if handoff_extension:
            retained_id = delayed_ids[-1]
            next_phase['event_ids'] = [retained_id if eid == anchor_id else eid for eid in next_phase.get('event_ids') or []]
            next_phase['progressive_focus_transfer_from_event_id'] = anchor_id
            next_phase['progressive_focus_transfer_to_event_id'] = retained_id
        voice_hits = [
            float(e['perceptual_hit_seconds']) for e in ordered[1:]
            if e.get('perceptual_hit_seconds') is not None
            and str(e.get('perceptual_hit_source') or '') == 'VOICE_TRIGGER'
        ]
        target = min(voice_hits) - 0.56 if voice_hits else start + duration * 0.45
        latest_cut = end - (0.10 if handoff_extension else short_final)
        cut = max(start + _MIN_BEAT_SECONDS, min(latest_cut, target))
        original_ids = list(phase.get('event_ids') or [])
        first_ids = [eid for eid in original_ids if eid not in delayed_ids]
        if anchor_id not in first_ids:
            first_ids.append(anchor_id)
        common = {
            'semantic_boundary_authority': phase.get('semantic_boundary_authority', 'ADJACENT_ANCHOR_MIDPOINT'),
            'choreography_authority': _EDITORIAL_TOPOLOGY_AUTHORITY,
        }
        rows.append({
            **common,
            'phase_id': f"{phase.get('phase_id')}_PB1",
            'start_seconds': round(start, 6),
            'end_seconds': round(cut, 6),
            'event_ids': first_ids,
            'entering_event_ids': [eid for eid in first_ids if eid not in reveal_order],
            'retained_event_ids': [eid for eid in first_ids if eid in reveal_order],
            'semantic_beat': 'ESTABLISH',
            'focus_event_id': anchor_id,
            'editorial_archetype': cohort_archetype,
        })
        for eid in first_ids:
            if eid not in reveal_order:
                reveal_order.append(eid)
        pb2_focus=delayed_ids[-1] if delayed_ids else anchor_id
        archetype=cohort_archetype
        if archetype=='CHARACTER_EXPLAINS_OBJECT':
            roles=grammar.get('roles') or {}
            def _event_role(eid):
                ev=by_id.get(str(eid));return str(roles.get(_implementation._sid(ev)) or '') if ev else ''
            if _event_role(pb2_focus)=='NARRATOR':
                pb2_focus=next((eid for eid in original_ids if _event_role(eid)!='NARRATOR'),anchor_id)
        rows.append({
            **common,
            'phase_id': f"{phase.get('phase_id')}_PB2",
            'start_seconds': round(cut, 6),
            'end_seconds': round(end, 6),
            'event_ids': original_ids,
            'entering_event_ids': delayed_ids,
            'retained_event_ids': [eid for eid in original_ids if eid not in delayed_ids],
            'semantic_beat': 'COMPOSITION_REBUILD',
            'focus_event_id': pb2_focus,
            'editorial_archetype': archetype,
            'retained_into_next_semantic_phase': handoff_extension,
        })
        for eid in delayed_ids:
            if eid not in reveal_order:
                reveal_order.append(eid)
        split_count += 1

    if not split_count:
        return None
    candidate = dict(fallback)
    candidate.update({
        'schema': 'HEXA_VISUAL_STORY_PHASES_V31_PROGRESSIVE',
        'phases': rows,
        'phase_count': len(rows),
        'progressive_reveal_compiled': True,
        'progressive_scene_cohort_count': split_count,
        'choreography_authority': _EDITORIAL_TOPOLOGY_AUTHORITY,
        'reveal_order_event_ids': reveal_order,
        'retention_policy': 'LEGACY_SEMANTIC_HANDOFF_PLUS_PROGRESSIVE_SCENE_COHORT',
        'minimum_final_reveal_seconds': _MIN_FINAL_REVEAL_SECONDS,
    })
    # Do not reject a semantically valid temporal split against one card-wide solve.
    # `solve_phase_layouts` is the authoritative phase-local geometry gate immediately
    # downstream and will fall back per phase if a local composition is infeasible.
    return candidate



def _compile_focus_transfer_tails(plan:dict, events:list[dict], grammar:dict)->dict:
    """Turn readable relationships/handoffs into a real focal resolution beat.

    The relationship stays visible long enough to understand. Then context retires and
    the semantic focus owns a bounded payoff tail. Cross-scene atomic focus gets a shorter
    eligibility threshold because carrying the previous scene's presenter/context for the
    whole next scene is exactly the repeated-poster failure this compiler must avoid.
    """
    arch=str((grammar or {}).get('archetype') or '').upper()
    allowed={'CHARACTER_EXPLAINS_OBJECT','RESULT_PAYOFF','SOURCE_BLOCKER_RESULT','QUESTION_ANSWER','SINGLE_FOCUS','GENERIC','FLOW_PIPELINE','COMPARISON','BEFORE_AFTER'}
    if arch not in allowed:return plan
    by_id={str(e.get('event_id')):e for e in events}
    rows=[];changed=0
    for phase in plan.get('phases') or []:
        ids=[str(x) for x in (phase.get('event_ids') or []) if str(x) in by_id]
        start=float(phase.get('start_seconds',0));end=float(phase.get('end_seconds',start));dur=end-start
        focus=str(phase.get('focus_event_id') or (ids[-1] if ids else ''))
        focus_event=by_id.get(focus)
        focus_scene=str((focus_event or {}).get('scene_id') or '')
        cross_scene_atomic=bool(focus_event and focus_event.get('composite_atomic') and any(
            str(by_id[eid].get('scene_id') or '')!=focus_scene for eid in ids if eid!=focus))
        base_safe=all(str(by_id[eid].get('render_mode') or 'ROOT_ATOMIC')=='ROOT_ATOMIC' and not by_id[eid].get('partition_group_id') for eid in ids)
        # A protected reaction from the previous semantic beat may retire at a new-scene
        # handoff; P2 protects cause-before-reaction order, not indefinite persistence.
        reaction_safe=all((not _protected_react_semantics(by_id[eid])) or cross_scene_atomic or eid==focus for eid in ids)
        if cross_scene_atomic:
            threshold=1.30
        elif arch in {'CHARACTER_EXPLAINS_OBJECT','QUESTION_ANSWER'}:
            threshold=1.18
        elif arch in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'}:
            threshold=1.34
        else:
            threshold=1.70
        eligible=(len(ids)>=2 and focus in ids and dur>=threshold and base_safe and reaction_safe)
        if not eligible:
            rows.append(phase);continue
        if cross_scene_atomic:
            tail=min(1.08,max(.78,dur*.54));min_relation=.46
        elif arch in {'CHARACTER_EXPLAINS_OBJECT','QUESTION_ANSWER'} and dur<1.70:
            tail=min(.72,max(.56,dur*.46));min_relation=.54
        else:
            tail=min(1.30,max(1.00,dur*.44));min_relation=.66
        split=end-tail
        if split-start<min_relation:
            rows.append(phase);continue
        relation=copy.deepcopy(phase);relation['end_seconds']=round(split,6)
        relation['semantic_beat']=relation.get('semantic_beat') or 'RELATIONSHIP_READ'
        relation['focus_transfer_tail_compiled']=True
        tail_phase=copy.deepcopy(phase)
        tail_phase.update({
            'phase_id':f"{phase.get('phase_id')}_FT",
            'start_seconds':round(split,6),'end_seconds':round(end,6),
            'event_ids':[focus],'entering_event_ids':[],
            'retained_event_ids':[focus],'focus_event_id':focus,
            'semantic_beat':'PAYOFF' if arch in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'} or cross_scene_atomic else 'FOCUS_TRANSFER',
            'focus_transfer_from_event_ids':[eid for eid in ids if eid!=focus],
            'focus_transfer_tail_compiled':True,
            'cross_scene_atomic_payoff':cross_scene_atomic,
            'choreography_authority':_EDITORIAL_TOPOLOGY_AUTHORITY,
        })
        rows.extend([relation,tail_phase]);changed+=1
    if not changed:return plan
    out=copy.deepcopy(plan);out['phases']=rows;out['phase_count']=len(rows)
    out['focus_transfer_tail_count']=changed
    out['focus_transfer_tail_authority']='SEMANTIC_RELATIONSHIP_TO_FOCAL_RESOLUTION_V2'
    out['choreography_authority']=_EDITORIAL_TOPOLOGY_AUTHORITY
    return out


def build_story_phases(card: dict, events: list[dict], grammar: dict) -> dict:
    """Build progressive same-scene beats before final geometry is solved."""
    progressive = _progressive_plan(card, events, grammar)
    if progressive is not None:
        return _compile_focus_transfer_tails(progressive,events,grammar)
    # Preserve the production planner's anchor-owned multi-scene topology.
    # The old generic card builder can merge adjacent source scenes into one
    # permanent state; anchor repartition keeps their semantic clocks intact.
    fallback = _BASE_REPARTITION_STORY_PHASES(card, events, [])
    refined = _progressivize_repartitioned_plan(card, events, grammar, fallback)
    if refined is not None:
        return _compile_focus_transfer_tails(refined,events,grammar)
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'ANCHOR_OWNED_PHASE_TOPOLOGY')
    fallback=_annotate_fallback_editorial_phases(fallback,events,grammar)
    return _compile_focus_transfer_tails(fallback,events,grammar)


def solve_phase_layouts(events:list[dict],grammar:dict,phase_plan:dict)->dict:
    """Compile trajectory-safe phase hierarchy with true solo hero geometry.

    Multi-actor relationship phases keep the card-wide collision-certified centers and
    express focus through hierarchy. Solo establishment/payoff phases may use the safe
    center and a larger scale. This keeps the temporal edit materially different without
    asking two large actors to cross through each other during a reveal.
    """
    by_id={str(event.get('event_id')):event for event in events if not event.get('suppressed_by_card_density')}
    stable=solve_card_layout(list(by_id.values()),grammar,phase_plan)
    if not stable.get('pass'):
        return stable
    if phase_plan.get('choreography_authority') != _EDITORIAL_TOPOLOGY_AUTHORITY:
        return dict(stable,phase_placements={},editorial_geometry_authority='PROTECTED_OR_LEGACY_TOPOLOGY')
    phase_placements={}
    previous_ids=set()
    previous_chosen={}
    for phase in phase_plan.get('phases') or []:
        ids=[str(event_id) for event_id in phase.get('event_ids') or [] if str(event_id) in by_id]
        if not ids:continue
        focus_id=str(phase.get('focus_event_id') or ids[-1])
        chosen={event_id:copy.deepcopy(stable['placements'][event_id]) for event_id in ids}
        if len(ids)==1:
            event_id=ids[0];event=by_id[event_id]
            protected=(str(event.get('render_mode') or 'ROOT_ATOMIC') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}
                       or bool(event.get('partition_group_id')) or _protected_react_semantics(event))
            placement=chosen[event_id];fp=_implementation._fp(event)
            if not protected:
                hero_center=(.50,.52);safe_scale=None
                stable_scale=float(stable['placements'][event_id]['scale'])
                for candidate in _implementation._scale_candidates(fp,fp.primary):
                    rect=_implementation._rect(hero_center,fp,float(candidate)*_implementation.MOTION_ENVELOPE_SCALE)
                    if _implementation._in_safe(rect):safe_scale=float(candidate);break
                if safe_scale is not None:
                    placement['center_norm']=[.50,.52]
                    placement['scale']=round(safe_scale,6)
            rect=_implementation._rect(tuple(placement['center_norm']),fp,float(placement['scale'])*_implementation.MOTION_ENVELOPE_SCALE)
            placement['rect_norm']=[round(x,6) for x in rect];placement['phase_focus']=True;placement['phase_geometry_protected']=protected
        else:
            # Solve the geometry against actors that *actually coexist in this phase*.
            # A card-wide solve is still the fallback/certification anchor, but it may
            # shrink a wide illustration merely to reserve room for an actor that enters
            # in another semantic beat. A phase-local solve removes that false occupancy
            # and gives wide/source-atomic ideas enough canvas to read.
            local_plan={'phases':[{'phase_id':'PHASE_LOCAL','event_ids':ids}]}
            phase_grammar=dict(grammar or {})
            phase_grammar['archetype']=str(phase.get('editorial_archetype') or grammar.get('archetype') or 'SINGLE_FOCUS')
            local=_implementation.solve_card_layout([by_id[event_id] for event_id in ids],phase_grammar,local_plan)
            local_placements=(local.get('placements') or {}) if local.get('pass') else {}
            protected_by_id={}
            items=[]
            for event_id in ids:
                event=by_id[event_id];fp=_implementation._fp(event)
                # P1 physical partitions keep their certified geometry. P2 reaction is a
                # timing/causal invariant, not a requirement to preserve the old poster
                # center; its layout may participate in a safe semantic composition.
                protected=(str(event.get('render_mode') or 'ROOT_ATOMIC') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}
                           or bool(event.get('partition_group_id')))
                retained=event_id in previous_ids and event_id in previous_chosen
                if protected:
                    source_placement=stable['placements'][event_id]
                elif retained:
                    # Retained context must not swap sides when a new actor enters.
                    # Pin its center to the prior semantic phase and express focus
                    # transfer through scale/hierarchy. This makes the entire interpolated
                    # transition safe instead of merely certifying two safe endpoints.
                    source_placement=previous_chosen[event_id]
                else:
                    source_placement=local_placements.get(event_id) or stable['placements'][event_id]
                chosen[event_id]=copy.deepcopy(source_placement)
                base=float(source_placement['scale'])
                protected_by_id[event_id]=protected
                items.append((event_id,event,fp,base,protected,retained))
            # Place pinned/protected context first so an entering focus searches the
            # remaining phase-local negative space rather than forcing a side swap.
            items.sort(key=lambda row:(0 if row[4] or row[5] else 1,0 if row[0]!=focus_id else 1,str(row[0])))
            states=[(0.0,[])]
            for event_id,event,fp,base,protected,retained in items:
                phase_arch=str(phase_grammar.get('archetype') or 'SINGLE_FOCUS')
                local_center=tuple((local_placements.get(event_id) or {}).get('center_norm') or chosen[event_id]['center_norm'])
                stable_center=tuple(stable['placements'][event_id]['center_norm'])
                if protected or retained:
                    center_candidates=[tuple(chosen[event_id]['center_norm'])]
                else:
                    center_candidates=[]
                    for center in [local_center,stable_center,*_implementation._adaptive_slots(phase_arch,str(chosen[event_id].get('role') or 'SUPPORT'),fp)]:
                        center=(round(float(center[0]),6),round(float(center[1]),6))
                        if center not in center_candidates:center_candidates.append(center)
                if protected:
                    scale_candidates=[base]
                else:
                    all_scales=[float(x) for x in _implementation._scale_candidates(fp,fp.primary)]
                    if event_id==focus_id:
                        # Focus can use any source-safe scale in the phase; density is a
                        # phase concern, not a card-wide multiplier.
                        scale_candidates=all_scales
                    else:
                        # Retained context stays readable but does not compete with focus.
                        ceiling=max(base,base*1.18);floor=max(.22,base*.68)
                        scale_candidates=[x for x in all_scales if floor-1e-9<=x<=ceiling+1e-9]
                        scale_candidates=sorted(set(scale_candidates+[base]),reverse=True)
                next_states=[]
                for cost,placed in states:
                    for center_index,center in enumerate(center_candidates):
                        for scale in scale_candidates:
                            rect=_implementation._rect(center,fp,scale*_implementation.MOTION_ENVELOPE_SCALE)
                            if not _implementation._in_safe(rect):continue
                            safe=True
                            for _,other_rect,other_fp,_,_ in placed:
                                gap=_implementation.PRIMARY_GAP if (fp.primary or other_fp.primary) else _implementation.SUPPORT_GAP
                                if _implementation._inter(_implementation._inflate(rect,gap),_implementation._inflate(other_rect,gap))>1e-8:
                                    safe=False;break
                            if not safe:continue
                            # Prefer a strong focal hierarchy and enough total visible ink,
                            # while keeping retained context above a readable floor.
                            visible=rect[2]*rect[3]*fp.fill
                            row_cost=-visible*(11.0 if event_id==focus_id else 3.0)
                            if event_id==focus_id:row_cost-=scale*.8
                            elif scale<base*.76:row_cost+=(base*.76-scale)*3.0
                            # Local semantic slots are preferred; later fallback slots are
                            # available only to preserve collision-safe continuity.
                            row_cost+=center_index*.035
                            next_states.append((cost+row_cost,placed+[(event_id,rect,fp,scale,center)]))
                if not next_states:
                    states=[];break
                next_states.sort(key=lambda row:row[0]);states=next_states[:256]
            if states:
                scored=[]
                for base_cost,placed in states:
                    occ=sum(r[1][2]*r[1][3]*r[2].fill for r in placed)
                    # Relationship compositions should feel occupied without turning
                    # into a wall of art. Penalize both sparse and overloaded solutions.
                    density_penalty=max(0.0,.27-occ)*28.0+max(0.0,occ-.56)*20.0
                    scored.append((base_cost+density_penalty,placed))
                _,best=min(scored,key=lambda row:row[0])
                selected={}
                for event_id,rect,fp,scale,center in best:
                    row=copy.deepcopy(chosen[event_id]);row['center_norm']=[round(float(center[0]),6),round(float(center[1]),6)];row['scale']=round(scale,6);row['rect_norm']=[round(x,6) for x in rect]
                    row['phase_focus']=event_id==focus_id;row['phase_geometry_protected']=protected_by_id[event_id];selected[event_id]=row
                chosen=selected
            else:
                for event_id,placement in chosen.items():
                    placement['phase_focus']=event_id==focus_id;placement['phase_geometry_protected']=protected_by_id[event_id]
        phase_placements[str(phase.get('phase_id'))]=chosen
        previous_ids=set(ids)
        previous_chosen={event_id:copy.deepcopy(row) for event_id,row in chosen.items()}
    return {'pass':True,'placements':stable['placements'],'phase_placements':phase_placements,
            'archetype':grammar.get('archetype'),'phase_aware':True,
            'search_mode':'SEMANTIC_ARCHETYPE_TRAJECTORY_SAFE_HIERARCHY',
            'editorial_geometry_authority':_EDITORIAL_TOPOLOGY_AUTHORITY}


def repartition_story_phases(card: dict, events: list[dict], conflicts: list[dict]) -> dict:
    """Preserve progressive beat topology through the planner's repartition gate.

    The production planner historically calls semantic repartition before its
    first geometry solve. With fallback semantic hits that legacy function
    groups every independent root into one R1 phase, exactly recreating the
    simultaneous poster state. Eligible same-scene roots therefore receive the
    progressive temporal topology here. The production planner immediately
    solves that topology with its real classified grammar, so this wrapper does
    not weaken or replace the hard layout/collision gate.
    """
    grammar=card.get('universal_scene_grammar') or {'archetype':'GENERIC','roles':{},'explicit_edges':[]}
    progressive = _progressive_plan(card, events, grammar, validate_layout=False)
    if progressive is not None:
        progressive['repartition_trigger_conflict_count'] = len(conflicts or [])
        progressive['repartition_policy'] = 'PRESERVE_PROGRESSIVE_TEMPORAL_TOPOLOGY'
        return _compile_focus_transfer_tails(progressive,events,grammar)
    fallback = _BASE_REPARTITION_STORY_PHASES(card, events, conflicts)
    refined = _progressivize_repartitioned_plan(card, events, grammar, fallback)
    if refined is not None:
        refined['repartition_trigger_conflict_count'] = len(conflicts or [])
        refined['repartition_policy'] = 'PRESERVE_PROGRESSIVE_TEMPORAL_TOPOLOGY'
        return _compile_focus_transfer_tails(refined,events,grammar)
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'LEGACY_REPARTITION_FALLBACK')
    fallback=_annotate_fallback_editorial_phases(fallback,events,grammar)
    return _compile_focus_transfer_tails(fallback,events,grammar)


def _expand_retained_phase_spans(phase_plan: dict, active_ids: set[str]) -> tuple[dict, int]:
    """Make layout co-occurrence match the scheduler's retained-carrier clock.

    ``_phase_for_event`` deliberately keeps a retained actor alive from its first
    listed phase through its last listed phase. A sparse phase plan can therefore
    omit that actor from an intermediate row while the renderer still owns a
    physical carrier there. Geometry must reserve that intermediate phase too;
    otherwise two actors can legally reuse one slot in the solver and collide at
    runtime. This expands only co-occurrence metadata. It never retimes, deletes,
    scales, or otherwise mutates source actors.
    """
    expanded = copy.deepcopy(phase_plan)
    phases = list(expanded.get('phases') or [])
    memberships: dict[str, list[int]] = {}
    for index, phase in enumerate(phases):
        for raw_id in phase.get('event_ids') or []:
            event_id = str(raw_id)
            if event_id in active_ids:
                memberships.setdefault(event_id, []).append(index)
    inserted = 0
    for event_id, indices in memberships.items():
        if len(indices) < 2:
            continue
        first, last = min(indices), max(indices)
        for index in range(first, last + 1):
            ids = phases[index].setdefault('event_ids', [])
            if event_id in ids:
                continue
            ids.append(event_id)
            phases[index]['physical_span_reserved'] = True
            inserted += 1
    if inserted:
        expanded['physical_phase_span_expansion_count'] = inserted
        expanded['physical_phase_span_authority'] = 'FIRST_TO_LAST_PHASE_PHYSICAL_CARRIER'
    return expanded, inserted


def solve_card_layout(events: list[dict], grammar: dict, phase_plan: dict) -> dict:
    """Solve geometry against the same first-to-last phase span used by scheduling."""
    active_ids = {
        str(event.get('event_id')) for event in events
        if not event.get('suppressed_by_card_density') and event.get('event_id') is not None
    }
    expanded, inserted = _expand_retained_phase_spans(phase_plan, active_ids)
    result = _implementation.solve_card_layout(events, grammar, expanded)
    result = dict(result)
    result['physical_phase_span_expansion_count'] = inserted
    result['physical_phase_span_authority'] = 'FIRST_TO_LAST_PHASE_PHYSICAL_CARRIER'
    return result
