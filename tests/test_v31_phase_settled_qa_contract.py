from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension/py'))

from hexa_v31.composition_qa import _in_safe, _phase_settled_rect, _phase_common_settled_rects


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


# Round 3 can start a directional entry a few frames after the semantic phase
# boundary. The travel intentionally begins outside the safe frame and reaches
# its certified destination later. A short phase that ends before that inbound
# motion settles has no settled rectangle; dynamic path/viewport QA owns it.
directional_entry_event = {
    'event_id': 'DELAYED_DIRECTIONAL_ACTOR',
    'attention_priority': 'SUPPORTING',
    'source_bbox_norm': [0.45, 0.45, 0.10, 0.10],
    'visible_ink_fraction': 1.0,
    'card_rest_position_norm': [0.76, 0.25],
    'layout_scale_multiplier': 1.8,
    'start_seconds': 2.12,
    'end_seconds': 3.6,
    'physical_start_seconds': 2.0,
    'physical_end_seconds': 3.6,
    'motion_start_seconds': 2.12,
    'motion_end_seconds': 3.6,
    'preset_entry': {
        'name': 'APPEAR_HIGH_SCALE',
        'start_seconds': 2.12,
        'duration_seconds': 0.8,
    },
    'composition_states': [
        {
            'state_id': 'PHASE_GEOMETRY',
            'start_seconds': 2.0,
            'transition_duration_seconds': 0.26,
            'center_norm': [0.76, 0.25],
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'state_reason': 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY',
        },
        {
            'state_id': 'EDITORIAL_ENTRY_ORIGIN',
            'start_seconds': 2.12,
            'transition_duration_seconds': 0.0,
            'center_norm': [1.035, 0.25],
            'scale_multiplier': 0.96,
            'visibility': 0.0,
            'position_envelope': True,
            'envelope_track': 'EDITORIAL_ENTRY',
            'editorial_motion_family': 'DIRECTIONAL_ENTRY',
        },
        {
            'state_id': 'EDITORIAL_ENTRY_SETTLE',
            'start_seconds': 2.153333,
            'transition_duration_seconds': 0.656,
            'center_norm': [0.76, 0.25],
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'position_envelope': True,
            'envelope_track': 'EDITORIAL_ENTRY',
            'editorial_motion_family': 'DIRECTIONAL_ENTRY',
            'previous_state_id': 'EDITORIAL_ENTRY_ORIGIN',
        },
    ],
}
short_entry_phase = {
    'phase_id': 'DIRECTIONAL_ENTRY_PHASE',
    'start_seconds': 2.0,
    'end_seconds': 2.72,
    'event_ids': ['DELAYED_DIRECTIONAL_ACTOR'],
}
rect, visibility = _phase_settled_rect(directional_entry_event, short_entry_phase)
assert visibility == 0.0, (rect, visibility)

# Once the phase extends beyond the inbound envelope, settled QA must resume and
# certify the final safe destination rather than permanently exempt the actor.
long_entry_phase = dict(short_entry_phase, end_seconds=3.35)
rect, visibility = _phase_settled_rect(directional_entry_event, long_entry_phase)
assert visibility > 0.05, (rect, visibility)
assert _in_safe(rect), rect


# Pairwise settled QA must use one common timestamp. The outgoing actor is stable
# only until 0.35s; the incoming actor does not finish its appearance until 0.70s.
# Comparing their two independent settled snapshots would invent a composition
# that never exists on screen. The swept-motion gate remains responsible for the
# actual handoff frames, so there is no simultaneous settled pair to return.
outgoing = event_with_states(0.35)
outgoing['event_id'] = 'OUTGOING'
outgoing['composition_states'][0]['state_id'] = 'OUTGOING_DESTINATION'
outgoing['composition_states'][1]['state_id'] = 'OUTGOING_HANDOFF'

incoming = {
    'event_id': 'INCOMING',
    'attention_priority': 'SUPPORTING',
    'source_bbox_norm': [0.45, 0.42, 0.10, 0.16],
    'visible_ink_fraction': 0.8,
    'card_rest_position_norm': [0.5, 0.5],
    'layout_scale_multiplier': 1.0,
    'start_seconds': 0.30,
    'end_seconds': 0.80,
    'physical_start_seconds': 0.30,
    'physical_end_seconds': 0.80,
    'motion_start_seconds': 0.30,
    'motion_end_seconds': 0.80,
    'preset_entry': {
        'name': 'APPEAR_HIGH_SCALE',
        'start_seconds': 0.30,
        'duration_seconds': 0.40,
    },
    'composition_states': [
        {
            'state_id': 'INCOMING_DESTINATION',
            'start_seconds': 0.30,
            'transition_duration_seconds': 0.0,
            'center_norm': [0.5, 0.5],
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'state_reason': 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY',
        },
    ],
}
handoff_phase = {
    'phase_id': 'HANDOFF_ONLY_PHASE',
    'start_seconds': 0.0,
    'end_seconds': 0.80,
    'event_ids': ['OUTGOING', 'INCOMING'],
}
# Each actor individually has a stable destination inside the phase.
assert _phase_settled_rect(outgoing, handoff_phase)[1] > 0.05
assert _phase_settled_rect(incoming, handoff_phase)[1] > 0.05
# But there is no common stable interval, so pairwise settled overlap is undefined.
assert _phase_common_settled_rects([outgoing, incoming], handoff_phase) == []

# When the incoming actor settles before the outgoing handoff, the common stable
# composition becomes certifiable again and both actors must be returned together.
incoming_with_overlap = dict(incoming)
incoming_with_overlap['preset_entry'] = dict(incoming['preset_entry'], duration_seconds=0.02)
common = _phase_common_settled_rects([event_with_states(0.60), incoming_with_overlap], handoff_phase)
assert len(common) == 2, common

print('V31_PHASE_SETTLED_QA_CONTRACT_PASS')
