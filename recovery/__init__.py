"""HEXA recovery knowledge layer.

The root recovery package owns problem identity, proven-solution lookup and
version-controlled recovery knowledge. Production planners may implement candidate
strategies, but only encoded-video visual approval can promote one to PROVEN.
"""

from .detector import detect_problem
from .engine import RecoveryEngine
from .errors import (
    RecoveryDataError,
    RecoveryError,
    RecoveryProblemUnknown,
    RecoveryPromotionRejected,
    RecoverySolutionNotFound,
)
from .models import RecoveryDecision, RecoveryIncident
from .store import RecoveryStore

__all__ = [
    'RecoveryDataError',
    'RecoveryDecision',
    'RecoveryEngine',
    'RecoveryError',
    'RecoveryIncident',
    'RecoveryProblemUnknown',
    'RecoveryPromotionRejected',
    'RecoverySolutionNotFound',
    'RecoveryStore',
    'detect_problem',
]
