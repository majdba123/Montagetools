"""Encoded editorial delivery authority for V31.

This module is intentionally downstream of semantic planning but upstream of pixel
composition.  The planner already emits semantic phase states; this layer makes those
states materially visible without inventing package-specific rules.  It is deterministic,
protects P1/P2 carriers, and uses only semantic beat/archetype/focus metadata.
"""
from __future__ import annotations

import copy
import hashlib
import math
from typing import Iterable

_PROTECTED_RENDER_MODES = {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'}
_PROTECTED_REACT_TOKENS = ('REACT', 'REACTION', 'RESPOND')


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _ease(q: float) -> float:
    q = _clamp(q, 0.0, 1.0)
    # Minimum-jerk interpolation.  Keep this local so the delivery layer has no
    # dependency cycle with the motion solver.
    return q * q * q * (10.0 + q * (-15.0 + 6.0 * q))


def _lerp(a: float, b: float, q: float) -> float:
    return float(a) + (float(b) - float(a)) * float(q)


def _semantic_text(event: dict) -> str:
    return ' '.join(str(event.get(key) or '') for key in (
        'canonical_clause', 'canonical_narration', 'visual_concept',
        'semantic_intent', 'narrative_function', 'relationship',
    )).upper()


def _protected(event: dict) -> bool:
    if str(event.get('render_mode') or 'ROOT_ATOMIC') in _PROTECTED_RENDER_MODES:
        return True
    if event.get('partition_group_id'):
        return True
    text = _semantic_text(event)
    return any(token in text for token in _PROTECTED_REACT_TOKENS)


def _states(event: dict) -> list[dict]:
    rows = list(event.get('composition_states') or [])
    rows.extend(event.get('composition_participant_states') or [])
    rows = [row for row in rows if row.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY']
    rows.sort(key=lambda row: (float(row.get('start_seconds', 0.0)), str(row.get('state_id') or '')))
    return rows


def _active_state(event: dict, t: float) -> tuple[dict | None, dict | None, float]:
    rows = _states(event)
    if not rows:
        return None, None, 1.0
    index = -1
    for i, row in enumerate(rows):
        if float(row.get('start_seconds', 0.0)) <= t + 1e-9:
            index = i
        else:
            break
    if index < 0:
        return None, None, 1.0
    current = rows[index]
    previous = rows[index - 1] if index > 0 else None
    duration = max(0.0, float(current.get('transition_duration_seconds') or 0.0))
    if duration <= 1e-6:
        return current, previous, 1.0
    q = _ease((t - float(current.get('start_seconds', 0.0))) / duration)
    return current, previous, q


def _stable_token(event: dict) -> float:
    raw = f"{event.get('visual_card_id')}|{event.get('event_id')}|{event.get('scene_id')}".encode('utf-8')
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:2], 'big') / 65535.0


