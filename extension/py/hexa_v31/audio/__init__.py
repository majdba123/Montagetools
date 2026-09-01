"""Audio layer and compatibility exports for ``hexa_v31.audio``."""
from . import audio as _implementation
globals().update({key: value for key, value in vars(_implementation).items() if not key.startswith('__')})
