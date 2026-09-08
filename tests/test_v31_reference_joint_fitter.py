from __future__ import annotations

from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.reference_geometry_finalizer import _projected_settled_ink
from hexa_v31.layout.reference_joint_fitter import finalize_reference_joint_geometry


def event(eid, x, y, bbox, *, primary=False, start=0.0, end=4.0, scene='SCENE_GENERIC'):
    row = {
        'event_id': eid,
        'scene_id': scene,
        'visual_card_id': 'CARD_GENERIC',
        'render_mode': 'ROOT_ATOMIC',
        'source_bbox_norm': list(bbox),
        'visible_ink_fraction': 0.88,
        'visible_ink_fraction_basis': 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        'reference_camera_scale': 1.0,
        'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': [x, y],
        'attention_priority': 'PRIMARY' if primary else 'SUPPORTING',
        'composition_role': 'LEAD' if primary else 'SUPPORT',
        'start_seconds': start,
        'end_seconds': end,
        'physical_start_seconds': start,
        'physical_end_seconds': end,
        'motion_start_seconds': start,
        'motion_end_seconds': end,
        'settle_seconds': min(end, start + 0.5),
        'perceptual_hit_seconds': start + 0.8,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'translation_safe_after_occlusion': False,
        'animation_safe': False,
        'position_animated': False,
    }
    fp = _fp(row)
    row['planned_rect_norm'] = list(_rect((x, y), fp, MOTION_ENVELOPE_SCALE))
    row['collision_envelope_rect_norm'] = list(row['planned_rect_norm'])
    return row


def card(events, *, end=4.0):
    return {
        'card_id': 'CARD_GENERIC',
        'start_seconds': 0.0,
        'end_seconds': end,
        'duration_seconds': end,
        'story_phase_plan': {
            'phases': [{
                'phase_id': 'PHASE_GENERIC',
                'start_seconds': 0.0,
                'end_seconds': end,
                'event_ids': [event['event_id'] for event in events],
            }],
        },
        'constraint_layout': {
            'placements': {
                event['event_id']: {
                    'center_norm': list(event['card_rest_position_norm']),
                    'scale': event['layout_scale_multiplier'],
                    'rect_norm': list(event['planned_rect_norm']),
                }
                for event in events
            },
        },
    }


def plan_for(prefix, *, duration=4.0):
    primary = event(prefix + '_PRIMARY', .28, .52, (0, 0, .15, .22), primary=True, end=duration)
    context = event(prefix + '_CONTEXT', .74, .52, (0, 0, .12, .18), end=duration)
    events = [primary, context]
    return {
        'fps': 30.0,
        'events': events,
        'visual_cards': {'cards': [card(events, end=duration)]},
    }, primary, context


plan, primary, context = plan_for('PACKAGE_ONE')
before_distance = context['card_rest_position_norm'][0] - primary['card_rest_position_norm'][0]
before_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
stats = finalize_reference_joint_geometry(plan, 30.0)
after_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
assert stats['pass'], stats
assert stats['joint_pairs_committed'] == 1, stats
assert stats['after_underfilled_seconds'] <= stats['before_underfilled_seconds'], stats
assert after_ink >= before_ink + 0.012, (before_ink, after_ink, stats)
assert primary['reference_joint_fit_partner_event_id'] == context['event_id']
assert context['reference_joint_fit_partner_event_id'] == primary['event_id']
assert primary['reference_joint_fit_authority'].startswith('SOURCE_BACKED_PRIMARY_CONTEXT_')
assert primary['layout_scale_multiplier'] > 1.0
assert context['layout_scale_multiplier'] > 1.0
assert context['card_rest_position_norm'][0] > primary['card_rest_position_norm'][0]
assert context['card_rest_position_norm'][0] - primary['card_rest_position_norm'][0] < before_distance
assert not primary['position_animated'] and not context['position_animated']

other, other_primary, other_context = plan_for('COMPLETELY_DIFFERENT_IDS', duration=9.5)
other_stats = finalize_reference_joint_geometry(other, 30.0)
assert other_stats['joint_pairs_committed'] == 1, other_stats
assert other_primary['layout_scale_multiplier'] == primary['layout_scale_multiplier']
assert other_context['layout_scale_multiplier'] == context['layout_scale_multiplier']
assert other_primary['card_rest_position_norm'] == primary['card_rest_position_norm']
assert other_context['card_rest_position_norm'] == context['card_rest_position_norm']

# Two competing primaries are never converted into a density pair.
a = event('PRIMARY_A', .28, .52, (0, 0, .15, .22), primary=True)
b = event('PRIMARY_B', .74, .52, (0, 0, .12, .18), primary=True)
two_primary = {'fps': 30.0, 'events': [a, b], 'visual_cards': {'cards': [card([a, b])]}}
assert finalize_reference_joint_geometry(two_primary, 30.0)['joint_pairs_committed'] == 0

# Position-authored actors are not statically relocated by this stage.
positioned_plan, positioned_primary, positioned_context = plan_for('POSITION_AUTHORITY')
positioned_context['position_animated'] = True
assert finalize_reference_joint_geometry(positioned_plan, 30.0)['joint_pairs_committed'] == 0
assert positioned_primary['card_rest_position_norm'] == [.28, .52]
assert positioned_context['card_rest_position_norm'] == [.74, .52]

# Mere temporal adjacency across unrelated scenes/phases is not semantic permission.
unrelated_primary = event('UNRELATED_PRIMARY', .28, .52, (0, 0, .15, .22), primary=True, scene='SCENE_ONE')
unrelated_context = event('UNRELATED_CONTEXT', .74, .52, (0, 0, .12, .18), scene='SCENE_TWO')
unrelated_card = card([unrelated_primary, unrelated_context])
unrelated_card['story_phase_plan']['phases'] = [
    {'phase_id': 'P1', 'event_ids': ['UNRELATED_PRIMARY']},
    {'phase_id': 'P2', 'event_ids': ['UNRELATED_CONTEXT']},
]
unrelated_plan = {
    'fps': 30.0,
    'events': [unrelated_primary, unrelated_context],
    'visual_cards': {'cards': [unrelated_card]},
}
assert finalize_reference_joint_geometry(unrelated_plan, 30.0)['joint_pairs_committed'] == 0

print('V31_REFERENCE_JOINT_PRIMARY_CONTEXT_FIT_PASS')
