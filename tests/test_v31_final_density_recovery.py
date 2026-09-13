from __future__ import annotations

import copy
from unittest.mock import patch

import hexa_v31.planning.final_density_recovery as density

FPS = 30.0


def _plan(source='SOURCE_INTERVAL_FALLBACK', anchor=10.65):
    outgoing = {
        'event_id': 'OUT', 'scene_id': 'SCENE_A', 'visual_card_id': 'CARD_A',
        'render_mode': 'ROOT_ATOMIC', 'start_seconds': 8.0, 'end_seconds': 10.4,
        'physical_start_seconds': 8.0, 'physical_end_seconds': 10.4,
        'preset_exit': {'name': 'DISAPPEAR_DOWN_SCALE', 'start_seconds': 9.85, 'duration_seconds': 0.6},
    }
    incoming = {
        'event_id': 'IN', 'scene_id': 'SCENE_B', 'visual_card_id': 'CARD_A',
        'render_mode': 'ROOT_ATOMIC', 'partition_group_id': None,
        'start_seconds': 10.1, 'settle_seconds': 10.9, 'end_seconds': 12.0,
        'physical_start_seconds': 10.0, 'physical_end_seconds': 12.0,
        'visibility_interval_seconds': [10.0, 12.0],
        'perceptual_hit_seconds': anchor, 'perceptual_hit_source': source,
        'preset_entry': {'name': 'APPEAR_HIGH_SCALE', 'start_seconds': 10.1, 'duration_seconds': 0.8},
        'preset_exit': None, 'preset_actions': [],
    }
    card = {'card_id': 'CARD_A', 'start_seconds': 9.5, 'end_seconds': 12.0}
    return {'events': [outgoing, incoming], 'visual_cards': {'cards': [card]}, 'fps': FPS}


def _entry_advance_is_bounded_and_truthful():
    plan = _plan()
    incoming = plan['events'][1]
    assert density._advance_incoming_entry(plan, 'IN', 6, FPS)
    assert incoming['preset_entry']['start_seconds'] == 10.0
    assert incoming['start_seconds'] == 10.0
    assert incoming['settle_seconds'] == 10.8
    assert incoming['final_density_overlap_advance_requested_frames'] == 6
    assert incoming['final_density_overlap_advance_frames'] == 3.0
    assert incoming['final_density_overlap_advance_seconds'] == 0.1
    assert incoming['final_density_recovery'] == 'BOUNDED_ENTRY_ADVANCE'


def _voice_anchor_budget_is_fail_closed():
    plan = _plan(source='VOICE_TRIGGER', anchor=11.0)
    original = copy.deepcopy(plan)
    assert not density._advance_incoming_entry(plan, 'IN', 6, FPS)
    assert plan == original


def _final_state_gate_is_mandatory():
    plan = _plan()
    metric_calls = {'count': 0}
    def metric(candidate, card_id):
        metric_calls['count'] += 1
        if metric_calls['count'] > 1:
            assert candidate.get('finalized') is True
        return {'hard_under_density': False}
    def finalize(candidate, fps=30.0):
        candidate['finalized'] = True
        return candidate
    with (
        patch.object(density, '_metric', side_effect=metric),
        patch.object(density, 'composition_plan_qa', return_value={'pass': True, 'failures': []}),
        patch('hexa_v31.interaction.director.finalize_interaction_motion_plan', side_effect=finalize),
    ):
        assert density._candidate_passes_final_state(plan, 'CARD_A', FPS)
    assert metric_calls['count'] == 2


def _refinalized_density_regression_is_rejected():
    plan = _plan()
    def metric(candidate, card_id):
        return {'hard_under_density': bool(candidate.get('finalized'))}
    def finalize(candidate, fps=30.0):
        candidate['finalized'] = True
        return candidate
    with (
        patch.object(density, '_metric', side_effect=metric),
        patch.object(density, 'composition_plan_qa', return_value={'pass': True, 'failures': []}),
        patch('hexa_v31.interaction.director.finalize_interaction_motion_plan', side_effect=finalize),
    ):
        assert not density._candidate_passes_final_state(plan, 'CARD_A', FPS)


def _hard_card_prefers_entry_advance_before_hold():
    plan = _plan()
    def advance(candidate, event_id, frames, fps):
        if frames < 2:
            return False
        event = next(row for row in candidate['events'] if row['event_id'] == event_id)
        event['final_density_overlap_advance_frames'] = 1.8
        event['final_density_overlap_advance_seconds'] = 0.06
        return True
    with (
        patch.object(density, '_advance_incoming_entry', side_effect=advance),
        patch.object(density, '_candidate_passes_final_state', return_value=True),
        patch.object(density, '_apply_hold', side_effect=AssertionError('hold must not run after entry success')),
    ):
        repair = density._recover_hard_card(plan, 'CARD_A', FPS)
    assert repair['strategy'] == 'BOUNDED_ENTRY_ADVANCE'
    assert repair['requested_frames'] == 2
    assert repair['advance_frames'] == 1.8
    assert repair['advance_seconds'] == 0.06


def _hold_is_fallback_not_first_choice():
    plan = _plan()
    def hold(candidate, event_id, card_id, frames, fps):
        return frames >= 2
    with (
        patch.object(density, '_advance_incoming_entry', return_value=False),
        patch.object(density, '_apply_hold', side_effect=hold),
        patch.object(density, '_candidate_passes_final_state', return_value=True),
    ):
        repair = density._recover_hard_card(plan, 'CARD_A', FPS)
    assert repair['strategy'] == 'BOUNDED_OUTGOING_HOLD'
    assert repair['hold_frames'] == 2


def main():
    _entry_advance_is_bounded_and_truthful()
    _voice_anchor_budget_is_fail_closed()
    _final_state_gate_is_mandatory()
    _refinalized_density_regression_is_rejected()
    _hard_card_prefers_entry_advance_before_hold()
    _hold_is_fallback_not_first_choice()
    print('V31_FINAL_DENSITY_RECOVERY_PASS')


if __name__ == '__main__':
    main()
