from __future__ import annotations

from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.reference_geometry_finalizer import _projected_settled_ink
from hexa_v31.layout.reference_joint_fitter import _preset_moves_center, finalize_reference_joint_geometry


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


# Joint fitting must coordinate the two static destinations and respond to the
# card-level source-ink deficit, not stop at already-satisfied individual targets.
plan, primary, context = plan_for('PACKAGE_ONE')
before_distance = context['card_rest_position_norm'][0] - primary['card_rest_position_norm'][0]
before_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
stats = finalize_reference_joint_geometry(plan, 30.0)
after_ink = _projected_settled_ink(primary) + _projected_settled_ink(context)
assert stats['pass'], stats
assert stats['authority'] == 'REFERENCE_SEMANTIC_CARD_COHORT_FIT_V3', stats
assert stats['joint_pairs_committed'] == 1, stats
assert stats['after_underfilled_seconds'] <= stats['before_underfilled_seconds'], stats
assert stats['joint_max_target_ink'] > .26, stats
assert after_ink >= before_ink + 0.012, (before_ink, after_ink, stats)
assert primary['reference_joint_fit_partner_event_id'] == context['event_id']
assert context['reference_joint_fit_partner_event_id'] == primary['event_id']
assert primary['reference_joint_fit_authority'].startswith('SOURCE_BACKED_PRIMARY_CONTEXT_')
assert primary['reference_joint_fit_target_ink'] == stats['joint_max_target_ink']
assert primary['layout_scale_multiplier'] > 1.0
assert context['layout_scale_multiplier'] > 1.0
assert context['card_rest_position_norm'][0] > primary['card_rest_position_norm'][0]
assert context['card_rest_position_norm'][0] - primary['card_rest_position_norm'][0] < before_distance
assert not primary['position_animated'] and not context['position_animated']


# IDs and narration duration cannot select the geometry. Same normalized source
# structure must produce the same coordinated result across different packages.
other, other_primary, other_context = plan_for('COMPLETELY_DIFFERENT_IDS', duration=9.5)
other_stats = finalize_reference_joint_geometry(other, 30.0)
assert other_stats['joint_pairs_committed'] == 1, other_stats
assert other_primary['layout_scale_multiplier'] == primary['layout_scale_multiplier']
assert other_context['layout_scale_multiplier'] == context['layout_scale_multiplier']
assert other_primary['card_rest_position_norm'] == primary['card_rest_position_norm']
assert other_context['card_rest_position_norm'] == context['card_rest_position_norm']


# Scale/opacity-only P2/P4 authority must not starve a valid static joint fit.
appearance_plan, appearance_primary, appearance_context = plan_for('APPEARANCE_AUTHORITY')
appearance_primary['preset_entry'] = {
    'name': 'APPEAR_HIGH_SCALE',
    'start_seconds': 0.0,
    'duration_seconds': 0.8,
}
appearance_context['preset_actions'] = [{
    'name': 'APPEAR_HIGH_SCALE',
    'start_seconds': 1.0,
    'duration_seconds': 0.8,
}]
appearance_context['preset_exit'] = {
    'name': 'DISAPPEAR_DOWN_SCALE',
    'start_seconds': 3.4,
    'duration_seconds': 0.6,
}
appearance_stats = finalize_reference_joint_geometry(appearance_plan, 30.0)
assert appearance_stats['joint_pairs_requested'] >= 1, appearance_stats
assert appearance_stats['joint_pairs_committed'] == 1, appearance_stats
assert not appearance_stats['joint_rejections'].get('POSITION_OR_RENDER_AUTHORITY'), appearance_stats


# Center-preserving hierarchy states may travel with the new settled composition.
state_plan, state_primary, state_context = plan_for('CENTER_PRESERVING_STATE')
for actor in (state_primary, state_context):
    base = list(actor['card_rest_position_norm'])
    actor['composition_states'] = [
        {'start_seconds': 0.0, 'center_norm': list(base), 'scale_multiplier': 1.0, 'visibility': 1.0},
        {'start_seconds': 2.0, 'center_norm': list(base), 'scale_multiplier': 1.06, 'visibility': 1.0},
    ]
state_stats = finalize_reference_joint_geometry(state_plan, 30.0)
assert state_stats['joint_pairs_committed'] == 1, state_stats
for actor in (state_primary, state_context):
    assert all(row['center_norm'] == actor['card_rest_position_norm'] for row in actor['composition_states']), actor
    assert actor['composition_states'][-1]['scale_multiplier'] == 1.06, actor


