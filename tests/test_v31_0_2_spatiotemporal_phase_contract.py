from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.preset_story_planner import _recover_trajectory_conflicts, _schedule_event


def event(eid, sem, center, priority):
    return {
        'event_id': eid, 'semantic_unit_id': sem, 'attention_priority': priority,
        'semantic_type': 'GROUP', 'source_bbox_norm': [0.0, 0.0, 0.15, 0.18],
        'reference_camera_scale': 1.0, 'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': list(center), 'composite_atomic': False,
        'perceptual_hit_seconds': 1.0, 'suppressed_by_card_density': False,
        'relationship_source_requested': True,
    }


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
print('V31_0_9_SPATIOTEMPORAL_PHASE_CONTRACT_PASS')
