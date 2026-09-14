from __future__ import annotations

import copy

from hexa_v31.composition_qa import _state
from hexa_v31.planning.scene_ownership import compile_scene_ownership
from hexa_v31.planning.scene_ownership_qa import scene_ownership_qa
from hexa_v31.render.preview import _event_state
from hexa_v31.interaction import director as _interaction_director
from hexa_v31.render import preview as _render_preview


def _root(event_id: str, scene_id: str, source_start: float, source_end: float,
          start: float, end: float, *, x: float = 0.5) -> dict:
    return {
        'event_id': event_id,
        'scene_id': scene_id,
        'visual_card_id': 'CARD_GENERIC',
        'render_mode': 'ROOT_ATOMIC',
        'source_scene_start_seconds': source_start,
        'source_scene_end_seconds': source_end,
        'start_seconds': start,
        'settle_seconds': start,
        'end_seconds': end,
        'physical_start_seconds': start,
        'physical_end_seconds': end,
        'visibility_interval_seconds': [start, end],
        'card_rest_position_norm': [x, 0.5],
        'object_rest_position_px': [x * 1920.0, 540.0],
        'source_bbox_norm': [0.0, 0.0, 0.18, 0.18],
        'layout_scale_multiplier': 1.0,
        'visible_ink_fraction': 0.8,
        'attention_priority': 'PRIMARY',
    }


def _plan(events: list[dict], end: float) -> dict:
    return {
        'fps': 30.0,
        'events': events,
        'visual_cards': {'cards': [{
            'card_id': 'CARD_GENERIC',
            'start_seconds': 0.0,
            'end_seconds': end,
            'duration_seconds': end,
        }]},
    }


def _ordinary_handoff_is_one_source_per_encoded_frame() -> None:
    for fps in (24.0, 30.0, 60.0):
        outgoing = _root('OUT', 'SOURCE_A', 0.0, 2.0, 0.0, 2.2, x=0.3)
        incoming = _root('IN', 'SOURCE_B', 2.0, 4.0, 1.8, 4.0, x=0.7)
        plan = _plan([outgoing, incoming], 4.0)
        original = copy.deepcopy(plan['events'])

        compiler = compile_scene_ownership(plan, fps=fps)
        qa = scene_ownership_qa(plan, fps=fps)

        assert compiler['pass'], compiler
        assert qa['pass'], qa
        assert compiler['raw_mixed_scene_pairs'] == [['SOURCE_A', 'SOURCE_B']], compiler
        assert compiler['final_mixed_scene_pairs'] == [], compiler
        assert qa['mixed_frame_count'] == 0 and qa['uncovered_handoff_count'] == 0, qa
        boundary = compiler['handoffs'][0]
        assert boundary['frame'] == int(round(2.0 * fps)), boundary
        assert abs(outgoing['scene_ownership_end_seconds'] - 2.0) <= 1.0 / fps + 1e-6
        assert abs(incoming['scene_ownership_start_seconds'] - 2.0) <= 1.0 / fps + 1e-6

        # Pixel ownership is not semantic retiming.
        for before, after in zip(original, plan['events']):
            for field in ('start_seconds', 'settle_seconds', 'end_seconds',
                          'physical_start_seconds', 'physical_end_seconds'):
                assert after[field] == before[field], (field, before, after)
            assert after.get('preset_entry') == before.get('preset_entry')
            assert after.get('preset_actions') == before.get('preset_actions')

        t = boundary['frame'] / fps
        assert _state(outgoing, t) is None
        assert _state(incoming, t) is not None
        assert _event_state(outgoing, t) is None
        assert _event_state(incoming, t) is not None



def _fractional_frame_boundary_does_not_round_past_its_own_frame() -> None:
    outgoing = _root('OUT_FRACTIONAL', 'SOURCE_A', 0.0, 2.0, 0.0, 3.0, x=0.35)
    incoming = _root('IN_FRACTIONAL', 'SOURCE_B', 2.0, 4.0, 2.44, 4.0, x=0.65)
    incoming['physical_start_seconds'] = 2.0
    incoming['visibility_interval_seconds'] = [2.0, 4.0]
    incoming['preset_entry'] = {
        'name': 'APPEAR_HIGH_SCALE',
        'start_seconds': 2.44,
        'duration_seconds': 0.8,
    }
    plan = _plan([outgoing, incoming], 4.0)
    compiler = compile_scene_ownership(plan, fps=30.0)
    qa = scene_ownership_qa(plan, fps=30.0)
    assert compiler['pass'], compiler
    assert qa['pass'], qa
    boundary = compiler['handoffs'][0]
    assert boundary['frame'] == 74, boundary
    assert incoming['scene_ownership_start_seconds'] == 74 / 30.0, incoming
    assert qa['uncovered_handoff_count'] == 0, qa

