"""Backward-compatible module shim; implementation lives in hexa_v31.integration.premiere."""
from .integration import premiere as _implementation
from .integration.scene_ownership_premiere_contract import install as _install_scene_ownership_premiere_contract

_install_scene_ownership_premiere_contract(_implementation)

globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
