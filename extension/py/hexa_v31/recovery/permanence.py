"""Permanent fail-closed enforcement for known production hard-gate failures.

A solved problem family is a product invariant, not a package-specific patch.  This
module owns the package-independent mapping between canonical Recovery problem ids and
the source-level bounded recovery contracts that are allowed to handle them.

The coordinator never lowers QA thresholds, suppresses semantic events, or promotes a
strategy to PROVEN.  It gives the already-installed source recovery chain one bounded
recertification attempt against the exact renderer-consumed plan, then reruns canonical
composition QA.  A known problem that remains is a hard build failure; an unclassified
canonical failure is also fail-closed so new bug families cannot leak into an encode.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re
from typing import Any, Callable

_SCHEMA = 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1'
_POLICY_MODE = 'AUTO_RECOVER_THEN_HARD_FAIL'

# This table is deliberately keyed only by stable problem identity.  It must never
# contain scene/card/event/package ids or timestamps.  Candidate details stay in the
# owning planner contract and every candidate is rechecked by canonical QA.
HARD_GATE_POLICIES: dict[str, dict[str, Any]] = {
    'HEXA_MOTION_PATH_OVERLAP': {
        'mode': _POLICY_MODE,
        'family': 'COLLISION',
        'recovery_owner': 'hexa_v31.planning.recovery_integrity_contract',
        'post_recovery_gate': 'CANONICAL_COMPOSITION_QA',
        'max_coordinator_recertification_passes': 1,
    },
    'HEXA_SETTLED_GEOMETRY_OVERLAP': {
        'mode': _POLICY_MODE,
        'family': 'COLLISION',
        'recovery_owner': 'hexa_v31.planning.final_certification_phase_contract',
        'post_recovery_gate': 'CANONICAL_COMPOSITION_QA',
        'max_coordinator_recertification_passes': 1,
    },
    'HEXA_VIEWPORT_CLIPPING': {
        'mode': _POLICY_MODE,
        'family': 'COMPOSITION',
        'recovery_owner': 'hexa_v31.planning.final_certification_phase_contract',
        'post_recovery_gate': 'CANONICAL_COMPOSITION_QA',
        'max_coordinator_recertification_passes': 1,
    },
}

_MOTION_PATH_RE = re.compile(r'\bmotion-path overlap\b', re.IGNORECASE)
_SETTLED_OVERLAP_RE = re.compile(r'\bsettled overlap\b|\bsettled geometry overlap\b', re.IGNORECASE)
_VIEWPORT_RE = re.compile(
    r'\bsettled bbox outside safe frame\b|\bsustained viewport clipping\b|\bviewport clipping\b',
    re.IGNORECASE,
)


def _default_registry_path() -> pathlib.Path:
    module_path = pathlib.Path(__file__).resolve()
    installed = module_path.parents[3] / 'recovery_data' / 'problem_registry.json'
    if installed.is_file():
        return installed
    return module_path.parents[4] / 'recovery_data' / 'problem_registry.json'


def load_registry(path: str | pathlib.Path | None = None) -> dict[str, Any]:
    registry_path = pathlib.Path(path) if path is not None else _default_registry_path()
    try:
        data = json.loads(registry_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f'KNOWN_PROBLEM_REGISTRY_UNAVAILABLE: {registry_path}: {exc}') from exc
    if data.get('schema') != _SCHEMA or not isinstance(data.get('problems'), list):
        raise RuntimeError(f'KNOWN_PROBLEM_REGISTRY_INVALID: {registry_path}')
    return data


def required_hard_gate_problem_ids(registry: dict[str, Any] | None = None) -> set[str]:
    data = registry or load_registry()
    return {
        str(row.get('problem_id') or '')
        for row in data.get('problems') or []
        if str(row.get('severity') or '').upper() == 'HARD_GATE'
        and 'CI' in set(row.get('allowed_sources') or [])
        and str(row.get('problem_id') or '')
    }


def validate_policy_coverage(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Require source recovery ownership for every registered CI hard gate."""
    required = required_hard_gate_problem_ids(registry)
    configured = set(HARD_GATE_POLICIES)
    missing = sorted(required - configured)
    stale = sorted(configured - required)
    registry_by_id = {
        str(row.get('problem_id') or ''): row
        for row in (registry or load_registry()).get('problems') or []
    }
    invalid = sorted(
        problem_id
        for problem_id, policy in HARD_GATE_POLICIES.items()
        if policy.get('mode') != _POLICY_MODE
        or policy.get('post_recovery_gate') != 'CANONICAL_COMPOSITION_QA'
        or int(policy.get('max_coordinator_recertification_passes') or 0) != 1
        or not str(policy.get('recovery_owner') or '').startswith('hexa_v31.planning.')
        or (registry_by_id.get(problem_id) or {}).get('runtime_policy') != _POLICY_MODE
        or (registry_by_id.get(problem_id) or {}).get('recovery_owner') != policy.get('recovery_owner')
        or (registry_by_id.get(problem_id) or {}).get('post_recovery_gate') != policy.get('post_recovery_gate')
    )
    if missing or stale or invalid:
        raise RuntimeError(
            'KNOWN_PROBLEM_PERMANENCE_POLICY_INVALID: '
            f'missing={missing} stale={stale} invalid={invalid}'
        )
    return {
        'pass': True,
        'required_problem_ids': sorted(required),
        'policy_problem_ids': sorted(configured),
        'mode': _POLICY_MODE,
    }


