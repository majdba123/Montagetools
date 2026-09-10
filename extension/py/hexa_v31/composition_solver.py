"""Backward-compatible composition solver facade.

Production planning imports this module, while the implementation lives under
``hexa_v31.layout``.  The facade is also the correct compatibility boundary for
V31's pre-layout editorial phase policy: geometry remains owned by the existing
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
_PROGRESSIVE_AUTHORITY = 'PRE_LAYOUT_PROGRESSIVE_SCENE_BEATS_V1'
_MIN_BEAT_SECONDS = 0.82


def _progressive_same_scene_candidates(events: list[dict]) -> list[dict]:
    active = [e for e in events if not e.get('suppressed_by_card_density')]
    if not 2 <= len(active) <= 5:
        return []
    # Certified partitions/residuals are source-survival structures.  Their
    # independent motion policy is already owned by P1/P2 and must not be
    # repartitioned here.  This path is deliberately for independent roots.
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
    # A supplied appearance preset consumes 0.8s.  Keep at least one readable
    # beat boundary around it and reduce complexity on short cards rather than
    # compressing every reveal into a burst.
    capacity = max(2, min(4, int((duration + 1e-9) // _MIN_BEAT_SECONDS)))
    return min(event_count, capacity)


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
        # APPEAR_HIGH_SCALE reaches its perceptual result at ~70% of 0.8s.
        # When a real voice trigger exists, open the phase just before it so the
        # visual impact lands on speech. Fallback-only scenes stay evenly paced.
        target = min(voice_hits) - 0.56 if voice_hits else uniform
        remaining = count - index
        lo = cuts[-1] + _MIN_BEAT_SECONDS
        hi = ce - remaining * _MIN_BEAT_SECONDS
        if hi < lo:
            target = uniform
            lo = cuts[-1] + max(0.60, duration / count * 0.72)
            hi = ce - remaining * max(0.60, duration / count * 0.72)
        cuts.append(max(lo, min(hi, target)))
    cuts.append(ce)
    return cuts


def _progressive_plan(card: dict, events: list[dict], grammar: dict) -> dict | None:
    active = _progressive_same_scene_candidates(events)
    if not active:
        return None
    cs = float(card['start_seconds'])
    ce = float(card['end_seconds'])
    duration = ce - cs
    ordered = list(_implementation._phase_order(active, grammar))
    if len(ordered) < 2:
        return None

    # Establish a focal source first.  Remaining independent roots are ordered
    # by the existing semantic phase authority and introduced over later beats.
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
        # Spread introductions across the available spoken clock.  When there
        # are more actors than beats, pair only the unavoidable later reveals;
        # never collapse them back into the opening frame.
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

        # Reference-like retained context with bounded concurrency: keep the
        # focal carrier plus the two most recent supporting actors.  This lets
        # earlier support retire when a later result needs space instead of
        # forcing all 4-5 roots into one undersized permanent layout.
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
        'atomic_asset_indivisibility': True,
    }
    # This is a pre-layout policy, so accept it only if the existing hard
    # geometry solver can solve every declared co-occurrence state.  Failure
    # falls back to the original phase authority rather than weakening QA.
    if not _implementation.solve_card_layout(active, grammar, candidate).get('pass'):
        return None
    return candidate


def build_story_phases(card: dict, events: list[dict], grammar: dict) -> dict:
    """Build progressive same-scene beats before final geometry is solved.

    The legacy builder remains the fallback for partitions, cross-scene cards,
    dense/irreducible groups, and any candidate the hard layout solver rejects.
    """
    progressive = _progressive_plan(card, events, grammar)
    if progressive is not None:
        return progressive
    fallback = _BASE_BUILD_STORY_PHASES(card, events, grammar)
    fallback.setdefault('progressive_reveal_compiled', False)
    fallback.setdefault('choreography_authority', 'LEGACY_PHASE_FALLBACK')
    return fallback
