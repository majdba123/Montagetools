"""Backward-compatible module shim; implementation lives in hexa_v31.motion.visual_choreography."""
from importlib import import_module as _import_module
_implementation = _import_module('hexa_v31.motion.visual_choreography')
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
