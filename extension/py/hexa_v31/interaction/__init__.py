"""Interaction-driven motion compiler for HEXA V31."""
from . import director as _director
from .scene_ownership_contract import install as _install_scene_ownership_contract

_install_scene_ownership_contract(_director)
build_interaction_motion_plan = _director.build_interaction_motion_plan

__all__=["build_interaction_motion_plan"]
