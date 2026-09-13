from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import tempfile
import threading
from typing import Any

from .errors import RecoveryDataError, RecoveryPromotionRejected

_LOCK = threading.RLock()
_REGISTRY_SCHEMA = 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1'
_PROVEN_SCHEMA = 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1'
_HISTORY_SCHEMA = 'HEXA_RECOVERY_HISTORY_V1'
_HEX40 = re.compile(r'^[0-9a-fA-F]{40}$')
_HEX64 = re.compile(r'^[0-9a-fA-F]{64}$')
_HISTORY_STATUSES = {
    'DETECTED', 'CANDIDATE_IMPLEMENTED', 'CI_VERIFIED_RENDER_PENDING',
    'RENDER_REJECTED', 'PROVEN', 'DEPRECATED',
}
_FORBIDDEN_FINGERPRINT_FIELDS = {
    'event_id', 'event_a', 'event_b', 'scene_id', 'card_id', 'project_name',
    'project_id', 'package_name', 'package_id', 'timestamp', 'time_seconds',
}


class RecoveryStore:
    """Version-controlled recovery knowledge store.

    Runtime detection may read this store. Promotion is deliberately explicit and
    requires both technical and encoded-video visual evidence. Nothing in this class
    automatically declares a technically passing candidate as PROVEN.
    """

    def __init__(self, data_root: str | os.PathLike[str] | None = None):
        if data_root is None:
            data_root = pathlib.Path(__file__).resolve().parents[1] / 'recovery_data'
        self.data_root = pathlib.Path(data_root)
        self.registry_path = self.data_root / 'problem_registry.json'
        self.proven_path = self.data_root / 'proven_solutions.json'
        self.history_path = self.data_root / 'recovery_history.json'

    @staticmethod
    def _read_json(path: pathlib.Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError as exc:
            raise RecoveryDataError(f'RECOVERY_DATA_MISSING: {path}') from exc
        except (OSError, ValueError, TypeError) as exc:
            raise RecoveryDataError(f'RECOVERY_DATA_INVALID_JSON: {path}: {exc}') from exc
        if not isinstance(value, dict):
            raise RecoveryDataError(f'RECOVERY_DATA_ROOT_NOT_OBJECT: {path}')
        return value

    @staticmethod
    def _validate_unique(rows: list[dict], key: str, label: str) -> None:
        seen: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise RecoveryDataError(f'{label}[{index}] must be an object')
            value = str(row.get(key) or '')
            if not value:
                raise RecoveryDataError(f'{label}[{index}] missing {key}')
            if value in seen:
                raise RecoveryDataError(f'{label} duplicate {key}={value}')
            seen.add(value)

    def load_registry(self) -> dict[str, Any]:
        data = self._read_json(self.registry_path)
        if data.get('schema') != _REGISTRY_SCHEMA:
            raise RecoveryDataError('RECOVERY_REGISTRY_SCHEMA_MISMATCH')
        rows = data.get('problems')
        if not isinstance(rows, list):
            raise RecoveryDataError('RECOVERY_REGISTRY_PROBLEMS_NOT_LIST')
        self._validate_unique(rows, 'problem_id', 'problems')
        for row in rows:
            sources = row.get('allowed_sources')
            if not isinstance(sources, list) or not sources or any(source not in {'CI', 'RENDER'} for source in sources):
                raise RecoveryDataError(f"invalid allowed_sources for {row.get('problem_id')}")
            fields = row.get('reusable_fingerprint_fields')
            if not isinstance(fields, list):
                raise RecoveryDataError(f"reusable_fingerprint_fields missing for {row.get('problem_id')}")
            if len(fields) != len(set(map(str, fields))):
                raise RecoveryDataError(f"duplicate reusable_fingerprint_fields for {row.get('problem_id')}")
            forbidden = _FORBIDDEN_FINGERPRINT_FIELDS.intersection(map(str, fields))
            if forbidden:
                raise RecoveryDataError(
                    f"forbidden reusable_fingerprint_fields for {row.get('problem_id')}: {sorted(forbidden)}"
                )
        return data

    def _problem_map(self) -> dict[str, dict[str, Any]]:
        return {
            str(row['problem_id']): row
            for row in self.load_registry()['problems']
        }

    @staticmethod
    def _raise(error_cls, message: str):
        raise error_cls(message)

    @classmethod
    def _validate_approval(cls, solution: dict[str, Any], error_cls=RecoveryPromotionRejected) -> None:
        technical = solution.get('technical_approval') or {}
        visual = solution.get('visual_approval') or {}
        if technical.get('status') != 'PASS':
            cls._raise(error_cls, 'PROVEN_REQUIRES_TECHNICAL_PASS')
        if visual.get('status') != 'PASS':
            cls._raise(error_cls, 'PROVEN_REQUIRES_VISUAL_PASS')
        source_commit = str(technical.get('source_commit') or '')
        if not _HEX40.fullmatch(source_commit):
            cls._raise(error_cls, 'PROVEN_REQUIRES_VALID_SOURCE_COMMIT')
        render_sha = str(visual.get('render_sha256') or '')
        if not _HEX64.fullmatch(render_sha):
            cls._raise(error_cls, 'PROVEN_REQUIRES_VALID_RENDER_SHA256')
        if not str(visual.get('reviewed_against') or '').strip():
            cls._raise(error_cls, 'PROVEN_REQUIRES_VISUAL_REVIEW_TARGET')
        try:
            validations = int(solution.get('successful_visual_validations') or 0)
        except (TypeError, ValueError):
            validations = 0
        if validations < 1:
            cls._raise(error_cls, 'PROVEN_REQUIRES_SUCCESSFUL_VISUAL_VALIDATION')

    @classmethod
    def _validate_fingerprint_constraints(
        cls,
        solution: dict[str, Any],
        problem: dict[str, Any],
        error_cls=RecoveryPromotionRejected,
    ) -> None:
        constraints = solution.get('fingerprint_constraints')
        if not isinstance(constraints, dict):
            cls._raise(error_cls, 'PROVEN_REQUIRES_FINGERPRINT_CONSTRAINTS_OBJECT')
        keys = set(map(str, constraints.keys()))
        forbidden = keys.intersection(_FORBIDDEN_FINGERPRINT_FIELDS)
        if forbidden:
            cls._raise(error_cls, f'PROVEN_FORBIDS_INSTANCE_FINGERPRINT_FIELDS: {sorted(forbidden)}')
        allowed = set(map(str, problem.get('reusable_fingerprint_fields') or []))
        unknown = keys - allowed
        if unknown:
            cls._raise(error_cls, f'PROVEN_UNKNOWN_FINGERPRINT_FIELDS: {sorted(unknown)}')

    def load_proven(self) -> dict[str, Any]:
        data = self._read_json(self.proven_path)
        if data.get('schema') != _PROVEN_SCHEMA:
            raise RecoveryDataError('RECOVERY_PROVEN_SCHEMA_MISMATCH')
        rows = data.get('solutions')
        if not isinstance(rows, list):
            raise RecoveryDataError('RECOVERY_PROVEN_SOLUTIONS_NOT_LIST')
        self._validate_unique(rows, 'solution_id', 'solutions')
        problems = self._problem_map()
        for row in rows:
            if row.get('status') != 'PROVEN':
                raise RecoveryDataError(f"non-PROVEN row in proven_solutions: {row.get('solution_id')}")
            problem_id = str(row.get('problem_id') or '')
            problem = problems.get(problem_id)
            if problem is None:
                raise RecoveryDataError(f'PROVEN_UNKNOWN_PROBLEM_ID: {problem_id}')
            self._validate_approval(row, RecoveryDataError)
            self._validate_fingerprint_constraints(row, problem, RecoveryDataError)
        return data

    def load_history(self) -> dict[str, Any]:
        data = self._read_json(self.history_path)
        if data.get('schema') != _HISTORY_SCHEMA:
            raise RecoveryDataError('RECOVERY_HISTORY_SCHEMA_MISMATCH')
        rows = data.get('records')
        if not isinstance(rows, list):
            raise RecoveryDataError('RECOVERY_HISTORY_RECORDS_NOT_LIST')
        self._validate_unique(rows, 'history_id', 'records')
        problems = self._problem_map()
        for row in rows:
            problem_id = str(row.get('problem_id') or '')
            if problem_id not in problems:
                raise RecoveryDataError(f'HISTORY_UNKNOWN_PROBLEM_ID: {problem_id}')
            status = str(row.get('status') or '')
            if status not in _HISTORY_STATUSES:
                raise RecoveryDataError(f'HISTORY_INVALID_STATUS: {status}')
        return data

    def problem(self, problem_id: str) -> dict[str, Any] | None:
        target = str(problem_id)
        for row in self.load_registry()['problems']:
            if str(row.get('problem_id')) == target:
                return copy.deepcopy(row)
        return None

    @staticmethod
    def fingerprint_matches(constraints: dict[str, Any], fingerprint: dict[str, Any]) -> bool:
        for key, expected in (constraints or {}).items():
            if key not in fingerprint:
                return False
            actual = fingerprint[key]
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True

    def proven_solutions(self, problem_id: str, fingerprint: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for row in self.load_proven()['solutions']:
            if str(row.get('problem_id')) != str(problem_id):
                continue
            if not self.fingerprint_matches(row.get('fingerprint_constraints') or {}, fingerprint):
                continue
            rows.append(copy.deepcopy(row))
        rows.sort(key=lambda row: (
            -int(row.get('successful_visual_validations') or 0),
            float(row.get('average_cost') or 0.0),
            str(row.get('solution_id')),
        ))
        return rows

    @staticmethod
    def _atomic_write(path: pathlib.Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
        fd, temp_name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def append_history(self, record: dict[str, Any]) -> None:
        record = copy.deepcopy(record)
        history_id = str(record.get('history_id') or '')
        if not history_id:
            raise RecoveryDataError('history record missing history_id')
        problem_id = str(record.get('problem_id') or '')
        if self.problem(problem_id) is None:
            raise RecoveryDataError(f'HISTORY_UNKNOWN_PROBLEM_ID: {problem_id}')
        status = str(record.get('status') or '')
        if status not in _HISTORY_STATUSES:
            raise RecoveryDataError(f'HISTORY_INVALID_STATUS: {status}')
        with _LOCK:
            data = self.load_history()
            if any(str(row.get('history_id')) == history_id for row in data['records']):
                raise RecoveryDataError(f'duplicate history_id={history_id}')
            data['records'].append(record)
            self._atomic_write(self.history_path, data)

    def promote_solution(self, solution: dict[str, Any]) -> None:
        solution = copy.deepcopy(solution)
        solution['status'] = 'PROVEN'
        self._validate_approval(solution, RecoveryPromotionRejected)
        problem = self.problem(str(solution.get('problem_id') or ''))
        if problem is None:
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_REGISTERED_PROBLEM')
        self._validate_fingerprint_constraints(solution, problem, RecoveryPromotionRejected)
        solution_id = str(solution.get('solution_id') or '')
        strategy = str(solution.get('strategy') or '')
        if not solution_id or not strategy:
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_SOLUTION_ID_AND_STRATEGY')
        with _LOCK:
            data = self.load_proven()
            if any(str(row.get('solution_id')) == solution_id for row in data['solutions']):
                raise RecoveryPromotionRejected(f'DUPLICATE_PROVEN_SOLUTION_ID: {solution_id}')
            data['solutions'].append(solution)
            self._atomic_write(self.proven_path, data)
