"""Backward-compatible module shim; implementation lives in hexa_v31.story.visual_sequence."""
from .story import visual_sequence as _implementation
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
