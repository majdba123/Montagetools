"""Backward-compatible composition solver facade.

Production planning imports this module, while the implementation lives under
``hexa_v31.layout``. The facade is also the compatibility boundary for V31's
pre-layout editorial phase policy: geometry remains owned by the existing
solver, but eligible same-scene actors are presented to it as progressive
co-occurrence states instead of one permanent poster state.
"""
from __future__ import annotations

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

    anchor = next(
        (e for e in ordered if str(e.get('attention_priority') or '').upper() == 'PRIMARY'),
        ordered[0],
    )
    ordered = [anchor] + [e for e in ordered if e is not anchor]
    phase_count = _progressive_phase_count(duration, len(ordered))
    if phase_count < 2:
        return None

    buckets: list[list[dict]] = [[] for _ in range(phase_count)]
    buckets[0].append(anchor)
    remaining = ordered[1:]
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

        # Retain the focal carrier plus the two most recent actors. Earlier
        # support can retire when a later result needs space; this is temporal
        # composition, not deletion of source evidence.
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
        rows.append({
            'phase_id': f"{card.get('card_id')}_PB{index + 1}",
            'start_seconds': round(cuts[index], 6),
            'end_seconds': round(cuts[index + 1], 6),
            'event_ids': [str(e.get('event_id')) for e in phase_events],
            'entering_event_ids': [str(e.get('event_id')) for e in newcomers],
            'retained_event_ids': [
                str(e.get('event_id')) for e in phase_events if e not in newcomers
            ],
            'semantic_beat': 'ESTABLISH' if index == 0 else (
                'COMPOSITION_REBUILD' if index == phase_count - 1 else 'SUPPORT_REVEAL'
            ),
            'choreography_authority': _PROGRESSIVE_AUTHORITY,
        })

    candidate = {
        'schema': 'HEXA_VISUAL_STORY_PHASES_V31_PROGRESSIVE',
        'phases': rows,
        'phase_count': len(rows),
        'progressive_reveal_compiled': True,
        'choreography_authority': _PROGRESSIVE_AUTHORITY,
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


def build_story_phases(card: dict, events: list[dict], grammar: dict) -> dict:
    """Build progressive same-scene beats before final geometry is solved."""
    progressive = _progressive_plan(card, events, grammar)
    if progressive is not None:
        return progressive
    fallback = _BASE_BUILD_STORY_PHASES(card, events, grammar)
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'LEGACY_PHASE_FALLBACK')
    return fallback


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
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'LEGACY_REPARTITION_FALLBACK')
    return fallback