# Two competing primaries are never converted into a density pair.
a = event('PRIMARY_A', .28, .52, (0, 0, .15, .22), primary=True)
b = event('PRIMARY_B', .74, .52, (0, 0, .12, .18), primary=True)
two_primary = {'fps': 30.0, 'events': [a, b], 'visual_cards': {'cards': [card([a, b])]}}
assert finalize_reference_joint_geometry(two_primary, 30.0)['joint_pairs_committed'] == 0


# Position-authored actors are not statically relocated by this stage.
positioned_plan, positioned_primary, positioned_context = plan_for('POSITION_AUTHORITY')
positioned_context['position_animated'] = True
positioned_stats = finalize_reference_joint_geometry(positioned_plan, 30.0)
assert positioned_stats['joint_pairs_requested'] >= 1, positioned_stats
assert positioned_stats['joint_pairs_committed'] == 0, positioned_stats
assert positioned_stats['joint_rejections'].get('POSITION_OR_RENDER_AUTHORITY') == 1, positioned_stats
assert positioned_primary['card_rest_position_norm'] == [.28, .52]
assert positioned_context['card_rest_position_norm'] == [.74, .52]


# Preset classification itself must preserve true travel while allowing the
# scale/opacity-only vocabulary used by P2/P4.
assert _preset_moves_center({'name': 'WITHIN_MIDDLE_TO_LEFT'})
assert _preset_moves_center({'name': 'ENTRY_LEFT_TO_MIDDLE'})
assert not _preset_moves_center({'name': 'APPEAR_HIGH_SCALE'})
assert not _preset_moves_center({'name': 'DISAPPEAR_DOWN_SCALE'})


# Mere temporal adjacency across unrelated scenes/phases is not semantic
# permission to use an actor as density filler.
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

# Presentation promotion must not erase explicit semantic context ownership.
promoted, focal, support = plan_for('PROMOTED_CONTEXT')
support.update(attention_priority='PRIMARY', semantic_role='SUPPORTING', relationship='CONTEXT_FOR')
assert finalize_reference_joint_geometry(promoted)['joint_pairs_committed'] == 1

# A bounded third support is fitted and rolled back with the entire cohort.
import copy
triple, focal, support = plan_for('COHORT')
third = event('COHORT_SECOND_SUPPORT', .74, .78, (0,0,.08,.10))
triple['events'].append(third)
triple['visual_cards']['cards'] = [card(triple['events'])]
triple_before = copy.deepcopy(triple)
triple_stats = finalize_reference_joint_geometry(triple)
assert triple_stats['joint_cohorts_committed'] == 1, triple_stats
assert len(triple_stats['joint_mutations'][0]['actors']) == 3
assert all(e['layout_scale_multiplier'] > 1 for e in triple['events'])
repeat = copy.deepcopy(triple_before)
assert finalize_reference_joint_geometry(repeat) == triple_stats
assert repeat == triple

# Material gain and viewport/collision failure restore every field atomically.
from unittest.mock import patch
for denied in ('_candidate_safe', '_density_not_worse'):
    rejected = copy.deepcopy(triple_before)
    with patch('hexa_v31.layout.reference_joint_fitter.'+denied, return_value=False):
        try:
            finalize_reference_joint_geometry(rejected)
        except ValueError:
            pass
    assert rejected == triple_before, denied
assert _projected_settled_ink(focal) >= max(_projected_settled_ink(e) for e in (support, third))
print('V31_SEMANTIC_CONTEXT_COHORT_ATOMICITY_PASS')

# Whole-card sparsity still requests a fit after both individual ink targets
# have been satisfied. Temporal card quality, not a fixed pair sum, owns it.
from hexa_v31.layout.reference_joint_fitter import _candidate_pairs
filled, a, b = plan_for('INDIVIDUAL_TARGETS')
a['source_bbox_norm']=[0,0,.50,.54]
b['source_bbox_norm']=[0,0,.32,.40]
assert _projected_settled_ink(a)>=.23 and _projected_settled_ink(b)>=.11
with patch('hexa_v31.layout.reference_joint_fitter._card_quality',
           return_value={'mean_ink':.15,'underfilled_seconds':2.}):
    assert _candidate_pairs(filled,30.)

material, _, _ = plan_for('NO_MATERIAL_CARD_GAIN')
original = copy.deepcopy(material)
with patch('hexa_v31.layout.reference_joint_fitter._card_quality',
           return_value={'mean_ink':.15,'underfilled_seconds':2.}):
    result=finalize_reference_joint_geometry(material)
assert result['joint_pairs_committed']==0 and material==original
assert result['joint_rejections'].get('NO_MATERIAL_CARD_GAIN'),result
print('V31_CARD_OWNED_DEFICIT_AND_MATERIAL_GAIN_PASS')
