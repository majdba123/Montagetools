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
    text = ' '.join(str(event.get(key) or '') for key in (
        'canonical_clause', 'canonical_narration', 'visual_concept',
        'semantic_intent', 'narrative_function', 'relationship',
    )).upper()
    return any(signal in text for signal in ('REACT', 'REACTION', 'RESPOND'))


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
    # REACT is reverse-causal in the protected interaction engine: the paired
    # object is the stimulus and the semantic subject is the reaction. P2 owns
    # that cause-before-reaction timing and may retime the subject's existing
    # in-place reveal to the semantic hit. Pre-layout focal-first phasing would
    # delay the causal source and make that protected schedule impossible.
    # Leave these scenes on the established topology so interaction authority
    # remains earlier/harder than P4 editorial staging.
    if any(_protected_react_semantics(e) for e in active):
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
    presenter = next((e for e in ordered if role(e) == 'NARRATOR'), None)
    result = next((e for e in ordered if role(e) in {'RESULT','TARGET'}), None)
    non_presenter_primary = next((e for e in ordered if e is not presenter and str(e.get('attention_priority') or '').upper() == 'PRIMARY'), None)
    if archetype in {'CHARACTER_EXPLAINS_OBJECT','RESULT_PAYOFF','QUESTION_ANSWER'}:
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
    if archetype in {'RESULT_PAYOFF','SOURCE_BLOCKER_RESULT'} and result in remaining:
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
            'choreography_authority': _PROGRESSIVE_AUTHORITY,
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
    scene_root_counts: dict[str, int] = {}
    for event in events:
        if str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC' and not event.get('partition_group_id'):
            sid = str(event.get('scene_id') or '')
            scene_root_counts[sid] = scene_root_counts.get(sid, 0) + 1
    rows: list[dict] = []
    reveal_order: list[str] = []
    split_count = 0
    source_phases = copy.deepcopy(fallback.get('phases') or [])
    for phase_index, phase in enumerate(source_phases):
        phase_events = [by_id[eid] for eid in phase.get('event_ids') or [] if eid in by_id]
        groups: dict[str, list[dict]] = {}
        for event in phase_events:
            if str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
                continue
            if event.get('partition_group_id'):
                continue
            if _protected_react_semantics(event):
                continue
            groups.setdefault(str(event.get('scene_id') or ''), []).append(event)
        cohorts = [
            group for sid, group in groups.items()
            if 2 <= len(group) <= 5 and scene_root_counts.get(sid, 0) <= 5
        ]
        duration = float(phase.get('end_seconds', 0.0)) - float(phase.get('start_seconds', 0.0))
        cohort = cohorts[0] if len(cohorts) == 1 else None
        if cohort is None:
            row = dict(phase)
            row.setdefault('entering_event_ids', list(row.get('event_ids') or []))
            row.setdefault('retained_event_ids', [])
            rows.append(row)
            for eid in row.get('event_ids') or []:
                if eid not in reveal_order:
                    reveal_order.append(eid)
            continue

        ordered = list(_implementation._phase_order(cohort, grammar))
        anchor = next((e for e in ordered if str(e.get('attention_priority') or '').upper() == 'PRIMARY'), ordered[0])
        ordered = [anchor] + [e for e in ordered if e is not anchor]
        delayed_ids = [str(e.get('event_id')) for e in ordered[1:]]
        anchor_id = str(anchor.get('event_id'))
        start = float(phase['start_seconds'])
        end = float(phase['end_seconds'])
        next_phase = source_phases[phase_index + 1] if phase_index + 1 < len(source_phases) else None
        handoff_extension = bool(
            next_phase and anchor_id in (next_phase.get('event_ids') or [])
            and delayed_ids and delayed_ids[-1] not in (next_phase.get('event_ids') or [])
        )
        if duration + 1e-9 < (_MIN_BEAT_SECONDS + (0.10 if handoff_extension else _MIN_FINAL_REVEAL_SECONDS)):
            row = dict(phase)
            row.setdefault('entering_event_ids', list(row.get('event_ids') or []))
            row.setdefault('retained_event_ids', [])
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
        latest_cut = end - (0.10 if handoff_extension else _MIN_FINAL_REVEAL_SECONDS)
        cut = max(start + _MIN_BEAT_SECONDS, min(latest_cut, target))
        original_ids = list(phase.get('event_ids') or [])
        first_ids = [eid for eid in original_ids if eid not in delayed_ids]
        if anchor_id not in first_ids:
            first_ids.append(anchor_id)
        common = {
            'semantic_boundary_authority': phase.get('semantic_boundary_authority', 'ADJACENT_ANCHOR_MIDPOINT'),
            'choreography_authority': _PROGRESSIVE_AUTHORITY,
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
        })
        for eid in first_ids:
            if eid not in reveal_order:
                reveal_order.append(eid)
        rows.append({
            **common,
            'phase_id': f"{phase.get('phase_id')}_PB2",
            'start_seconds': round(cut, 6),
            'end_seconds': round(end, 6),
            'event_ids': original_ids,
            'entering_event_ids': delayed_ids,
            'retained_event_ids': [eid for eid in original_ids if eid not in delayed_ids],
            'semantic_beat': 'COMPOSITION_REBUILD',
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
        'choreography_authority': _PROGRESSIVE_AUTHORITY,
        'reveal_order_event_ids': reveal_order,
        'retention_policy': 'LEGACY_SEMANTIC_HANDOFF_PLUS_PROGRESSIVE_SCENE_COHORT',
        'minimum_final_reveal_seconds': _MIN_FINAL_REVEAL_SECONDS,
    })
    if not _implementation.solve_card_layout(events, grammar, candidate).get('pass'):
        return None
    return candidate


