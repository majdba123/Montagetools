"""Backward-compatible preview facade with canonical preset-coordinate enforcement.

The production preset authority is authored against a 1920x1080 Program Monitor.
Renderers may rasterize at another resolution for QA/proxies, but event Position values
must remain in canonical coordinates until the compositor performs the single output
scale. Normalizing here prevents non-1080p renders from double-scaling Position while
leaving the 1920x1080 shipping path equivalent in preset semantics.

V31 editorial phases are also materialized here after the canonical motion evaluator has
resolved preset motion.  This is the last event-state boundary shared by preview and
shipping scene-media rendering, so semantic phase geometry can no longer exist only as
planner metadata while encoded pixels remain unchanged.
"""
from __future__ import annotations

from .render import preview as _implementation
from .editorial_runtime import apply_editorial_runtime_state

globals().update({
    key: value
    for key, value in vars(_implementation).items()
    if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}
})

_CANONICAL_WIDTH = 1920.0
_CANONICAL_HEIGHT = 1080.0
_PIXEL_VECTOR_FIELDS = (
    'object_rest_position_px',
    'rest_position_px',
    'start_position_px',
    'end_position_px',
    'exit_position_px',
    'micro_position_px',
)


def _canonicalize_event_coordinates(event:dict)->dict:
    width=float(event.get('sequence_width') or _CANONICAL_WIDTH)
    height=float(event.get('sequence_height') or _CANONICAL_HEIGHT)
    if abs(width-_CANONICAL_WIDTH)<1e-6 and abs(height-_CANONICAL_HEIGHT)<1e-6:
        return event
    if width<=0.0 or height<=0.0:
        return event
    sx=_CANONICAL_WIDTH/width
    sy=_CANONICAL_HEIGHT/height
    normalized=dict(event)
    for field in _PIXEL_VECTOR_FIELDS:
        value=event.get(field)
        if isinstance(value,(list,tuple)) and len(value)>=2:
            normalized[field]=[float(value[0])*sx,float(value[1])*sy,*list(value[2:])]
    normalized['sequence_width']=_CANONICAL_WIDTH
    normalized['sequence_height']=_CANONICAL_HEIGHT
    normalized['coordinate_normalization']='CANONICAL_1920X1080_SINGLE_OUTPUT_SCALE'
    return normalized


def _materialize_static_planner_center(event:dict)->dict:
    """Bridge final settled planner geometry into the pure-static evaluator path."""
    planned=event.get('card_rest_position_norm')
    if not (isinstance(planned,(list,tuple)) and len(planned)>=2):
        return event
    if (
        event.get('position_animated')
        or event.get('preset_entry')
        or event.get('preset_exit')
        or event.get('preset_actions')
        or event.get('composition_states')
        or event.get('composition_participant_states')
    ):
        return event
    try:
        center=[float(planned[0])*_CANONICAL_WIDTH,float(planned[1])*_CANONICAL_HEIGHT]
    except (TypeError,ValueError,IndexError):
        return event
    bridged=dict(event)
    for field in _PIXEL_VECTOR_FIELDS:
        bridged[field]=list(center)
    bridged['sequence_width']=_CANONICAL_WIDTH
    bridged['sequence_height']=_CANONICAL_HEIGHT
    bridged['static_planner_center_authority']='FINAL_CARD_REST_POSITION_NORM'
    return bridged


def _event_state(event:dict,t:float):
    normalized=_canonicalize_event_coordinates(event)
    normalized=_materialize_static_planner_center(normalized)
    state=_implementation._event_state(normalized,t)
    return apply_editorial_runtime_state(normalized,t,state)
