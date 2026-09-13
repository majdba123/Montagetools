"""Persistent advisory memory for recovery strategies.

History may reorder equivalent recovery attempts on production machines, but it
never bypasses canonical QA. CI disables history by default so deterministic
regressions cannot depend on runner state.
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import threading

_SCHEMA = 'HEXA_RECOVERY_MEMORY_V1'
_LOCK = threading.Lock()


def _enabled() -> bool:
    override = os.environ.get('HEXA_RECOVERY_MEMORY_ENABLED')
    if override is not None:
        return override.strip().lower() not in {'0', 'false', 'no', 'off'}
    return os.environ.get('CI', '').strip().lower() not in {'1', 'true', 'yes', 'on'}


def _default_path() -> pathlib.Path | None:
    override = os.environ.get('HEXA_RECOVERY_MEMORY_PATH')
    if override:
        return pathlib.Path(override)
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        return None
    return pathlib.Path(local) / 'HEXA' / 'VideoBuilderV31' / 'recovery_memory.json'


class RecoveryMemory:
    """Small fail-open strategy memory; correctness never depends on persistence."""

    def __init__(self, path: pathlib.Path | None = None):
        self.enabled = _enabled()
        self.path = pathlib.Path(path) if path is not None else _default_path()
        self.data = self._load()

    def _load(self) -> dict:
        empty = {'schema': _SCHEMA, 'families': {}}
        if not self.enabled or not self.path or not self.path.is_file():
            return empty
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('schema') == _SCHEMA and isinstance(data.get('families'), dict):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return empty

    def _row(self, family: str, strategy: str) -> dict:
        return (((self.data.get('families') or {}).get(family) or {}).get(strategy) or {})

    def rank(self, family: str, strategies: list[str]) -> list[str]:
        if not self.enabled:
            return list(strategies)

        def key(strategy: str) -> tuple:
            row = self._row(family, strategy)
            attempts = max(0, int(row.get('attempts') or 0))
            successes = max(0, int(row.get('successes') or 0))
            # Beta(1,1) prior avoids over-trusting a single lucky sample.
            posterior = (successes + 1.0) / (attempts + 2.0)
            cost_total = max(0.0, float(row.get('successful_cost_total') or 0.0))
            average_cost = cost_total / successes if successes else float('inf')
            return (-posterior, -successes, average_cost, strategy)

        return sorted(strategies, key=key)

    def record(self, family: str, strategy: str, success: bool, cost: float = 0.0) -> None:
        if not self.enabled or not self.path or not family or not strategy:
            return
        with _LOCK:
            latest = self._load()
            families = latest.setdefault('families', {})
            row = families.setdefault(family, {}).setdefault(
                strategy,
                {'attempts': 0, 'successes': 0, 'successful_cost_total': 0.0},
            )
            row['attempts'] = int(row.get('attempts') or 0) + 1
            if success:
                row['successes'] = int(row.get('successes') or 0) + 1
                row['successful_cost_total'] = round(
                    float(row.get('successful_cost_total') or 0.0) + max(0.0, float(cost)), 6
                )
            self.data = latest
            self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.data, sort_keys=True, separators=(',', ':'))
            fd, temp_name = tempfile.mkstemp(prefix='.recovery.', suffix='.tmp', dir=str(self.path.parent))
            try:
                with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
        except OSError:
            # Persistence is advisory. Never turn a disk/permission problem into a build failure.
            pass