def _archetype_target(state: dict, event: dict, base: tuple[float, float]) -> tuple[float, float, float]:
    """Return deterministic semantic center + scale multiplier.

    Targets are deliberately bounded to the inner safe area. They are not absolute
    scene templates: event identity supplies a stable side preference and the semantic
    beat decides whether the actor establishes, supports, pays off, or hands off.
    """
    x, y = float(base[0]), float(base[1])
    arch = str(state.get('layout_archetype') or '').upper()
    beat = str(state.get('semantic_beat') or '').upper()
    event_id = str(event.get('event_id') or '')
    focus = event_id == str(state.get('focus_event_id') or '')
    participants = [str(v) for v in (state.get('participating_event_ids') or [])]
    count = max(1, len(participants))
    token = _stable_token(event)
    side = -1.0 if token < 0.5 else 1.0

    # Establishment is intentionally sparse and central. This removes the permanent
    # presenter/object two-column default and gives the first idea real authority.
    if count == 1 or beat in {'ESTABLISH', 'PROCESS_ESTABLISH', 'CONTEXT_ESTABLISH', 'BEFORE_ESTABLISH'}:
        if focus:
            return (0.50, 0.51, 1.20 if count == 1 else 1.10)
        return (_clamp(x, 0.24, 0.76), _clamp(y, 0.28, 0.76), 0.78)

    if 'COMPAR' in arch or beat.startswith('COMPARE_'):
        # Comparison reads as an argument: established term on one side, current focus
        # on the other, conclusion tightens toward the center instead of staying poster-like.
        idx = participants.index(event_id) if event_id in participants else 0
        target_x = 0.29 if idx % 2 == 0 else 0.71
        if 'CONCLUDE' in beat and focus:
            target_x = 0.58 if target_x > 0.5 else 0.42
        return (target_x, 0.51, 1.08 if focus else 0.84)

    if 'FLOW' in arch or beat.startswith('PROCESS_'):
        idx = participants.index(event_id) if event_id in participants else 0
        if count <= 2:
            target_x = 0.36 if idx == 0 else 0.66
            target_y = 0.46 if idx == 0 else 0.57
        else:
            target_x = 0.24 + (0.52 * idx / max(1, count - 1))
            target_y = 0.43 + (0.10 if idx % 2 else 0.0)
        if focus:
            target_y -= 0.035
        return (target_x, target_y, 1.08 if focus else 0.80)

    if 'RESULT' in arch or 'PAYOFF' in beat or 'RESULT' in beat:
        if focus:
            return (0.50, 0.49, 1.24)
        return (0.25 if side < 0 else 0.75, 0.64, 0.70)

    if 'BEFORE_AFTER' in arch or beat in {'TRANSITION', 'AFTER_REVEAL'}:
        idx = participants.index(event_id) if event_id in participants else 0
        if beat == 'AFTER_REVEAL' and focus:
            return (0.55, 0.50, 1.18)
        return (0.32 if idx == 0 else 0.68, 0.52, 0.86 if not focus else 1.05)

    if 'QUESTION' in arch:
        if focus:
            return (0.50, 0.48, 1.16)
        return (0.28 if side < 0 else 0.72, 0.62, 0.76)

    if 'CHARACTER_EXPLAINS' in arch:
        role = str(state.get('role') or '').upper()
        narrator = role in {'NARRATOR', 'PRESENTER', 'CHARACTER'}
        if narrator and not focus:
            return (0.79 if side > 0 else 0.21, 0.66, 0.70)
        if focus:
            return (0.47 if narrator else 0.52, 0.48, 1.16)
        return (0.25 if side < 0 else 0.75, 0.54, 0.80)

    if 'REBUILD' in beat or 'HANDOFF' in beat:
        if focus:
            return (0.50, 0.50, 1.16)
        return (0.23 if side < 0 else 0.77, 0.64, 0.72)

    # Generic support reveal: keep relation readable but break the repeated symmetric
    # side-by-side composition through deterministic vertical asymmetry.
    if focus:
        return (0.56 if side > 0 else 0.44, 0.46, 1.10)
    return (0.27 if side < 0 else 0.73, 0.61 if token > 0.5 else 0.39, 0.80)


def _target_for_state(state: dict | None, event: dict, base: tuple[float, float]) -> tuple[float, float, float]:
    if state is None:
        return float(base[0]), float(base[1]), 1.0
    return _archetype_target(state, event, base)


