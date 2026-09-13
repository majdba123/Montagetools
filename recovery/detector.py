from __future__ import annotations

import re
from typing import Any

from .errors import RecoveryProblemUnknown
from .models import RecoveryIncident, RecoverySource

_DYNAMIC_OVERLAP_RE = re.compile(
    r'(?P<card>VCARD_[^@:\s]+)@(?P<time>[0-9]+(?:\.[0-9]+)?)s:\s*'
    r'motion-path overlap\s+(?P<a>\S+)\s+x\s+(?P<b>\S+)='
)

_RENDER_CODE_SPECS = {
    'MOTION_PATH_OVERLAP': (
        'HEXA_MOTION_PATH_OVERLAP', 'motion-path overlap', {'conflict_type': 'MOTION_PATH'}
    ),
    'SETTLED_GEOMETRY_OVERLAP': (
        'HEXA_SETTLED_GEOMETRY_OVERLAP', 'settled geometry overlap', {'conflict_type': 'SETTLED_GEOMETRY'}
    ),
    'VIEWPORT_CLIPPING': (
        'HEXA_VIEWPORT_CLIPPING', 'viewport clipping', {'conflict_type': 'VIEWPORT_CLIPPING'}
    ),
    'STALE_ACTOR': ('HEXA_RENDER_STALE_ACTOR', 'stale actor', {}),
    'WEAK_FOCUS': ('HEXA_RENDER_WEAK_FOCUS', 'weak focus', {}),
    'POSTER_LIKE_CARD': ('HEXA_RENDER_POSTER_LIKE_CARD', 'poster-like card', {}),
    'BAD_HANDOFF': ('HEXA_RENDER_BAD_HANDOFF', 'bad handoff', {}),
    'VISUAL_SYNC': ('HEXA_RENDER_VISUAL_SYNC', 'visual sync', {}),
}


def _generic_fingerprint(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(metadata or {})
    allowed = (
        'conflict_type', 'actor_a_role', 'actor_b_role', 'cross_scene',
        'same_visual_card', 'incoming_motion_family', 'outgoing_motion_family',
        'render_mode_a', 'render_mode_b', 'semantic_relation', 'severity',
    )
    return {key: metadata[key] for key in allowed if key in metadata}


def _normalized_fingerprint(metadata: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    fingerprint = _generic_fingerprint(metadata)
    for key, value in defaults.items():
        fingerprint.setdefault(key, value)
    return fingerprint


def detect_problem(
    message: str,
    source: RecoverySource,
    *,
    stage: str = '',
    metadata: dict[str, Any] | None = None,
    render_code: str | None = None,
) -> RecoveryIncident:
    """Map CI text or render-review codes to one stable problem identity.

    Event/card ids and timestamps remain diagnostic metadata only; they never enter
    the reusable fingerprint used to match future packages. The same underlying
    problem is normalized to the same canonical fingerprint regardless of whether
    CI or encoded-render review detected it.
    """
    text = str(message or '')
    metadata = dict(metadata or {})

    match = _DYNAMIC_OVERLAP_RE.search(text)
    if match:
        fingerprint = _normalized_fingerprint(metadata, {'conflict_type': 'MOTION_PATH'})
        return RecoveryIncident(
            problem_id='HEXA_MOTION_PATH_OVERLAP',
            source=source,
            raw_name='motion-path overlap',
            stage=stage or 'FINAL_PHYSICAL_CERTIFICATION',
            fingerprint=fingerprint,
            message=text,
            metadata={
                **metadata,
                'card_id': match.group('card'),
                'time_seconds': float(match.group('time')),
                'event_a': match.group('a'),
                'event_b': match.group('b'),
            },
        )

    lowered = text.lower()
    if 'settled' in lowered and 'overlap' in lowered:
        return RecoveryIncident(
            'HEXA_SETTLED_GEOMETRY_OVERLAP', source, 'settled geometry overlap',
            stage or 'COMPOSITION_QA',
            _normalized_fingerprint(metadata, {'conflict_type': 'SETTLED_GEOMETRY'}),
            text, metadata,
        )
    if 'clip' in lowered and ('viewport' in lowered or 'safe frame' in lowered):
        return RecoveryIncident(
            'HEXA_VIEWPORT_CLIPPING', source, 'viewport clipping',
            stage or 'COMPOSITION_QA',
            _normalized_fingerprint(metadata, {'conflict_type': 'VIEWPORT_CLIPPING'}),
            text, metadata,
        )

    code = str(render_code or '').strip().upper()
    spec = _RENDER_CODE_SPECS.get(code)
    if spec:
        problem_id, raw_name, defaults = spec
        return RecoveryIncident(
            problem_id=problem_id,
            source=source,
            raw_name=raw_name,
            stage=stage or 'ENCODED_VIDEO_VISUAL_REVIEW',
            fingerprint=_normalized_fingerprint(metadata, defaults),
            message=text,
            metadata=metadata,
        )

    raise RecoveryProblemUnknown(
        f"RECOVERY_PROBLEM_UNKNOWN: source={source} stage={stage or 'UNKNOWN'} message={text[:600]}"
    )
