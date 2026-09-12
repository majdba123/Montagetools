"""Backward-compatible module shim; implementation lives in hexa_v31.planning.preset_story_planner."""
from .planning import preset_story_planner as _implementation
from .planning.round2_editorial import install as _install_round2_editorial
from .planning.same_scene_collision_recovery_contract import install as _install_same_scene_collision_recovery

_install_round2_editorial(_implementation)
_install_same_scene_collision_recovery(_implementation)
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