def classify_failure(message: str) -> str | None:
    text = str(message or '')
    if _MOTION_PATH_RE.search(text):
        return 'HEXA_MOTION_PATH_OVERLAP'
    if _SETTLED_OVERLAP_RE.search(text):
        return 'HEXA_SETTLED_GEOMETRY_OVERLAP'
    if _VIEWPORT_RE.search(text):
        return 'HEXA_VIEWPORT_CLIPPING'
    return None


def classify_failures(failures: list[Any] | tuple[Any, ...]) -> tuple[list[str], list[str]]:
    problem_ids: set[str] = set()
    unknown: list[str] = []
    for failure in failures or []:
        text = str(failure)
        problem_id = classify_failure(text)
        if problem_id is None:
            unknown.append(text)
        else:
            problem_ids.add(problem_id)
    return sorted(problem_ids), unknown


def _restore_plan(plan: dict[str, Any], snapshot: dict[str, Any]) -> None:
    plan.clear()
    plan.update(copy.deepcopy(snapshot))


def enforce_known_problem_permanence(
    plan: dict[str, Any],
    *,
    fps: float = 30.0,
    recertify: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    qa_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Enforce known hard-gate permanence on the exact final plan.

    ``recertify`` is intentionally injected by the motion layer so Recovery does not
    own planner internals or create an import cycle.  The coordinator permits at most
    one full recertification pass; the planner's individual recovery contracts remain
    responsible for their own bounded candidate loops and rollback semantics.
    """
    coverage = validate_policy_coverage()
    if qa_fn is None:
        from hexa_v31.composition_qa import composition_plan_qa
        qa_fn = composition_plan_qa

    before = qa_fn(plan)
    before_failures = list(before.get('failures') or [])
    before_ids, before_unknown = classify_failures(before_failures)
    if before.get('pass'):
        plan['known_problem_permanence_gate'] = {
            'schema': 'HEXA_KNOWN_PROBLEM_PERMANENCE_GATE_V1',
            'pass': True,
            'recovery_attempted': False,
            'known_problem_ids': [],
            'policy_coverage': coverage,
            'authority': 'EXACT_FINAL_PLAN_CANONICAL_QA',
        }
        return plan

    if before_unknown or not before_ids:
        raise ValueError(
            'KNOWN_PROBLEM_PERMANENCE_UNKNOWN_HARD_FAILURE: '
            + ' | '.join(before_unknown or before_failures)[:2400]
        )
    if recertify is None:
        raise ValueError(
            'KNOWN_PROBLEM_PERMANENCE_RECERTIFIER_REQUIRED: ' + ','.join(before_ids)
        )

    snapshot = copy.deepcopy(plan)
    try:
        candidate = recertify(plan, float(fps))
        if candidate is not plan:
            plan.clear()
            plan.update(candidate)
    except Exception as exc:
        _restore_plan(plan, snapshot)
        raise ValueError(
            'KNOWN_PROBLEM_PERMANENCE_RECOVERY_FAILED: '
            + ','.join(before_ids)
            + ': '
            + str(exc)[:2200]
        ) from exc

    after = qa_fn(plan)
    after_failures = list(after.get('failures') or [])
    after_ids, after_unknown = classify_failures(after_failures)
    if not after.get('pass'):
        _restore_plan(plan, snapshot)
        if after_unknown:
            raise ValueError(
                'KNOWN_PROBLEM_PERMANENCE_RECOVERY_INTRODUCED_UNKNOWN_FAILURE: '
                + ' | '.join(after_unknown)[:2400]
            )
        raise ValueError(
            'KNOWN_PROBLEM_PERMANENCE_HARD_FAIL: '
            + ','.join(after_ids or before_ids)
            + ': '
            + ' | '.join(after_failures)[:2200]
        )

    plan['known_problem_permanence_gate'] = {
        'schema': 'HEXA_KNOWN_PROBLEM_PERMANENCE_GATE_V1',
        'pass': True,
        'recovery_attempted': True,
        'known_problem_ids': before_ids,
        'remaining_problem_ids': [],
        'policy_coverage': coverage,
        'authority': 'AUTO_RECOVER_THEN_CANONICAL_REQA',
        'recovery_validation_state': 'CI_VERIFIED_RENDER_PENDING',
    }
    return plan
