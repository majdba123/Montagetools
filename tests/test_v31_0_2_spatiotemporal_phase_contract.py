from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.preset_story_planner import _recover_trajectory_conflicts, _schedule_event


def event(eid, sem, center, priority, *, scene_id=None, source_bbox=None, source_order=None):
    row = {
        'event_id': eid, 'semantic_unit_id': sem, 'attention_priority': priority,
        'semantic_type': 'GROUP', 'source_bbox_norm': list(source_bbox or [0.0, 0.0, 0.15, 0.18]),
        'reference_camera_scale': 1.0, 'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': list(center), 'composite_atomic': False,
        'perceptual_hit_seconds': 1.0, 'suppressed_by_card_density': False,
        'relationship_source_requested': True,
        'render_mode': 'ROOT_ATOMIC',
    }
    if scene_id is not None:
        row['scene_id'] = scene_id
    if source_order is not None:
        row['source_scene_start_seconds'] = float(source_order)
    return row


def static_lifetime(row, start=0.0, end=4.0):
    row.update({
        'start_seconds': float(start),
        'end_seconds': float(end),
        'physical_start_seconds': float(start),
        'physical_end_seconds': float(end),
        'motion_start_seconds': float(start),
        'motion_end_seconds': float(end),
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'position_animated': False,
        'settle_seconds': float(start),
    })
    return row


card = {'card_id': 'GENERATED_CARD', 'start_seconds': 0.0, 'end_seconds': 4.0}
phase_plan = {'phases': [{'phase_id': 'P1', 'start_seconds': 0.0, 'end_seconds': 4.0,
                          'event_ids': ['SOURCE', 'TARGET']}]}
src = event('SOURCE', 'U_SOURCE', (0.5, 0.5), 'PRIMARY')
dst = event('TARGET', 'U_TARGET', (0.83, 0.5), 'SUPPORTING')
events = [src, dst]
for i, row in enumerate(events):
    _schedule_event(row, (0.0, 4.0), card, i, len(events), force_static=True)
src['preset_actions'] = [{
    'name': 'WITHIN_MIDDLE_TO_RIGHT', 'start_seconds': 1.0, 'duration_seconds': 0.9,
    'action_type': 'SEMANTIC_RELATIONSHIP', 'target_semantic_unit_id': 'U_TARGET',
    'relationship_evidence': 'EXPLICIT_INTERACTION_TARGET', 'relationship_confidence': 1.0,
}]
assert card_motion_conflicts(events, 0.0, 4.0, 30.0), 'fixture must contain a trajectory collision'
resolutions = [{'source': 'U_SOURCE', 'target': 'U_TARGET', 'mode': 'WITHIN_FRAME_PRESET',
                'preset': 'WITHIN_MIDDLE_TO_RIGHT'}]
resolved = _recover_trajectory_conflicts(card, events, phase_plan, resolutions, 30.0)
assert not card_motion_conflicts(events, 0.0, 4.0, 30.0)
assert src['preset_actions'] == []
assert resolved[0]['mode'] == 'TEMPORAL_HANDOFF'
assert resolved[0]['reason'] == 'ANIMATED_TRAJECTORY_COLLISION_RECOVERY'

# A later phase never becomes visible early and an earlier phase never survives its boundary.
left = event('LEFT_PHASE', 'U1', (0.5, 0.5), 'PRIMARY')
right = event('RIGHT_PHASE', 'U2', (0.5, 0.5), 'PRIMARY')
_schedule_event(left, (0.0, 2.0), card, 0, 2, force_static=True)
_schedule_event(right, (2.0, 4.0), card, 1, 2, force_static=True)
assert left['end_seconds'] <= 2.0 and right['start_seconds'] >= 2.0
assert not card_motion_conflicts([left, right], 0.0, 4.0, 30.0)

# Production regression: a mixed card can contain one unresolved same-scene settled
# collision plus a separate ordered cross-scene carrier overlap. The early planner must
# solve the independent same-scene roots against exact physical co-occurrence first,
# then leave only the cross-scene pair to the existing final handoff authority.
mixed_card = {
    'card_id': 'CARD_MIXED_GENERIC',
    'start_seconds': 0.0,
    'end_seconds': 4.0,
    'universal_scene_grammar': {'archetype': 'GENERIC', 'roles': {}, 'explicit_edges': []},
}
same_a = static_lifetime(event(
    'SAME_A', 'U_SAME_A', (0.5, 0.5), 'PRIMARY',
    scene_id='SCENE_A', source_bbox=[0.0, 0.0, 0.18, 0.22], source_order=0.0,
))
same_b = static_lifetime(event(
    'SAME_B', 'U_SAME_B', (0.5, 0.5), 'SUPPORTING',
    scene_id='SCENE_A', source_bbox=[0.0, 0.0, 0.18, 0.22], source_order=0.0,
))
cross = static_lifetime(event(
    'CROSS_B', 'U_CROSS_B', (0.5, 0.5), 'PRIMARY',
    scene_id='SCENE_B', source_bbox=[0.0, 0.0, 0.72, 0.68], source_order=2.0,
))
mixed_events = [same_a, same_b, cross]
mixed_phase = {
    'phases': [{
        'phase_id': 'MIXED_PHASE',
        'start_seconds': 0.0,
        'end_seconds': 4.0,
        'event_ids': [row['event_id'] for row in mixed_events],
    }]
}
initial = card_motion_conflicts(mixed_events, 0.0, 4.0, 30.0)
assert any({row['event_a'], row['event_b']} == {'SAME_A', 'SAME_B'} for row in initial), initial
_recover_trajectory_conflicts(mixed_card, mixed_events, mixed_phase, [], 30.0)
remaining = card_motion_conflicts(mixed_events, 0.0, 4.0, 30.0)
by_id = {row['event_id']: row for row in mixed_events}
assert not any(
    by_id[row['event_a']]['scene_id'] == by_id[row['event_b']]['scene_id']
    for row in remaining
), remaining
assert remaining, 'fixture must retain an ordered cross-scene overlap for final handoff reconciliation'
assert all(
    by_id[row['event_a']]['scene_id'] != by_id[row['event_b']]['scene_id']
    for row in remaining
), remaining
assert mixed_card['late_same_scene_collision_recovery'] == 'LATE_SAME_SCENE_EXACT_PHYSICAL_COOCCURRENCE_LAYOUT'
assert mixed_card['trajectory_recovery'] == 'DEFERRED_TO_FINAL_CROSS_SCENE_HANDOFF_RECONCILER'
assert all(not row.get('suppressed_by_card_density') for row in mixed_events)
assert same_a['late_same_scene_collision_recovery_authority'] == 'LATE_SAME_SCENE_EXACT_PHYSICAL_COOCCURRENCE_LAYOUT'
assert same_b['late_same_scene_collision_recovery_authority'] == 'LATE_SAME_SCENE_EXACT_PHYSICAL_COOCCURRENCE_LAYOUT'
assert any(row.get('cross_scene_handoff_authority') == 'FINAL_CROSS_SCENE_BOUNDED_HANDOFF_SEARCH' for row in mixed_events)

print('V31_0_9_SPATIOTEMPORAL_PHASE_CONTRACT_PASS')
