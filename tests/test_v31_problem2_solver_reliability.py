from __future__ import annotations

from hexa_v31.interaction import constraint_solver as cs


class FakeCpModel:
    UNKNOWN = 0
    MODEL_INVALID = 1
    FEASIBLE = 2
    INFEASIBLE = 3
    OPTIMAL = 4


class FakeSolver:
    def __init__(self, status, wall=0.0, branches=0):
        self._status = status
        self._wall = wall
        self._branches = branches

    def Solve(self, model):
        return self._status

    def WallTime(self):
        return self._wall

    def NumBranches(self):
        return self._branches


original_factory = cs._new_solver
try:
    calls = []

    def unknown_then_feasible(cp_model, budget):
        calls.append(budget)
        return FakeSolver(
            cp_model.UNKNOWN if len(calls) == 1 else cp_model.FEASIBLE,
            wall=budget,
            branches=0 if len(calls) == 1 else 3,
        )

    cs._new_solver = unknown_then_feasible
    solver, status, attempts = cs._solve_with_unknown_retry(object(), FakeCpModel)
    assert status == FakeCpModel.FEASIBLE, (status, attempts)
    assert calls == [cs.SOLVER_FAST_BUDGET_SECONDS, cs.SOLVER_UNKNOWN_RETRY_BUDGET_SECONDS], calls
    assert [row['status'] for row in attempts] == ['UNKNOWN', 'FEASIBLE'], attempts
    assert attempts[0]['branches'] == 0 and attempts[1]['branches'] == 3, attempts

    calls.clear()

    def immediately_infeasible(cp_model, budget):
        calls.append(budget)
        return FakeSolver(cp_model.INFEASIBLE, wall=budget, branches=7)

    cs._new_solver = immediately_infeasible
    solver, status, attempts = cs._solve_with_unknown_retry(object(), FakeCpModel)
    assert status == FakeCpModel.INFEASIBLE, (status, attempts)
    assert calls == [cs.SOLVER_FAST_BUDGET_SECONDS], calls
    assert len(attempts) == 1 and attempts[0]['status'] == 'INFEASIBLE', attempts
finally:
    cs._new_solver = original_factory

print('V31_PROBLEM2_SOLVER_RELIABILITY_PASS')
