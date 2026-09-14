"""Geometry-certified cross-card editorial choreography.

This finalizer runs after the reference density/geometry passes.  It derives motion
from the final source-backed footprint and adjacent semantic focus, never from package,
scene, narration, or asset identifiers.  P1 partitions and P2 causal timing remain
owned by their earlier authorities.
"""
from __future__ import annotations

import copy

from hexa_v31.preset_authority import opacity as preset_opacity, duration as preset_duration
from hexa_v31.composition_qa import card_motion_conflicts

AUTHORITY = 'GEOMETRY_CERTIFIED_CROSS_CARD_EDITORIAL_V1'
SAFE_X = (0.08, 0.92)
SAFE_Y = (0.10, 0.90)


def _react(event: dict) -> bool:
    values = {
        str(event.get(key) or '').strip().upper()
        for key in (
            'semantic_intent', 'relationship', 'interaction_action',
            'semantic_action', 'semantic_sentence_action',
        )
    }
    entry = event.get('preset_entry') or {}
    values.add(str(entry.get('semantic_action') or '').strip().upper())
    return bool(values.intersection({'REACT', 'REACTION', 'RESPOND'})) or bool(
        event.get('character_reaction_after_cause_required')
    )


def _root(event: dict) -> bool:
    return (
        not event.get('suppressed_by_card_density')
        and str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and not event.get('partition_group_id')
    )


def _translation_safe(event: dict) -> bool:
    return _root(event) and not _react(event) and bool(
        event.get('translation_safe_after_occlusion', event.get('animation_safe', True))
    )


def _center(event: dict) -> tuple[float, float]:
    value = event.get('card_rest_position_norm') or [0.5, 0.52]
    return float(value[0]), float(value[1])


def _phase_focus_id(card: dict, *, last: bool) -> str | None:
    phases = list((card.get('story_phase_plan') or {}).get('phases') or [])
    iterator = reversed(phases) if last else phases
    for phase in iterator:
        if phase.get('focus_event_id'):
            return str(phase['focus_event_id'])
    return None


def _pick_focus(events: list[dict], card: dict, *, last: bool) -> dict | None:
    if not events:
        return None
    focus_id = _phase_focus_id(card, last=last)
    if focus_id:
        hit = next((event for event in events if str(event.get('event_id')) == focus_id), None)
        if hit is not None:
            return hit
    primary = [event for event in events if str(event.get('attention_priority') or '').upper() == 'PRIMARY'] or events
    key_name = 'end_seconds' if last else 'start_seconds'
    def key(event: dict):
        return (
            float(event.get('perceptual_hit_seconds', event.get(key_name, 0.0))),
            str(event.get('event_id') or ''),
        )
    return max(primary, key=key) if last else min(primary, key=key)


def _readable_progress(name: str, minimum_opacity: float = 0.92) -> float:
    threshold = max(0.0, min(1.0, float(minimum_opacity)))
    for step in range(101):
        q = step / 100.0
        if float(preset_opacity(name, q)) >= threshold:
            return q
    return 1.0


def _hard_cut_readability(incoming: dict, boundary: float) -> bool:
    """Clip only the unreadable head of an existing appearance curve.

    Actor existence, preset identity and semantic start stay unchanged.  This is safe for
    P2 because no pixel is created before the P2-owned physical/semantic start.
    """
    entry = incoming.get('preset_entry') or {}
    name = str(entry.get('name') or '')
    if name != 'APPEAR_HIGH_SCALE':
        return False
    start = float(incoming.get('start_seconds', boundary))
    physical = float(incoming.get('physical_start_seconds', start))
    if start > boundary + 0.12 or physical > start + 1e-6:
        return False
    floor = _readable_progress(name)
    if not 0.0 < floor < 1.0:
        return False
    current = float(incoming.get('entry_curve_progress_floor') or 0.0)
    if current >= floor - 1e-6:
        return False
    incoming['entry_curve_progress_floor'] = round(floor, 6)
    incoming['entry_curve_progress_floor_authority'] = AUTHORITY
    incoming['cross_card_editorial_role'] = 'INCOMING_HARD_CUT_READABLE'
    incoming['cross_card_editorial_authority'] = AUTHORITY
    return True


