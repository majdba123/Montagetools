"""Shared classification of authored center travel, independent of scale/opacity."""
from __future__ import annotations
import math
from hexa_v31.preset_authority import preset as _preset_def

def _preset_moves_center(row: dict | None) -> bool:
    if not row:
        return False
    name = str(row.get('name') or '')
    if not name:
        return False
    try:
        definition = _preset_def(name)
    except KeyError:
        return True
    family = str(definition.get('family') or '').upper()
    if family in {'ENTRY_EXIT', 'WITHIN_FRAME'}:
        return True
    delta = definition.get('position_delta_norm') or [0.0, 0.0]
    try:
        return abs(float(delta[0])) > 1e-6 or abs(float(delta[1])) > 1e-6
    except (TypeError, ValueError, IndexError):
        return True


def _state_moves_center(event: dict) -> bool:
    base = event.get('card_rest_position_norm') or [0.5, 0.5]
    for key in ('composition_states', 'composition_participant_states'):
        for state in event.get(key) or []:
            center = state.get('center_norm') or base
            try:
                if math.dist([float(center[0]), float(center[1])],
                             [float(base[0]), float(base[1])]) > 1e-6:
                    return True
            except (TypeError, ValueError, IndexError):
                return True
    return False


def _vector_motion_authority(event: dict) -> bool:
    if abs(float(event.get('drift_dx_norm') or 0.0)) > 1e-6 or abs(float(event.get('drift_dy_norm') or 0.0)) > 1e-6:
        return True
    for key in ('focus_beats', 'story_beats', 'story_actions'):
        for row in event.get(key) or []:
            if (
                abs(float(row.get('dx_norm') or 0.0)) > 1e-6
                or abs(float(row.get('dy_norm') or 0.0)) > 1e-6
                or abs(float(row.get('arc_norm') or 0.0)) > 1e-6
            ):
                return True
    return False


def has_actual_center_travel(event: dict) -> bool:
    """Protect actual center travel while allowing center-preserving hierarchy."""
    if event.get('position_animated'):
        return True
    if _preset_moves_center(event.get('preset_entry')) or _preset_moves_center(event.get('preset_exit')):
        return True
    if any(_preset_moves_center(row) for row in event.get('preset_actions') or []):
        return True
    if _state_moves_center(event) or _vector_motion_authority(event):
        return True
    return False


