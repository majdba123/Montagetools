from __future__ import annotations

class RecoveryError(RuntimeError):
    pass

class RecoveryDataError(RecoveryError):
    pass

class RecoveryProblemUnknown(RecoveryError):
    pass

class RecoverySolutionNotFound(RecoveryError):
    def __init__(self, problem_id: str, source: str, fingerprint: dict | None = None):
        self.problem_id = str(problem_id)
        self.source = str(source)
        self.fingerprint = dict(fingerprint or {})
        super().__init__(f"RECOVERY_SOLUTION_NOT_FOUND: problem_id={self.problem_id} source={self.source} fingerprint={self.fingerprint}")

class RecoveryPromotionRejected(RecoveryError):
    pass
