from __future__ import annotations

import copy
import json
import os
import pathlib
import tempfile
import threading
from typing import Any

from .errors import RecoveryDataError, RecoveryPromotionRejected

_LOCK = threading.RLock()
_REGISTRY_SCHEMA = 'HEXA_RECOVERY_PROBLEM_REGISTRY_V1'
_PROVEN_SCHEMA = 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1'
_HISTORY_SCHEMA = 'HEXA_RECOVERY_HISTORY_V1'


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
        return data

    def load_proven(self) -> dict[str, Any]:
        data = self._read_json(self.proven_path)
        if data.get('schema') != _PROVEN_SCHEMA:
            raise RecoveryDataError('RECOVERY_PROVEN_SCHEMA_MISMATCH')
        rows = data.get('solutions')
        if not isinstance(rows, list):
            raise RecoveryDataError('RECOVERY_PROVEN_SOLUTIONS_NOT_LIST')
        self._validate_unique(rows, 'solution_id', 'solutions')
        for row in rows:
            if row.get('status') != 'PROVEN':
                raise RecoveryDataError(f"non-PROVEN row in proven_solutions: {row.get('solution_id')}")
            self._validate_approval(row)
        return data

    def load_history(self) -> dict[str, Any]:
        data = self._read_json(self.history_path)
        if data.get('schema') != _HISTORY_SCHEMA:
            raise RecoveryDataError('RECOVERY_HISTORY_SCHEMA_MISMATCH')
        rows = data.get('records')
        if not isinstance(rows, list):
            raise RecoveryDataError('RECOVERY_HISTORY_RECORDS_NOT_LIST')
        self._validate_unique(rows, 'history_id', 'records')
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
    def _validate_approval(solution: dict[str, Any]) -> None:
        technical = solution.get('technical_approval') or {}
        visual = solution.get('visual_approval') or {}
        if technical.get('status') != 'PASS':
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_TECHNICAL_PASS')
        if visual.get('status') != 'PASS':
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_VISUAL_PASS')
        if not str(technical.get('source_commit') or ''):
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_SOURCE_COMMIT')
        if not str(visual.get('render_sha256') or ''):
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_RENDER_SHA256')
        if not str(visual.get('reviewed_against') or ''):
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_VISUAL_REVIEW_TARGET')

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
        with _LOCK:
            data = self.load_history()
            if any(str(row.get('history_id')) == history_id for row in data['records']):
                raise RecoveryDataError(f'duplicate history_id={history_id}')
            data['records'].append(record)
            self._atomic_write(self.history_path, data)

    def promote_solution(self, solution: dict[str, Any]) -> None:
        solution = copy.deepcopy(solution)
        solution['status'] = 'PROVEN'
        self._validate_approval(solution)
        if not self.problem(str(solution.get('problem_id') or '')):
            raise RecoveryPromotionRejected('PROVEN_REQUIRES_REGISTERED_PROBLEM')
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
