from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension/py'))

from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa


def event(event_id: str, scene_id: str, root_id: str, *, complete: bool = True) -> dict:
    return {
        'event_id': event_id,
        'physical_id': event_id,
        'scene_id': scene_id,
        'visual_card_id': 'CARD_GENERIC',
        'render_mode': 'CHILD_PARTITION',
        'partition_root_id': root_id,
        'partition_complete': complete,
        'attention_priority': 'SUPPORTING',
        'source_bbox_norm': [0.35, 0.35, 0.30, 0.30],
        'reference_camera_scale': 1.0,
        'visible_ink_fraction': 0.8,
        'card_rest_position_norm': [0.50, 0.50],
        'layout_scale_multiplier': 1.0,
        'start_seconds': 0.0,
        'end_seconds': 3.0,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 3.0,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 3.0,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
    }


# Two physical children of one complete source partition are one semantic
# composition slot. Their internal bbox intersection is not an actor collision.
a = event('PART_A', 'SCENE_A', 'ROOT_A')
b = event('PART_B', 'SCENE_A', 'ROOT_A')
assert card_motion_conflicts([a, b], 0.0, 3.0, 30.0) == []

plan = {
    'fps': 30.0,
    'events': [a, b],
    'visual_cards': {
        'cards': [{
            'card_id': 'CARD_GENERIC',
            'start_seconds': 0.0,
            'end_seconds': 3.0,
            'story_phase_plan': {
                'phases': [{
                    'phase_id': 'PHASE_GENERIC',
                    'start_seconds': 0.0,
                    'end_seconds': 3.0,
                    'event_ids': ['PART_A', 'PART_B'],
                }]
            },
        }]
    },
}
qa = composition_plan_qa(plan)
assert qa['pass'], qa
assert qa['partition_internal_pair_count'] >= 1, qa
assert qa['partition_collision_authority'] == 'CERTIFIED_PARTITION_IS_ONE_SEMANTIC_COMPOSITION_SLOT'

# The exemption is deliberately narrow. Different roots in the same scene are
# still independent slots and must collide under the existing hard threshold.
different_root = event('OTHER_ROOT', 'SCENE_A', 'ROOT_B')
rows = card_motion_conflicts([a, different_root], 0.0, 3.0, 30.0)
assert rows and {rows[0]['event_a'], rows[0]['event_b']} == {'PART_A', 'OTHER_ROOT'}, rows

# The same root label in a different source scene does not create a partition
# relationship. Cross-scene overlap remains visible to the final handoff solver.
cross_scene = event('NEXT_SCENE', 'SCENE_B', 'ROOT_A')
rows = card_motion_conflicts([a, cross_scene], 0.0, 3.0, 30.0)
assert rows and {rows[0]['event_a'], rows[0]['event_b']} == {'PART_A', 'NEXT_SCENE'}, rows

# Mixed case matching production recovery: internal sibling overlap disappears,
# while both cross-scene conflicts remain for the bounded lifetime handoff authority.
rows = card_motion_conflicts([a, b, cross_scene], 0.0, 3.0, 30.0)
pairs = [{row['event_a'], row['event_b']} for row in rows]
assert {'PART_A', 'PART_B'} not in pairs, rows
assert {'PART_A', 'NEXT_SCENE'} in pairs, rows
assert {'PART_B', 'NEXT_SCENE'} in pairs, rows

# Incomplete partitions never receive the composite-slot exemption.
incomplete = event('INCOMPLETE', 'SCENE_A', 'ROOT_A', complete=False)
assert card_motion_conflicts([a, incomplete], 0.0, 3.0, 30.0)

print('V31_PARTITION_COLLISION_SLOT_CONTRACT_PASS')
