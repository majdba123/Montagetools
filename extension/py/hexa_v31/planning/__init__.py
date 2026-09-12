"""HEXA V31 planning layer.

Shipping code imports ``hexa_v31.planning.preset_story_planner`` directly, so
editorial planner corrections must be installed at the planning-package boundary
rather than only through the legacy top-level facade.  Keeping the installation
here makes preview, tests and production motion share the exact same planner
functions without duplicating renderer behavior.
"""
from . import preset_story_planner as _preset_story_planner
from .round2_editorial import install as _install_round2_editorial

_install_round2_editorial(_preset_story_planner)
