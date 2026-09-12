"""Backward-compatible module shim; implementation lives in hexa_v31.layout.composition_qa."""
from .layout import composition_qa as _implementation
from .layout.phase_qa_contract import install as _install_phase_qa_contract

_install_phase_qa_contract(_implementation)
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
