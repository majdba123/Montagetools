from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RecoverySource = Literal['CI', 'RENDER']


@dataclass(frozen=True)
class RecoveryIncident:
    problem_id: str
    source: RecoverySource
    raw_name: str
    stage: str
    fingerprint: dict[str, Any] = field(default_factory=dict)
    message: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryDecision:
    problem_id: str
    solution_id: str
    strategy: str
    status: str
    source: RecoverySource
    fingerprint: dict[str, Any]
    evidence: dict[str, Any] = field(default_factory=dict)