def _protected_partition_releases_to_independent_root_without_mutation() -> None:
    partition = _root('PART_A', 'SOURCE_A', 0.0, 2.0, 0.0, 2.2, x=0.35)
    partition.update({
        'render_mode': 'CHILD_PARTITION',
        'partition_root_id': 'ROOT_COMPOSITE',
        'partition_group_id': 'GROUP_COMPOSITE',
        'partition_carrier_start_seconds': 0.0,
        'partition_carrier_end_seconds': 2.2,
    })
    residual = copy.deepcopy(partition)
    residual.update({
        'event_id': 'PART_SUPPORT',
        'render_mode': 'RESIDUAL_SUPPORT',
        'card_rest_position_norm': [0.42, 0.5],
        'object_rest_position_px': [806.4, 540.0],
        'independent_motion_allowed': False,
        'translation_safe_after_occlusion': False,
    })
    incoming = _root('ROOT_B', 'SOURCE_B', 2.0, 4.0, 2.0, 4.0, x=0.7)
    plan = _plan([partition, residual, incoming], 4.0)
    physical_before = {
        e['event_id']: (
            e['physical_start_seconds'], e['physical_end_seconds'],
            e.get('partition_carrier_start_seconds'), e.get('partition_carrier_end_seconds'),
        )
        for e in plan['events']
    }

    compiler = compile_scene_ownership(plan, fps=30.0)
    qa = scene_ownership_qa(plan, fps=30.0)

    assert compiler['pass'], compiler
    assert qa['pass'], qa
    assert compiler['handoffs'][0]['reason'] == 'PROTECTED_PARTITION_MATERIAL_RELEASE', compiler
    assert abs(incoming['scene_ownership_start_seconds'] - 2.2) < 1e-6, incoming
    assert compiler['protected_root_recoveries'], compiler
    assert compiler['protected_root_recoveries'][0]['delayed_independent_root_event_ids'] == ['ROOT_B']
    assert physical_before == {
        e['event_id']: (
            e['physical_start_seconds'], e['physical_end_seconds'],
            e.get('partition_carrier_start_seconds'), e.get('partition_carrier_end_seconds'),
        )
        for e in plan['events']
    }
    assert all(row['pass'] for row in qa['protected_partition_groups']), qa


def _protected_handoff_fails_closed_for_non_independent_incoming_actor() -> None:
    partition = _root('PART_A', 'SOURCE_A', 0.0, 2.0, 0.0, 2.2)
    partition.update({
        'render_mode': 'CHILD_PARTITION',
        'partition_root_id': 'ROOT_COMPOSITE',
        'partition_group_id': 'GROUP_COMPOSITE',
        'partition_carrier_start_seconds': 0.0,
        'partition_carrier_end_seconds': 2.2,
    })
    incoming = _root('PART_B', 'SOURCE_B', 2.0, 4.0, 2.0, 4.0)
    incoming.update({
        'render_mode': 'CHILD_PARTITION',
        'partition_root_id': 'ROOT_B',
        'partition_group_id': 'GROUP_B',
        'partition_carrier_start_seconds': 2.0,
        'partition_carrier_end_seconds': 4.0,
    })
    report = compile_scene_ownership(_plan([partition, incoming], 4.0), fps=30.0)
    assert not report['pass'], report
    assert any('would suppress non-independent incoming actors' in failure for failure in report['failures'])


def _semantic_actions_cannot_be_hidden_by_pixel_ownership() -> None:
    outgoing = _root('OUT', 'SOURCE_A', 0.0, 2.0, 0.0, 2.2)
    outgoing.update({
        'render_mode': 'CHILD_PARTITION',
        'partition_root_id': 'ROOT_A',
        'partition_group_id': 'GROUP_A',
        'partition_carrier_start_seconds': 0.0,
        'partition_carrier_end_seconds': 2.2,
    })
    incoming = _root('IN', 'SOURCE_B', 2.0, 4.0, 2.0, 4.0)
    plan = _plan([outgoing, incoming], 4.0)
    assert compile_scene_ownership(plan, fps=30.0)['pass']
    plan['interaction_engine'] = {
        'physical_actions': [{
            'interaction_id': 'REL_GENERIC',
            'event_id': 'IN',
            'start_seconds': 2.0,
            'end_seconds': 2.1,
        }]
    }
    qa = scene_ownership_qa(plan, fps=30.0)
    assert not qa['pass'], qa
    assert qa['hidden_interaction_action_count'] == 1, qa
    assert 'SCENE_OWNERSHIP_HIDES_SEMANTIC_ACTION' in qa['failures'], qa


def _missing_ownership_metadata_is_behavior_neutral() -> None:
    event = _root('EVENT', 'ONLY_SOURCE', 0.0, 2.0, 0.1, 2.0)
    for t in (0.0, 0.05, 0.1, 0.5, 1.99, 2.0):
        assert _state(event, t) == _state(event, t, ignore_scene_ownership=True)


def _contracts_are_installed_on_public_import_paths() -> None:
    assert _interaction_director._scene_ownership_contract_installed
    assert _render_preview._scene_ownership_contract_installed
    assert 'scene_ownership_start_seconds' in _interaction_director._FINAL_TIMING_FIELDS
    assert 'scene_ownership_end_seconds' in _interaction_director._FINAL_TIMING_FIELDS


def main() -> None:
    _contracts_are_installed_on_public_import_paths()
    _ordinary_handoff_is_one_source_per_encoded_frame()
    _fractional_frame_boundary_does_not_round_past_its_own_frame()
    _protected_partition_releases_to_independent_root_without_mutation()
    _protected_handoff_fails_closed_for_non_independent_incoming_actor()
    _semantic_actions_cannot_be_hidden_by_pixel_ownership()
    _missing_ownership_metadata_is_behavior_neutral()
    print('V31_SCENE_OWNERSHIP_PASS')


if __name__ == '__main__':
    main()
