"""Backward-compatible module shim; implementation lives in hexa_v31.extraction.projected_visible_ink."""
from .extraction import projected_visible_ink as _implementation
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
