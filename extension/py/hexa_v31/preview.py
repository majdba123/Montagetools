"""Backward-compatible preview facade with canonical preset-coordinate enforcement.

The production preset authority is authored against a 1920x1080 Program Monitor.
Renderers may rasterize at another resolution for QA/proxies, but event Position values
must remain in canonical coordinates until the compositor performs the single output
scale.  Normalizing here prevents non-1080p renders from double-scaling Position while
leaving the 1920x1080 shipping path byte-for-byte equivalent in motion semantics.
"""
from __future__ import annotations

from .render import preview as _implementation

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
)


def _canonicalize_event_coordinates(event:dict)->dict:
    """Return an event whose pixel Position fields use the preset-authority space.

    Some low-resolution renderer paths materialize a planned normalized center into
    output-resolution pixels before calling the shared motion evaluator.  The shared
    compositor, however, deliberately scales canonical Position to output resolution.
    Without this normalization those paths scale Position twice.  We copy only when
    the event explicitly declares a non-canonical sequence size, preserving caller
    data and avoiding hidden mutation/global state.
    """
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


def _event_state(event:dict,t:float):
    return _implementation._event_state(_canonicalize_event_coordinates(event),t)
