from __future__ import annotations

from typing import Any

from .detector import detect_problem
from .errors import RecoveryProblemUnknown, RecoverySolutionNotFound
from .models import RecoveryDecision, RecoveryIncident, RecoverySource
from .store import RecoveryStore


class RecoveryEngine:
    """Lookup-only recovery coordinator.

    This layer never invents or silently promotes fixes. It identifies a problem and
    returns only a solution that already carries both technical and visual approval.
    Unknown or unproven problems fail closed so engineering can add a candidate fix,
    run CI, render the encoded video, review it, and then explicitly promote it.
    """

    def __init__(self, store: RecoveryStore | None = None):
        self.store = store or RecoveryStore()

    def detect(
        self,
        message: str,
        source: RecoverySource,
        *,
        stage: str = '',
        metadata: dict[str, Any] | None = None,
        render_code: str | None = None,
    ) -> RecoveryIncident:
        incident = detect_problem(
            message, source, stage=stage, metadata=metadata, render_code=render_code
        )
        problem = self.store.problem(incident.problem_id)
        if problem is None:
            raise RecoveryProblemUnknown(
                f'RECOVERY_PROBLEM_NOT_REGISTERED: {incident.problem_id}'
            )
        if incident.source not in set(problem.get('allowed_sources') or []):
            raise RecoveryProblemUnknown(
                f'RECOVERY_SOURCE_NOT_ALLOWED: {incident.problem_id}:{incident.source}'
            )
        return incident

    def resolve(self, incident: RecoveryIncident) -> RecoveryDecision:
        matches = self.store.proven_solutions(incident.problem_id, incident.fingerprint)
        if not matches:
            raise RecoverySolutionNotFound(
                incident.problem_id, incident.source, incident.fingerprint
            )
        solution = matches[0]
        return RecoveryDecision(
            problem_id=incident.problem_id,
            solution_id=str(solution['solution_id']),
            strategy=str(solution['strategy']),
            status='PROVEN',
            source=incident.source,
            fingerprint=dict(incident.fingerprint),
            evidence={
                'technical_approval': solution.get('technical_approval') or {},
                'visual_approval': solution.get('visual_approval') or {},
            },
        )

    def detect_and_resolve(self, message: str, source: RecoverySource, **kwargs) -> RecoveryDecision:
        return self.resolve(self.detect(message, source, **kwargs))
