from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension/py'))

from hexa_v31.composition_qa import _in_safe, _phase_settled_rect


def event_with_states(outbound_start: float) -> dict:
    return {
        'event_id': 'GENERIC_ACTOR',
        'attention_priority': 'PRIMARY',
        'source_bbox_norm': [0.45, 0.42, 0.10, 0.16],
        'visible_ink_fraction': 0.8,
        'card_rest_position_norm': [0.5, 0.5],
        'layout_scale_multiplier': 1.0,
        'start_seconds': 0.0,
        'end_seconds': 0.8,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 0.8,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 0.8,
        'composition_states': [
            {
                'state_id': 'PHASE_DESTINATION',
                'start_seconds': 0.0,
                'transition_duration_seconds': 0.20,
                'center_norm': [0.5, 0.5],
                'scale_multiplier': 1.0,
                'visibility': 1.0,
                'state_reason': 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY',
            },
            {
                'state_id': 'OUTBOUND_HANDOFF',
                'start_seconds': outbound_start,
                'transition_duration_seconds': 0.30,
                'center_norm': [0.95, 0.5],
                'scale_multiplier': 1.0,
                'visibility': 1.0,
                'state_reason': 'HANDOFF_GEOMETRY',
            },
        ],
    }


phase = {
    'phase_id': 'GENERIC_PHASE',
    'start_seconds': 0.0,
    'end_seconds': 0.60,
    'event_ids': ['GENERIC_ACTOR'],
}

# There is a real stable interval from 0.20s until the 0.35s handoff starts.
# Settled QA must sample inside that interval, not inside the outbound travel.
rect, visibility = _phase_settled_rect(event_with_states(0.35), phase)
assert visibility > 0.05, (rect, visibility)
assert _in_safe(rect), rect

# With only 10ms between arrival and the outbound handoff there is no useful
# static destination to call "settled". Dynamic motion/viewport QA owns this beat.
rect, visibility = _phase_settled_rect(event_with_states(0.21), phase)
assert visibility == 0.0, (rect, visibility)

print('V31_PHASE_SETTLED_QA_CONTRACT_PASS')