def build_story_phases(card: dict, events: list[dict], grammar: dict) -> dict:
    """Build progressive same-scene beats before final geometry is solved."""
    progressive = _progressive_plan(card, events, grammar)
    if progressive is not None:
        return progressive
    # Preserve the production planner's anchor-owned multi-scene topology.
    # The old generic card builder can merge adjacent source scenes into one
    # permanent state; anchor repartition keeps their semantic clocks intact.
    fallback = _BASE_REPARTITION_STORY_PHASES(card, events, [])
    refined = _progressivize_repartitioned_plan(card, events, {'archetype':'GENERIC','roles':{},'explicit_edges':[]}, fallback)
    if refined is not None:
        return refined
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'ANCHOR_OWNED_PHASE_TOPOLOGY')
    return fallback


def solve_phase_layouts(events:list[dict],grammar:dict,phase_plan:dict)->dict:
    """Solve a real geometry/hierarchy destination for every editorial phase."""
    by_id={str(event.get('event_id')):event for event in events if not event.get('suppressed_by_card_density')}
    stable=solve_card_layout(list(by_id.values()),grammar,phase_plan)
    if not stable.get('pass'):
        return stable
    if phase_plan.get('choreography_authority') != _EDITORIAL_TOPOLOGY_AUTHORITY:
        return dict(stable,phase_placements={},editorial_geometry_authority='PROTECTED_OR_LEGACY_TOPOLOGY')
    phase_placements={}
    for phase in phase_plan.get('phases') or []:
        ids=[str(event_id) for event_id in phase.get('event_ids') or [] if str(event_id) in by_id]
        if not ids:continue
        focus_id=str(phase.get('focus_event_id') or ids[-1])
        chosen={event_id:copy.deepcopy(stable['placements'][event_id]) for event_id in ids}
        focus_base=float(chosen[focus_id]['scale'])
        focus_fp=_implementation._fp(by_id[focus_id])
        # Expand focus into phase-local negative space. Centers remain the
        # card-wide collision-certified authority, making every interpolated
        # transition safe; scale is the phase-owned geometric variable.
        # A co-occurring actor may still be traversing its preset envelope even
        # when both phase endpoints are disjoint. Reserve expansion for solo
        # focus states; multi-actor states retain the certified envelope.
        focus_candidates=[focus_base*factor for factor in (1.42,1.34,1.26,1.18,1.12)] if len(ids)==1 else []
        focus_scale=focus_base
        for candidate in focus_candidates:
            rect=_implementation._rect(tuple(chosen[focus_id]['center_norm']),focus_fp,candidate*_implementation.MOTION_ENVELOPE_SCALE)
            if not _implementation._in_safe(rect):continue
            safe=True
            for event_id in ids:
                if event_id==focus_id:continue
                other=stable['placements'][event_id];other_fp=_implementation._fp(by_id[event_id])
                other_rect=_implementation._rect(tuple(other['center_norm']),other_fp,float(other['scale'])*_implementation.MOTION_ENVELOPE_SCALE)
                gap=_implementation.PRIMARY_GAP if (focus_fp.primary or other_fp.primary) else _implementation.SUPPORT_GAP
                if _implementation._inter(_implementation._inflate(rect,gap),_implementation._inflate(other_rect,gap))>1e-8:
                    safe=False;break
            if safe:
                focus_scale=candidate
                chosen[focus_id]['scale']=round(candidate,6)
                chosen[focus_id]['rect_norm']=[round(x,6) for x in rect]
                break
        # With co-occurring actors, keep the previously certified conservative
        # hierarchy. Entry/exit envelopes occupy more space than static phase
        # endpoints, so enlarging either endpoint is not sufficient evidence of
        # a safe interpolated path.
        for event_id,placement in chosen.items():
            if event_id==focus_id:continue
            fp=_implementation._fp(by_id[event_id]);scale=float(stable['placements'][event_id]['scale'])*.82
            rect=_implementation._rect(tuple(placement['center_norm']),fp,scale*_implementation.MOTION_ENVELOPE_SCALE)
            placement['scale']=round(scale,6);placement['rect_norm']=[round(x,6) for x in rect]
        for event_id,placement in chosen.items():
            base_scale=max(1e-9,float(stable['placements'][event_id]['scale']))
            placement['phase_scale_factor']=round(float(placement['scale'])/base_scale,6)
            placement['phase_focus']=event_id==focus_id
        context=[placement for event_id,placement in chosen.items() if event_id!=focus_id]
        focus_factor=float(chosen[focus_id]['phase_scale_factor'])
        if context and focus_factor-max(float(row['phase_scale_factor']) for row in context)<.099:
            return {'pass':False,'reason':'NO_MATERIAL_PHASE_HIERARCHY','phase_id':phase.get('phase_id')}
        phase_placements[str(phase.get('phase_id'))]=chosen
    return {'pass':True,'placements':stable['placements'],'phase_placements':phase_placements,
            'archetype':grammar.get('archetype'),'phase_aware':True,
            'search_mode':'SEMANTIC_ARCHETYPE_PER_PHASE_GEOMETRY',
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
    progressive = _progressive_plan(card, events, validate_layout=False)
    if progressive is not None:
        progressive['repartition_trigger_conflict_count'] = len(conflicts or [])
        progressive['repartition_policy'] = 'PRESERVE_PROGRESSIVE_TEMPORAL_TOPOLOGY'
        return progressive
    fallback = _BASE_REPARTITION_STORY_PHASES(card, events, conflicts)
    refined = _progressivize_repartitioned_plan(card, events, {'archetype': 'GENERIC', 'roles': {}, 'explicit_edges': []}, fallback)
    if refined is not None:
        refined['repartition_trigger_conflict_count'] = len(conflicts or [])
        refined['repartition_policy'] = 'PRESERVE_PROGRESSIVE_TEMPORAL_TOPOLOGY'
        return refined
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'LEGACY_REPARTITION_FALLBACK')
    return fallback


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
