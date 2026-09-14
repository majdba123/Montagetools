from __future__ import annotations

from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.perceptual_finalizer import finalize_perceptual_composition


def event(eid, x, y, bbox, *, primary=False, render_mode='ROOT_ATOMIC', ink=.2):
    row = {
        'event_id': eid,
        'scene_id': 'GENERIC_SCENE',
        'visual_card_id': 'GENERIC_CARD',
        'render_mode': render_mode,
        'source_bbox_norm': list(bbox),
        'visible_ink_fraction': ink,
        'visible_ink_fraction_basis': 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        # Deliberately stale/high legacy matte value. Final density authority
        # must use visible_ink_fraction instead of this whole-canvas proxy.
        'matting': {'opaque_foreground_fraction': .95},
        'reference_camera_scale': 1.0,
        'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': [x, y],
        'attention_priority': 'PRIMARY' if primary else 'SUPPORTING',
        'composition_role': 'LEAD' if primary else 'SUPPORT',
        'start_seconds': 0.0,
        'end_seconds': 4.0,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 4.0,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 4.0,
        'settle_seconds': .8,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'translation_safe_after_occlusion': False,
        'animation_safe': False,
    }
    fp = _fp(row)
    row['planned_rect_norm'] = list(_rect((x, y), fp, MOTION_ENVELOPE_SCALE))
    row['collision_envelope_rect_norm'] = list(row['planned_rect_norm'])
    return row


focus = event('FOCUS', .30, .52, (0, 0, .18, .28), primary=True, ink=.20)
focus['meaningful_recomposition'] = True
focus['composition_states'] = [
    {
        'state_id': 'GENERIC_CARD::FOCUS::A',
        'start_seconds': .8,
        'transition_duration_seconds': 0.0,
        'center_norm': [.30, .52],
        'scale_multiplier': 1.0,
        'visibility': 1.0,
        'translation_safe': False,
    },
    {
        'state_id': 'GENERIC_CARD::FOCUS::B',
        'start_seconds': 2.0,
        'transition_duration_seconds': .48,
        'center_norm': [.30, .52],
        'scale_multiplier': 1.14,
        'visibility': 1.0,
        'translation_safe': False,
        'state_reason': 'SEMANTIC_FOCUS_TRANSFER_TO_NEXT_ACTOR',
    },
]
support = event('SUPPORT', .70, .52, (0, 0, .10, .16), ink=.55)
partition = event('PARTITION_CHILD', .82, .28, (0, 0, .08, .10), render_mode='CHILD_PARTITION', ink=.15)

card = {
    'card_id': 'GENERIC_CARD',
    'start_seconds': 0.0,
    'end_seconds': 4.0,
    'story_phase_plan': {
        'phases': [
            {
                'phase_id': 'GENERIC_CARD_P1',
                'start_seconds': 0.0,
                'end_seconds': 4.0,
                'event_ids': ['FOCUS', 'SUPPORT', 'PARTITION_CHILD'],
            }
        ]
    },
    'constraint_layout': {
        'placements': {
            row['event_id']: {
                'center_norm': list(row['card_rest_position_norm']),
                'scale': row['layout_scale_multiplier'],
                'rect_norm': list(row['planned_rect_norm']),
            }
            for row in (focus, support, partition)
        }
    },
}
plan = {
    'fps': 30.0,
    'events': [focus, support, partition],
    'visual_cards': {'cards': [card]},
}

partition_scale = partition['layout_scale_multiplier']
stats = finalize_perceptual_composition(plan, fps=30.0)

assert stats['pass'], stats
assert stats['scale_candidates_committed'] >= 1, stats
assert focus['layout_scale_multiplier'] > 1.0, focus
assert focus['final_visible_ink_scale_authority'] == 'SOURCE_BACKED_INK_WITH_FULL_LIFETIME_COLLISION_CERTIFICATION'
assert focus['final_visible_ink_after'] > focus['final_visible_ink_before'], focus
# Certified source partitions remain group-owned and are never enlarged as
# independent objects by the perceptual density pass.
assert partition['layout_scale_multiplier'] == partition_scale, partition
assert 'final_visible_ink_scale_authority' not in partition, partition
# Existing semantic recomposition may become stronger only after the same full
# trajectory/collision authority accepts the larger amplitude.
assert focus['composition_states'][-1]['scale_multiplier'] >= 1.14, focus
assert stats['hierarchy_candidates_committed'] >= 0
# Constraint-layout diagnostics must describe the exact final event geometry.
placement = card['constraint_layout']['placements']['FOCUS']
assert placement['scale'] == focus['layout_scale_multiplier'], (placement, focus)
assert placement['rect_norm'] == focus['planned_rect_norm'], (placement, focus)

print('V31_FINAL_PERCEPTUAL_COMPOSITION_PASS')
