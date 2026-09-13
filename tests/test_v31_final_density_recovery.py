from __future__ import annotations

import copy
from unittest.mock import patch

import hexa_v31.planning.final_density_recovery as density

FPS = 30.0


def _plan():
    outgoing = {
        'event_id': 'OUT', 'scene_id': 'SCENE_A', 'visual_card_id': 'CARD_A',
        'render_mode': 'ROOT_ATOMIC', 'start_seconds': 8.0, 'end_seconds': 10.4,
        'physical_start_seconds': 8.0, 'physical_end_seconds': 10.4,
        'preset_exit': {'name': 'DISAPPEAR_DOWN_SCALE', 'start_seconds': 9.85, 'duration_seconds': 0.6},
    }
    incoming = {
        'event_id': 'IN', 'scene_id': 'SCENE_B', 'visual_card_id': 'CARD_A',
        'render_mode': 'ROOT_ATOMIC', 'partition_group_id': None,
        'start_seconds': 10.0, 'settle_seconds': 10.8, 'end_seconds': 12.0,
        'physical_start_seconds': 10.0, 'physical_end_seconds': 12.0,
        'visibility_interval_seconds': [10.0, 12.0],
        'preset_entry': {'name': 'APPEAR_HIGH_SCALE', 'start_seconds': 10.0, 'duration_seconds': 0.8},
        'preset_exit': None, 'preset_actions': [],
    }
    card = {'card_id': 'CARD_A', 'start_seconds': 9.5, 'end_seconds': 12.0}
    plan = {'events': [outgoing, incoming], 'visual_cards': {'cards': [card]}, 'fps': FPS}
    return plan, card, outgoing, incoming


def _fake_recompile(event):
    start = float((event.get('preset_entry') or {}).get('start_seconds', event.get('start_seconds', 0.0)))
    event['motion_intervals'] = []
    event['motion_start_seconds'] = start
    event['motion_end_seconds'] = float(event.get('physical_end_seconds', event.get('end_seconds', start)))


def _report_for_threshold(plan):
    incoming = next(row for row in plan['events'] if row['event_id'] == 'IN')
    hard = float(incoming['preset_entry']['start_seconds']) > 9.9 + 1e-6
    return {
        'cards': [{'card_id': 'CARD_A', 'hard_under_density': hard, 'near_blank_duration_seconds': 0.0}],
        'hard_under_density_cards': ['CARD_A'] if hard else [],
        'near_blank_duration_seconds': 0.0,
    }


def _success_is_bounded_and_qa_gated():
    plan, card, outgoing, incoming = _plan()
    original = copy.deepcopy(incoming)
    with (
        patch.object(density, '_recompile_event_motion', side_effect=_fake_recompile),
        patch.object(density, 'build_visual_density_report', side_effect=_report_for_threshold),
        patch('hexa_v31.composition_qa.composition_plan_qa', return_value={'pass': True, 'failures': []}),
    ):
        repair = density._try_bounded_source_overlap(plan, card, outgoing, incoming, FPS)
    assert repair is not None
    assert 1 <= repair['advance_frames'] <= 6
    assert repair['advance_frames'] == 3
    assert repair['authority'] == 'FINAL_DENSITY_BOUNDED_SOURCE_OVERLAP'
    assert incoming['preset_entry']['start_seconds'] < original['preset_entry']['start_seconds']
    assert incoming['final_density_overlap_advance_frames'] == 3
    assert incoming['final_density_recovery'] == 'BOUNDED_SOURCE_OVERLAP'


def _failed_candidate_restores_exact_event():
    plan, card, outgoing, incoming = _plan()
    original = copy.deepcopy(incoming)
    with (
        patch.object(density, '_recompile_event_motion', side_effect=_fake_recompile),
        patch.object(density, 'build_visual_density_report', side_effect=_report_for_threshold),
        patch('hexa_v31.composition_qa.composition_plan_qa', return_value={'pass': False, 'failures': ['TEST_REJECT']}),
    ):
        repair = density._try_bounded_source_overlap(plan, card, outgoing, incoming, FPS)
    assert repair is None
    assert incoming == original


def _ineligible_pair_is_immutable():
    plan, card, outgoing, incoming = _plan()
    incoming['scene_id'] = outgoing['scene_id']
    original = copy.deepcopy(incoming)
    repair = density._try_bounded_source_overlap(plan, card, outgoing, incoming, FPS)
    assert repair is None
    assert incoming == original


def main():
    _success_is_bounded_and_qa_gated()
    _failed_candidate_restores_exact_event()
    _ineligible_pair_is_immutable()
    print('V31_FINAL_DENSITY_RECOVERY_PASS')


if __name__ == '__main__':
    main()
