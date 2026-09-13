VERSION = '31.0.25'
ENGINE_ID = 'HEXA_VIDEO_BUILDER_V31_0_25_PREMIUM_MOTION_INTERACTION_DIRECTOR'

# Composition focus hierarchy is a viewer-facing production contract.  Install it
# at package initialization so every import path (planner, QA, tests, preview and
# shipping render) observes the same certified phase geometry.
from . import composition_solver as _composition_solver
from .editorial_phase_contract import install as _install_editorial_phase_contract
_install_editorial_phase_contract(_composition_solver)

# Certified Foundation child partitions reconstruct one source-backed semantic
# composition slot. Install the phase-settled evaluator first, then the partition
# collision contract, so direct layout imports and the public compatibility facade
# share identical physical QA semantics. External/different-root collisions remain
# hard failures under the unchanged thresholds.
from .layout import composition_qa as _composition_qa
from .layout.phase_qa_contract import install as _install_phase_qa_contract
from .layout.partition_collision_contract import install as _install_partition_collision_contract
_install_phase_qa_contract(_composition_qa)
_install_partition_collision_contract(_composition_qa)
