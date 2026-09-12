VERSION = '31.0.25'
ENGINE_ID = 'HEXA_VIDEO_BUILDER_V31_0_25_PREMIUM_MOTION_INTERACTION_DIRECTOR'

# Composition focus hierarchy is a viewer-facing production contract.  Install it
# at package initialization so every import path (planner, QA, tests, preview and
# shipping render) observes the same certified phase geometry.
from . import composition_solver as _composition_solver
from .editorial_phase_contract import install as _install_editorial_phase_contract
_install_editorial_phase_contract(_composition_solver)
