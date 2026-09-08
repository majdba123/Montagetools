from __future__ import annotations

from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.reference_geometry_finalizer import finalize_reference_geometry
from hexa_v31.layout.reference_quality_finalizer import finalize_reference_density_topology


def event(eid, x, y, bbox, *, start=0.0, end=4.0, hit=1.0, primary=False,
          render_mode='ROOT_ATOMIC', ink=1.0, partition_root=None):
    row = {
        'event_id': eid,
        'scene_id': 'SCENE_A',
        'visual_card_id': 'CARD_A',
        'render_mode': render_mode,
        'source_bbox_norm': list(bbox),
        'visible_ink_fraction': ink,
        'visible_ink_fraction_basis': 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        'matting': {'opaque_foreground_fraction': ink},
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
        'settle_seconds': min(end, start + .8),
        'perceptual_hit_seconds': hit,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'translation_safe_after_occlusion': False,
        'animation_safe': False,
        'position_animated': False,
    }
    if partition_root is not None:
        row['partition_root_id'] = partition_root
        row['partition_complete'] = True
    fp = _fp(row)
    row['planned_rect_norm'] = list(_rect((x, y), fp, MOTION_ENVELOPE_SCALE))
    row['collision_envelope_rect_norm'] = list(row['planned_rect_norm'])
    return row


def card(events, *, end=4.0):
    return {
        'card_id': 'CARD_A',
        'start_seconds': 0.0,
        'end_seconds': end,
        'duration_seconds': end,
        'story_phase_plan': {
            'phases': [{
                'phase_id': 'CARD_A_P1',
                'start_seconds': 0.0,
                'end_seconds': end,
                'event_ids': [row['event_id'] for row in events],
            }]
        },
        'constraint_layout': {
            'placements': {
                row['event_id']: {
                    'center_norm': list(row['card_rest_position_norm']),
                    'scale': row['layout_scale_multiplier'],
                    'rect_norm': list(row['planned_rect_norm']),
                }
                for row in events
            }
        },
    }


# P3 topology regression: the outgoing source-backed context is already dense
# enough on its own. The incoming focus is deliberately sparse; once context
# retires, a sustained underfilled interval appears and must be rescued by
# retaining that real predecessor state rather than inventing new pixels.
context = event('CONTEXT', .30, .52, (0, 0, .40, .52), start=0.0, end=2.0, hit=.7, ink=1.0)
focus = event('FOCUS', .72, .52, (0, 0, .30, .32), start=1.5, end=4.0, hit=2.0, primary=True, ink=1.0)
card_a = card([context, focus])
plan = {'fps': 30.0, 'events': [context, focus], 'visual_cards': {'cards': [card_a]}}

topology = finalize_reference_density_topology(plan, fps=30.0)
assert topology['pass'], topology
assert topology['holds_committed'] >= 1, topology
assert float(context['end_seconds']) > 3.5, context
assert context['reference_density_hold_authority'] == 'SOURCE_BACKED_PREDECESSOR_STATE_CONTINUITY'
assert topology['after_underfilled_seconds'] < topology['before_underfilled_seconds'], topology


# P3 partition regression: certified source partitions remain atomic, but the
# whole partition may grow through one uniform transform. No child receives an
# independent source-ink scale authority.
left = event('PART_L', .39, .52, (0, 0, .08, .18), end=2.0, hit=.5,
             render_mode='CHILD_PARTITION', ink=1.0, partition_root='ROOT_X')
right = event('PART_R', .61, .52, (0, 0, .08, .18), end=2.0, hit=.5,
              render_mode='CHILD_PARTITION', ink=1.0, partition_root='ROOT_X')
partition_card = card([left, right], end=2.0)
partition_plan = {'fps': 30.0, 'events': [left, right], 'visual_cards': {'cards': [partition_card]}}
old_distance = abs(left['card_rest_position_norm'][0] - right['card_rest_position_norm'][0])
partition_stats = finalize_reference_geometry(partition_plan, fps=30.0)
assert partition_stats['pass'], partition_stats
assert partition_stats['partition_groups_committed'] >= 1, partition_stats
assert left['layout_scale_multiplier'] == right['layout_scale_multiplier'], (left, right)
assert left['layout_scale_multiplier'] > 1.0, (left, right)
new_distance = abs(left['card_rest_position_norm'][0] - right['card_rest_position_norm'][0])
assert new_distance > old_distance, (old_distance, new_distance)
assert left['reference_partition_scale_authority'] == 'SOURCE_BACKED_PARTITION_UNIFORM_TRANSFORM_FULL_LIFETIME_CERTIFIED'
assert right['reference_partition_scale_authority'] == left['reference_partition_scale_authority']
assert 'final_visible_ink_scale_authority' not in left
assert 'final_visible_ink_scale_authority' not in right


# P4 regression: after richer lifetimes exist, the reference geometry stage gets
# a second chance to compile a semantic focus transfer at the real next reveal.
# This is source-owned editorial choreography, never idle camera drift.
lead = event('LEAD', .28, .52, (0, 0, .16, .22), start=0.0, end=4.0, hit=.8, primary=True, ink=.9)
support = event('SUPPORT', .72, .52, (0, 0, .16, .22), start=1.4, end=4.0, hit=2.4, ink=.9)
cascade_card = card([lead, support])
cascade_plan = {'fps': 30.0, 'events': [lead, support], 'visual_cards': {'cards': [cascade_card]}}
cascade_stats = finalize_reference_geometry(cascade_plan, fps=30.0)
assert cascade_stats['pass'], cascade_stats
assert cascade_stats['semantic_cascade_committed'] >= 1, cascade_stats
assert lead.get('meaningful_recomposition'), lead
assert len(lead.get('composition_states') or []) >= 2, lead
assert len(support.get('composition_participant_states') or []) >= 2, support
assert float(lead['composition_states'][-1]['start_seconds']) <= float(support['perceptual_hit_seconds']), lead

print('V31_REFERENCE_QUALITY_FINALIZERS_PASS')