def _fixed_reference_action(outgoing: dict, incoming: dict, card: dict, boundary: float, impl) -> dict | None:
    """Use a literal installed within-frame preset only when geometry matches it."""
    if not _translation_safe(outgoing):
        return None
    cx, _ = _center(outgoing)
    scale = float(outgoing.get('layout_scale_multiplier') or 1.0)
    settle = float(outgoing.get('settle_seconds', outgoing.get('start_seconds', 0.0)))
    exit_start = float((outgoing.get('preset_exit') or {}).get('start_seconds', boundary))

    name = None
    purpose = None
    direction = None
    # Literal MIDDLE -> side preset requires a genuinely middle start.
    if abs(cx - 0.5) <= 0.055:
        ix, _ = _center(incoming)
        direction = 'RIGHT' if ix < 0.46 else ('LEFT' if ix > 0.54 else ('RIGHT' if cx <= 0.5 else 'LEFT'))
        name = 'WITHIN_MIDDLE_TO_RIGHT' if direction == 'RIGHT' else 'WITHIN_MIDDLE_TO_LEFT'
        purpose = 'CLEAR_STAGE_FOR_NEXT_FOCUS'
    # Literal side -> MIDDLE requires an authored start near the installed endpoint.
    elif abs(cx - 0.183) <= 0.085:
        name = 'WITHIN_LEFT_TO_MIDDLE'; direction = 'MIDDLE'; purpose = 'RETURN_FOCUS_TO_MIDDLE'
    elif abs(cx - 0.833) <= 0.085:
        name = 'WITHIN_RIGHT_TO_MIDDLE'; direction = 'MIDDLE'; purpose = 'RETURN_FOCUS_TO_MIDDLE'
    if not name or not impl.within_preset_safe(outgoing, name, scale):
        return None

    duration = float(preset_duration(name))
    finish = min(boundary - 0.05, exit_start - 0.05)
    start = finish - duration
    if start < settle + 0.20 or start < float(card.get('start_seconds', 0.0)) + 0.30:
        return None
    for action in outgoing.get('preset_actions') or []:
        action_start = float(action.get('start_seconds', -999.0))
        action_end = action_start + float(action.get('duration_seconds') or 0.0)
        if action_start < finish and action_end > start:
            return None
    return {
        'name': name,
        'start_seconds': round(start, 6),
        'duration_seconds': round(duration, 6),
        'action_type': 'LAYOUT_CHOREOGRAPHY',
        'layout_purpose': purpose,
        'target_event_id': str(incoming.get('event_id') or ''),
        'authority': AUTHORITY,
        '_direction': direction,
    }


def _adaptive_stage_clear(outgoing: dict, incoming: dict, card: dict, boundary: float) -> dict | None:
    """Adapt the endpoint, not the reference motion language, for a wide single hero."""
    if not _translation_safe(outgoing):
        return None
    rect = list(outgoing.get('planned_rect_norm') or [])
    if len(rect) != 4:
        return None
    cx, cy = _center(outgoing)
    w, h = float(rect[2]), float(rect[3])
    if w <= 0.0 or h <= 0.0:
        return None

    # Adaptation exists for footprints that cannot safely reach the fixed reference side
    # endpoint. Small actors should use the literal preset path above.
    if w < 0.48 and h < 0.58:
        return None

    ix, _ = _center(incoming)
    if ix < 0.46:
        direction = 'RIGHT'
    elif ix > 0.54:
        direction = 'LEFT'
    else:
        direction = 'RIGHT' if cx <= 0.5 else 'LEFT'

    desired_delta = 0.07
    if direction == 'RIGHT':
        horizontal_cap = 2.0 * (SAFE_X[1] - cx - desired_delta) / max(w, 1e-9)
    else:
        horizontal_cap = 2.0 * (cx - SAFE_X[0] - desired_delta) / max(w, 1e-9)
    vertical_cap = min(
        2.0 * (cy - SAFE_Y[0]) / max(h, 1e-9),
        2.0 * (SAFE_Y[1] - cy) / max(h, 1e-9),
    )
    scale_cap = min(1.0, horizontal_cap, vertical_cap)
    # Do not manufacture movement by crushing the source. A 72% floor keeps the
    # adaptation editorially readable across photos, illustrations and large icons.
    if scale_cap < 0.72:
        return None
    clear_scale = min(0.92, scale_cap)
    half_w = w * clear_scale / 2.0
    target_x = SAFE_X[1] - half_w if direction == 'RIGHT' else SAFE_X[0] + half_w
    if abs(target_x - cx) < 0.055:
        return None

    reference_name = 'WITHIN_MIDDLE_TO_RIGHT' if direction == 'RIGHT' else 'WITHIN_MIDDLE_TO_LEFT'
    duration = float(preset_duration(reference_name))
    exit_start = float((outgoing.get('preset_exit') or {}).get('start_seconds', boundary))
    finish = min(boundary - 0.05, exit_start - 0.05)
    start = finish - duration
    settle = float(outgoing.get('settle_seconds', outgoing.get('start_seconds', 0.0)))
    if start < settle + 0.30 or start < float(card.get('start_seconds', 0.0)) + 0.35:
        return None

    return {
        'state_id': f"{outgoing.get('event_id')}::CROSS_CARD::ADAPTIVE_STAGE_CLEAR",
        'authority': AUTHORITY,
        'sequence_envelope': True,
        'envelope_track': 'CROSS_CARD_HANDOFF',
        'position_envelope': True,
        'semantic_beat': 'PRE_HANDOFF_STAGE_CLEAR',
        'start_seconds': round(start, 6),
        'transition_duration_seconds': round(duration, 6),
        'transition_preset_name': reference_name,
        'center_norm': [round(target_x, 6), round(cy, 6)],
        'scale_multiplier': round(clear_scale, 6),
        'visibility': 1.0,
        'card_id': outgoing.get('visual_card_id'),
        'owner_event_id': outgoing.get('event_id'),
        'participating_event_ids': [str(outgoing.get('event_id') or '')],
        'target_event_id': str(incoming.get('event_id') or ''),
        'state_reason': 'GEOMETRY_ADAPTED_REFERENCE_HANDOFF',
        '_direction': direction,
    }


