"""Read-only ranking hints from visually proven recovery solutions.

A technical test/CI pass is never learning authority. Only entries already promoted
into the version-controlled ``recovery_data/proven_solutions.json`` after encoded-video
visual approval may influence future strategy order. The compatibility ``record`` API
is intentionally a no-op so older planner contracts cannot accidentally train from a
CI-only result.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

_SCHEMA = 'HEXA_RECOVERY_PROVEN_SOLUTIONS_V1'
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


def _enabled() -> bool:
    override = os.environ.get('HEXA_RECOVERY_MEMORY_ENABLED')
    if override is None:
        return True
    return override.strip().lower() not in _FALSE_VALUES


def _configured_runtime_path() -> pathlib.Path | None:
    candidates = []
    explicit = os.environ.get('HEXA_V31_RUNTIME_CONFIG')
    if explicit:
        candidates.append(pathlib.Path(explicit))
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidates.append(pathlib.Path(local) / 'HEXA' / 'VideoBuilderV31' / 'runtime_config.json')
    for cfg_path in candidates:
        if not cfg_path.is_file():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
            configured = str(cfg.get('recovery_proven_solutions_path') or '')
            if configured:
                return pathlib.Path(configured)
        except (OSError, ValueError, TypeError):
            continue
    return None


def _default_path() -> pathlib.Path:
    override = os.environ.get('HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH')
    if override:
        return pathlib.Path(override)
    configured = _configured_runtime_path()
    if configured is not None:
        return configured
    # Source checkout layout:
    # repo/extension/py/hexa_v31/recovery/memory.py -> parents[4] == repo.
    return pathlib.Path(__file__).resolve().parents[4] / 'recovery_data' / 'proven_solutions.json'


def _approved(row: dict[str, Any]) -> bool:
    technical = row.get('technical_approval') or {}
    visual = row.get('visual_approval') or {}
    return (
        row.get('status') == 'PROVEN'
        and technical.get('status') == 'PASS'
        and bool(str(technical.get('source_commit') or ''))
        and visual.get('status') == 'PASS'
        and bool(str(visual.get('render_sha256') or ''))
        and bool(str(visual.get('reviewed_against') or ''))
    )


class RecoveryMemory:
    """Compatibility reader for PROVEN strategy ranking only.

    Missing/corrupt data deliberately falls back to authored deterministic strategy
    order. Correctness still comes from canonical QA after every candidate.
    """

    def __init__(self, path: pathlib.Path | None = None):
        self.enabled = _enabled()
        self.path = pathlib.Path(path) if path is not None else _default_path()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        empty = {'schema': _SCHEMA, 'solutions': []}
        if not self.enabled or not self.path.is_file():
            return empty
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return empty
        if data.get('schema') != _SCHEMA or not isinstance(data.get('solutions'), list):
            return empty
        return {
            'schema': _SCHEMA,
            'solutions': [row for row in data['solutions'] if isinstance(row, dict) and _approved(row)],
        }

    def rank(self, family: str, strategies: list[str]) -> list[str]:
        authored = list(strategies)
        if not self.enabled or not authored:
            return authored

        index = {strategy: position for position, strategy in enumerate(authored)}
        hints = []
        for row in self.data.get('solutions') or []:
            ranking_family = str(row.get('ranking_family') or row.get('recovery_memory_family') or '')
            strategy = str(row.get('strategy') or row.get('recovery_strategy') or '')
            if ranking_family != str(family) or strategy not in index:
                continue
            hints.append((
                -int(row.get('successful_visual_validations') or 1),
                float(row.get('average_cost') or 0.0),
                str(row.get('solution_id') or ''),
                strategy,
            ))
        if not hints:
            return authored

        preferred = []
        seen = set()
        for *_score, strategy in sorted(hints):
            if strategy not in seen:
                preferred.append(strategy)
                seen.add(strategy)
        preferred.extend(strategy for strategy in authored if strategy not in seen)
        return preferred

    def record(self, family: str, strategy: str, success: bool, cost: float = 0.0) -> None:
        """Compatibility no-op: technical outcomes are not learning authority."""
        return None
