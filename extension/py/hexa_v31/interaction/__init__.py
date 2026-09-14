"""Interaction-driven motion compiler for HEXA V31."""
from . import director as _director
from . import scene_ownership_contract as _scene_ownership_contract
from .scene_ownership_contract import install as _install_scene_ownership_contract
from .global_frame_coverage_contract import install as _install_global_frame_coverage_contract

_install_scene_ownership_contract(_director)
_install_global_frame_coverage_contract(_scene_ownership_contract)
build_interaction_motion_plan = _director.build_interaction_motion_plan

__all__=["build_interaction_motion_plan"]
