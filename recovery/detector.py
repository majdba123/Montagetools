from __future__ import annotations

import re
from typing import Any

from .errors import RecoveryProblemUnknown
from .models import RecoveryIncident, RecoverySource

_DYNAMIC_OVERLAP_RE = re.compile(
    r'(?P<card>VCARD_[^@:\s]+)@(?P<time>[0-9]+(?:\.[0-9]+)?)s:\s*'
    r'motion-path overlap\s+(?P<a>\S+)\s+x\s+(?P<b>\S+)='
)

_RENDER_CODE_TO_PROBLEM = {
    'MOTION_PATH_OVERLAP': 'HEXA_MOTION_PATH_OVERLAP',
    'SETTLED_GEOMETRY_OVERLAP': 'HEXA_SETTLED_GEOMETRY_OVERLAP',
    'VIEWPORT_CLIPPING': 'HEXA_VIEWPORT_CLIPPING',
    'STALE_ACTOR': 'HEXA_RENDER_STALE_ACTOR',
    'WEAK_FOCUS': 'HEXA_RENDER_WEAK_FOCUS',
    'POSTER_LIKE_CARD': 'HEXA_RENDER_POSTER_LIKE_CARD',
    'BAD_HANDOFF': 'HEXA_RENDER_BAD_HANDOFF',
    'VISUAL_SYNC': 'HEXA_RENDER_VISUAL_SYNC',
}


def _generic_fingerprint(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(metadata or {})
    allowed = (
        'conflict_type', 'actor_a_role', 'actor_b_role', 'cross_scene',
        'same_visual_card', 'incoming_motion_family', 'outgoing_motion_family',
        'render_mode_a', 'render_mode_b', 'semantic_relation', 'severity',
    )
    return {key: metadata[key] for key in allowed if key in metadata}


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
    the reusable fingerprint used to match future packages.
    """
    text = str(message or '')
    metadata = dict(metadata or {})

    match = _DYNAMIC_OVERLAP_RE.search(text)
    if match:
        fingerprint = _generic_fingerprint(metadata)
        fingerprint.setdefault('conflict_type', 'MOTION_PATH')
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
            stage or 'COMPOSITION_QA', _generic_fingerprint(metadata), text, metadata,
        )
    if 'clip' in lowered and ('viewport' in lowered or 'safe frame' in lowered):
        return RecoveryIncident(
            'HEXA_VIEWPORT_CLIPPING', source, 'viewport clipping',
            stage or 'COMPOSITION_QA', _generic_fingerprint(metadata), text, metadata,
        )

    code = str(render_code or '').strip().upper()
    problem_id = _RENDER_CODE_TO_PROBLEM.get(code)
    if problem_id:
        return RecoveryIncident(
            problem_id=problem_id,
            source=source,
            raw_name=code,
            stage=stage or 'ENCODED_VIDEO_VISUAL_REVIEW',
            fingerprint=_generic_fingerprint(metadata),
            message=text,
            metadata=metadata,
        )

    raise RecoveryProblemUnknown(
        f"RECOVERY_PROBLEM_UNKNOWN: source={source} stage={stage or 'UNKNOWN'} message={text[:600]}"
    )
