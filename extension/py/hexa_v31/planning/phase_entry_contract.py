"""Keep directional-entry motion subordinate to certified semantic phase geometry.

The phase layout compiler owns absolute actor destinations. Beat choreography may add
an entry envelope after those destinations exist, but that envelope must land on the
active phase center/scale rather than restoring stale card-wide rest geometry. This
contract patches the bounded entry helpers used by shipping BeatChoreographyCompiler
without weakening collision, viewport, or final certification thresholds.
"""
from __future__ import annotations


def _phase_geometry_states(event: dict) -> list[dict]:
    rows = []
    for key in ('composition_states', 'composition_participant_states'):
        for state in event.get(key) or []:
            if state.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY':
                rows.append(state)
    rows.sort(key=lambda state: (
        float(state.get('start_seconds', 0.0)),
        str(state.get('state_id') or ''),
    ))
    return rows


def _entry_destination(event: dict, at: float):
    """Return active phase destination and the next immutable phase boundary."""
    states = _phase_geometry_states(event)
    active = [
        state for state in states
        if float(state.get('start_seconds', 0.0)) <= float(at) + 1e-6
    ]
    if active:
        state = active[-1]
        target = list(
            state.get('center_norm')
            or event.get('card_rest_position_norm')
            or [0.5, 0.5]
        )
        state_scale = float(state.get('scale_multiplier') or 1.0)
        state_id = str(state.get('state_id') or '') or None
    else:
        target = list(event.get('card_rest_position_norm') or [0.5, 0.5])
        state_scale = 1.0
        state_id = None

    future = [
        float(state.get('start_seconds', 0.0))
        for state in states
        if float(state.get('start_seconds', 0.0)) > float(at) + 1e-6
    ]
    return target, state_scale, state_id, (min(future) if future else None)


def install(beat_module) -> None:
    """Install idempotent phase-aware directional-entry helpers."""
    if getattr(beat_module, '_phase_entry_contract_installed', False):
        return

    def candidate_origins(event: dict):
        entry = event.get('preset_entry') or {}
        at = float(entry.get('start_seconds', event.get('start_seconds', 0.0)))
        target, state_scale, _, _ = _entry_destination(event, at)
        fp = beat_module._fp(event)
        scale = float(event.get('layout_scale_multiplier') or 1.0) * float(state_scale)
        width = fp.w * scale
        height = fp.h * scale
        candidates = {
            'LEFT': [beat_module.SAFE_X[0] - width / 2.0 - 0.025, target[1]],
            'RIGHT': [beat_module.SAFE_X[1] + width / 2.0 + 0.025, target[1]],
            'TOP': [target[0], beat_module.SAFE_Y[0] - height / 2.0 - 0.025],
            'BOTTOM': [target[0], beat_module.SAFE_Y[1] + height / 2.0 + 0.025],
        }
        edge_distance = {
            'LEFT': max(0.0, target[0] - beat_module.SAFE_X[0]),
            'RIGHT': max(0.0, beat_module.SAFE_X[1] - target[0]),
            'TOP': max(0.0, target[1] - beat_module.SAFE_Y[0]),
            'BOTTOM': max(0.0, beat_module.SAFE_Y[1] - target[1]),
        }
        bias = {name: 0.0 for name in candidates}
        if target[0] < 0.43:
            bias['LEFT'] -= 0.10
        elif target[0] > 0.57:
            bias['RIGHT'] -= 0.10
        if target[1] < 0.40:
            bias['TOP'] -= 0.07
        elif target[1] > 0.64:
            bias['BOTTOM'] -= 0.07
        rows = [(name, candidates[name], edge_distance[name] + bias[name]) for name in candidates]
        rows.sort(key=lambda row: (row[2], row[0]))
        return rows

    def entry_states(event: dict, origin: list[float], direction: str, fps: float):
        entry = event.get('preset_entry') or {}
        start = float(entry.get('start_seconds', event.get('start_seconds', 0.0)))
        preset_duration = max(0.0, float(entry.get('duration_seconds') or 0.0))
        physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', start)))
        target, phase_scale, phase_state_id, next_phase_start = _entry_destination(event, start)
        action_starts = [
            float(action.get('start_seconds'))
            for action in event.get('preset_actions') or []
            if action.get('start_seconds') is not None
        ]
        hard_boundaries = [physical_end, *action_starts]
        if next_phase_start is not None:
            hard_boundaries.append(float(next_phase_start))
        hard_end = min(hard_boundaries)
        frame = 1.0 / max(1.0, fps)
        transition = min(0.72, max(0.42, preset_duration * 0.82 if preset_duration else 0.58))
        settle_start = start + frame
        transition = min(transition, hard_end - settle_start - 0.08)
        if transition < 0.32:
            return None

        base = f"{event.get('event_id')}::EDITORIAL_ENTRY"
        common = {
            'authority': beat_module._AUTHORITY,
            'envelope_track': beat_module._ENTRY_TRACK,
            'position_envelope': True,
            'card_id': event.get('visual_card_id'),
            'editorial_motion_family': 'DIRECTIONAL_ENTRY',
            'entry_direction': direction,
        }
        if phase_state_id:
            common['phase_destination_state_id'] = phase_state_id
            common['phase_geometry_rebase_authority'] = 'DIRECTIONAL_ENTRY_SUBORDINATE_TO_PHASE_GEOMETRY'

        origin_state = dict(
            common,
            state_id=base + '::ORIGIN',
            semantic_beat='ENTRY_ORIGIN',
            start_seconds=round(start, 6),
            transition_duration_seconds=0.0,
            center_norm=[round(float(origin[0]), 6), round(float(origin[1]), 6)],
            scale_multiplier=round(0.96 * phase_scale, 6),
            visibility=0.0,
        )
        settle_state = dict(
            common,
            state_id=base + '::SETTLE',
            previous_state_id=origin_state['state_id'],
            semantic_beat='DIRECTIONAL_REVEAL',
            start_seconds=round(settle_start, 6),
            transition_duration_seconds=round(transition, 6),
            center_norm=[round(float(target[0]), 6), round(float(target[1]), 6)],
            scale_multiplier=round(phase_scale, 6),
            visibility=1.0,
        )
        return [origin_state, settle_state]

    beat_module._candidate_origins = candidate_origins
    beat_module._entry_states = entry_states
    beat_module._phase_entry_contract_installed = True