def apply_editorial_runtime_state(
    event: dict,
    t: float,
    state: tuple[tuple[float, float], float, float] | None,
) -> tuple[tuple[float, float], float, float] | None:
    """Materialize semantic phase topology into final event state.

    Existing entry/exit/preset motion remains authoritative; this function only nudges
    the settled semantic destination during planner-authored phase windows. Protected
    P1/P2 carriers are returned byte-for-byte unchanged.
    """
    if state is None or _protected(event):
        return state
    current, previous, q = _active_state(event, float(t))
    if current is None:
        return state

    (px, py), scale, opacity = state
    width = max(1.0, float(event.get('sequence_width') or 1920.0))
    height = max(1.0, float(event.get('sequence_height') or 1080.0))
    base = (float(px) / width, float(py) / height)
    prev_target = _target_for_state(previous, event, base)
    cur_target = _target_for_state(current, event, base)
    tx = _lerp(prev_target[0], cur_target[0], q)
    ty = _lerp(prev_target[1], cur_target[1], q)
    semantic_scale = _lerp(prev_target[2], cur_target[2], q)

    # Preserve authored preset travel: semantic authority supplies the destination,
    # while the existing preset's instantaneous displacement remains visible.
    authored_base = event.get('object_rest_position_px') or event.get('end_position_px') or event.get('rest_position_px')
    if isinstance(authored_base, (list, tuple)) and len(authored_base) >= 2:
        dx = float(px) - float(authored_base[0])
        dy = float(py) - float(authored_base[1])
    else:
        dx = dy = 0.0
    out_x = _clamp(tx * width + dx, width * 0.08, width * 0.92)
    out_y = _clamp(ty * height + dy, height * 0.10, height * 0.90)

    # Pale crossfades were a repeated encoded failure. Inside an established semantic
    # phase, source actors stay visually solid; authored opening/closing envelopes retain
    # control near physical lifetime boundaries.
    physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
    physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
    if t >= physical_start + 0.16 and t <= physical_end - 0.16:
        opacity = max(float(opacity), 0.94)

    return (out_x, out_y), float(scale) * semantic_scale, float(opacity)


def promote_text_plan(text_plan: dict | None, motion_plan: dict | None) -> dict | None:
    """Make role-specific typography participate in editorial beats.

    No copy is invented or rewritten here.  The existing phrase-quality/shaping authority
    remains upstream; this function only makes already-approved display copy move/read as
    designed graphics rather than passive subtitles.
    """
    if not text_plan:
        return text_plan
    promoted = copy.deepcopy(text_plan)
    events = list(promoted.get('events') or [])
    role_profiles = {
        'HERO': (0.90, 1.08, 1.00, 0.055, 0.0, 0.52),
        'RESULT': (0.91, 1.07, 1.00, -0.050, 0.0, 0.50),
        'VALUE': (0.90, 1.09, 1.00, 0.0, -0.045, 0.48),
        'WARNING': (0.94, 1.04, 1.00, 0.0, 0.050, 0.44),
        'STATUS': (0.96, 1.03, 1.00, 0.035, 0.0, 0.42),
        'KEYWORD': (0.94, 1.05, 1.00, -0.035, 0.0, 0.42),
        'COMPARISON_LABEL': (0.96, 1.03, 1.00, 0.030, 0.0, 0.40),
        'MICRO_LABEL': (0.98, 1.015, 1.00, 0.020, 0.0, 0.36),
    }
    for event in events:
        role = str(event.get('semantic_role') or event.get('role') or event.get('treatment_role') or 'KEYWORD').upper()
        profile = role_profiles.get(role, role_profiles['KEYWORD'])
        event['pop_scale_from'], event['pop_scale_peak'], event['pop_scale_end'] = profile[:3]
        event['slide_dx_norm'] = profile[3]
        event['slide_dy_norm'] = profile[4]
        event['slide_duration_seconds'] = profile[5]
        duration = max(0.0, float(event.get('end_seconds', 0.0)) - float(event.get('start_seconds', 0.0)))
        if duration >= 1.4 and role in {'HERO', 'RESULT', 'VALUE', 'WARNING'}:
            event['read_sweep_duration_seconds'] = min(0.9, max(0.55, duration * 0.24))
            event['read_sweep_dx_norm'] = -profile[3] * 0.35
            event['read_sweep_dy_norm'] = -profile[4] * 0.35
        event['editorial_typography_runtime_authority'] = 'SEMANTIC_ROLE_MOTION_GRAPHICS_V1'
    promoted['events'] = events
    promoted['editorial_typography_runtime_authority'] = 'SEMANTIC_ROLE_MOTION_GRAPHICS_V1'
    return promoted