def _card_events(events: list[dict], card: dict) -> list[dict]:
    card_id = str(card.get('card_id') or '')
    return [
        event for event in events
        if str(event.get('visual_card_id') or '') == card_id
        and not event.get('suppressed_by_card_density')
    ]


def finalize_cross_card_editorial(plan: dict, fps: float = 30.0) -> dict:
    events = plan.get('events') or []
    cards = sorted((plan.get('visual_cards') or {}).get('cards') or [], key=lambda card: float(card.get('start_seconds', 0.0)))
    from hexa_v31 import preset_story_planner as impl

    stats = {
        'authority': AUTHORITY,
        'changed': False,
        'boundaries_evaluated': 0,
        'hard_cut_readable_entries': 0,
        'literal_directional_handoffs': 0,
        'adaptive_stage_clears': 0,
        'source_limited_handoffs': 0,
        'collision_rollbacks': 0,
        'p1_p2_protected_boundaries': 0,
        'directions': [],
        'mutations': [],
        'pass': True,
    }

    for left, right in zip(cards, cards[1:]):
        left_events = _card_events(events, left)
        right_events = _card_events(events, right)
        outgoing = _pick_focus(left_events, left, last=True)
        incoming = _pick_focus(right_events, right, last=False)
        if outgoing is None or incoming is None or outgoing is incoming:
            continue
        stats['boundaries_evaluated'] += 1
        boundary = float(left.get('end_seconds', right.get('start_seconds', 0.0)))
        outgoing_end = float(outgoing.get('physical_end_seconds', outgoing.get('end_seconds', boundary)))
        overlap = max(0.0, outgoing_end - boundary)

        changed_here = False
        incoming_snapshot = copy.deepcopy(incoming)
        outgoing_snapshot = copy.deepcopy(outgoing)

        if overlap < 0.12 and _hard_cut_readability(incoming, boundary):
            stats['hard_cut_readable_entries'] += 1
            changed_here = True

        # Never stage an independent editorial sentence on top of P2 causal motion. The
        # preceding non-P2 card may still clear itself before the boundary; the P2 actor
        # is only observed as a geometry target and is never retimed/repositioned here.
        if _react(outgoing):
            stats['p1_p2_protected_boundaries'] += 1
        else:
            action = _fixed_reference_action(outgoing, incoming, left, boundary, impl)
            if action is not None:
                direction = action.pop('_direction')
                outgoing.setdefault('preset_actions', []).append(action)
                outgoing['cross_card_editorial_direction'] = direction
                outgoing['cross_card_editorial_authority'] = AUTHORITY
                stats['literal_directional_handoffs'] += 1
                stats['directions'].append(direction)
                changed_here = True
            elif len(left_events) == 1:
                state = _adaptive_stage_clear(outgoing, incoming, left, boundary)
                if state is not None:
                    direction = state.pop('_direction')
                    outgoing.setdefault('composition_states', []).append(state)
                    outgoing['cross_card_editorial_direction'] = direction
                    outgoing['cross_card_editorial_authority'] = AUTHORITY
                    stats['adaptive_stage_clears'] += 1
                    stats['directions'].append(direction)
                    changed_here = True
                else:
                    stats['source_limited_handoffs'] += 1

        if not changed_here:
            continue

        # Reuse production motion-conflict authority over both adjacent cards.  A failed
        # candidate is rolled back atomically; QA thresholds are never weakened.
        local = [*left_events, *right_events]
        start = float(left.get('start_seconds', 0.0))
        end = float(right.get('end_seconds', boundary))
        conflicts = card_motion_conflicts(local, start, end, fps)
        touched = {str(outgoing.get('event_id')), str(incoming.get('event_id'))}
        bad = [row for row in conflicts if str(row.get('event_a')) in touched or str(row.get('event_b')) in touched]
        if bad:
            outgoing.clear(); outgoing.update(outgoing_snapshot)
            incoming.clear(); incoming.update(incoming_snapshot)
            stats['collision_rollbacks'] += 1
            continue

        stats['changed'] = True
        stats['mutations'].append({
            'left_card_id': left.get('card_id'),
            'right_card_id': right.get('card_id'),
            'outgoing_event_id': outgoing.get('event_id'),
            'incoming_event_id': incoming.get('event_id'),
            'direction': outgoing.get('cross_card_editorial_direction'),
            'hard_cut_readable': bool(incoming.get('entry_curve_progress_floor_authority') == AUTHORITY),
        })

    return stats
