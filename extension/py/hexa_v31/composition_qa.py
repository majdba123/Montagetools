"""Backward-compatible module shim; implementation lives in hexa_v31.layout.composition_qa."""
from .layout import composition_qa as _implementation
from .layout.phase_qa_contract import install as _install_phase_qa_contract
from .layout.partition_collision_contract import install as _install_partition_collision_contract

# Install both planner-visible QA contracts before exporting symbols. Production
# planning imports ``card_motion_conflicts`` by value from this facade, so a later
# monkey-patch of the implementation would leave the shipping planner holding the
# unpatched function. The order matters: partition-aware composition QA delegates
# settled sampling to the phase QA contract.
_install_phase_qa_contract(_implementation)
_install_partition_collision_contract(_implementation)

globals().update({
    key: value
    for key, value in vars(_implementation).items()
    if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}
})
