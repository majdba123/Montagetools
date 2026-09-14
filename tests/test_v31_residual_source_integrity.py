from __future__ import annotations

from hexa_v31.composition_solver import _fp, _rect
from hexa_v31.layout.source_integrity_finalizer import (
    AUTHORITY,
    finalize_residual_source_integrity,
)


def residual_event():
    event = {
        'event_id': 'RESIDUAL',
        'scene_id': 'SCENE_A',
        'visual_card_id': 'CARD_A',
        'render_mode': 'RESIDUAL_SUPPORT',
        'source_bbox_norm': [0.0, 0.0, 0.10, 0.08],
        'source_center_norm': [0.50, 0.52],
        'visible_ink_fraction': 0.18,
        'visible_ink_fraction_basis': 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        'reference_camera_scale': 1.0,
        'layout_scale_multiplier': 2.4,
        'card_rest_position_norm': [0.74, 0.52],
        'attention_priority': 'SUPPORTING',
        'start_seconds': 0.0,
        'end_seconds': 4.0,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 4.0,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 4.0,
        'settle_seconds': 0.4,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'translation_safe_after_occlusion': False,
        'animation_safe': False,
        'position_animated': False,
        'composition_participant_states': [
            {
                'state_id': 'BAD_GENERIC_SUPPORT_PROMOTION',
                'start_seconds': 1.0,
                'transition_duration_seconds': 0.3,
                'center_norm': [0.80, 0.60],
                'scale_multiplier': 1.6,
                'visibility': 1.0,
                'sequence_envelope': True,
                'envelope_track': 'DENSITY_FRAME',
                'position_envelope': True,
            }
        ],
    }
    fp = _fp(event)
    event['planned_rect_norm'] = list(_rect(event['card_rest_position_norm'], fp, event['layout_scale_multiplier']))
    event['collision_envelope_rect_norm'] = list(event['planned_rect_norm'])
    return event


event = residual_event()
card = {
    'card_id': 'CARD_A',
    'start_seconds': 0.0,
    'end_seconds': 4.0,
    'story_phase_plan': {
        'phases': [
            {
                'phase_id': 'CARD_A_P1',
                'start_seconds': 0.0,
                'end_seconds': 4.0,
                'event_ids': ['RESIDUAL'],
            }
        ]
    },
    'constraint_layout': {
        'placements': {
            'RESIDUAL': {
                'center_norm': list(event['card_rest_position_norm']),
                'scale': event['layout_scale_multiplier'],
                'rect_norm': list(event['planned_rect_norm']),
            }
        }
    },
}
plan = {'fps': 30.0, 'events': [event], 'visual_cards': {'cards': [card]}}

stats = finalize_residual_source_integrity(plan, fps=30.0)
assert stats['pass'] and stats['changed'], stats
assert stats['event_count'] == 1, stats
assert event['layout_scale_multiplier'] == 1.0, event
assert event['card_rest_position_norm'] == [0.5, 0.52], event
assert event['residual_source_center_restored'] is True, event
assert event['residual_context_authority'] == AUTHORITY, event
assert event['residual_independent_recomposition_forbidden'] is True, event
state = event['composition_participant_states'][0]
assert state['scale_multiplier'] == 1.0, state
assert state['center_norm'] == [0.5, 0.52], state
assert state['position_envelope'] is False, state
placement = card['constraint_layout']['placements']['RESIDUAL']
assert placement['center_norm'] == [0.5, 0.52], placement
assert placement['scale'] == 1.0, placement

print('V31_RESIDUAL_SOURCE_INTEGRITY_PASS')
