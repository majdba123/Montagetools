from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import patch

import hexa_v31.planning.final_certification_dynamic_collision_recovery_contract as legacy
import hexa_v31.planning.final_cross_scene_handoff_recovery_contract as cross
import hexa_v31.planning.recovery_integrity_contract as integrity
from hexa_v31.interaction import choreography
from hexa_v31.preset_authority import duration

FPS = 30.0


def _legacy_gate_stays_render_pending():
    original_shift = legacy._shift_incoming
    original_retire = legacy._retire_outgoing
    try:
        legacy._shift_incoming = lambda impl, incoming, delay, fps, max_sync: True
        legacy._retire_outgoing = lambda impl, state, outgoing, handoff_end, fps: True

        def base(events, cards, fps):
            if not any(event.get('final_certification_dynamic_recovery_authority') for event in events):
                raise ValueError('FINAL_PHYSICAL_CERTIFICATION_FAILED: VCARD_TEST@2.50s: motion-path overlap OUT x IN=0.050>0.015')
            return {'pass': True, 'repairs': []}

        impl = SimpleNamespace(_final_physical_certification=base)
        legacy.install(impl)
        events = [
            {'event_id': 'OUT', 'scene_id': 'S1', 'render_mode': 'ROOT_ATOMIC', 'attention_priority': 'PRIMARY', 'source_scene_start_seconds': 0.0, 'preset_exit': {'name': 'EXIT_MIDDLE_TO_LEFT'}},
            {'event_id': 'IN', 'scene_id': 'S2', 'render_mode': 'ROOT_ATOMIC', 'attention_priority': 'PRIMARY', 'source_scene_start_seconds': 2.0, 'preset_entry': {'name': 'ENTRY_RIGHT_TO_MIDDLE'}},
        ]
        result = impl._final_physical_certification(events, {'cards': []}, FPS)
        assert result['pass'] is True
        assert result['recovery_validation_state'] == 'CI_VERIFIED_RENDER_PENDING'
        assert result.get('recovery_validation_state') != 'PROVEN'
    finally:
        legacy._shift_incoming = original_shift
        legacy._retire_outgoing = original_retire


def _causal_retime_is_truthful():
    integrity._patch_choreography_truthfulness()
    dd = duration('APPEAR_HIGH_SCALE')
    event = {
        'event_id': 'REACTION', 'render_mode': 'ROOT_ATOMIC',
        'translation_safe_after_occlusion': False, 'animation_safe': False, 'scale_safe': True,
        'physical_start_seconds': 4.0, 'physical_end_seconds': 8.0,
        'start_seconds': 5.6725, 'end_seconds': 8.0,
        'preset_entry': {'name': 'APPEAR_HIGH_SCALE', 'start_seconds': 5.6725, 'duration_seconds': dd},
        'preset_exit': None, 'preset_actions': [],
        'perceptual_hit_seconds': 5.87, 'perceptual_hit_source': 'SOURCE_INTERVAL_FALLBACK',
    }
    intent = {'semantic_action': 'REACT', 'causal_direction': 'OBJECT_CAUSES_SUBJECT_REACTION'}
    fixed = choreography._retime_reaction_after_cause(copy.deepcopy(event), intent, FPS, 5.60)
    assert fixed and fixed.get('causal_order_already_satisfied') is True
    assert not fixed.get('retime_existing_entry')
    assert fixed['start_seconds'] == 5.6725
    moved = choreography._retime_reaction_after_cause(copy.deepcopy(event), intent, FPS, 5.80)
    assert moved and moved.get('retime_existing_entry') is True
    assert moved['start_seconds'] > moved['original_start_seconds']


class _CrossStub:
    _AUTHORITY = 'TEST_HANDOFF'
    @staticmethod
    def _is_independent_root(event): return True


class _RetireImpl:
    @staticmethod
    def preset_duration(name): return 0.6
    @staticmethod
    def _motion_interval_effective_fraction(kind, name): return 0.6
    @staticmethod
    def _compile_final_motion_intervals(event):
        row = event.get('preset_exit') or {}
        start = float(row.get('start_seconds', event['start_seconds']))
        dur = float(row.get('duration_seconds', 0.0))
        intervals = [{'kind': 'EXIT', 'name': row.get('name'), 'start_seconds': start, 'duration_seconds': dur, 'effective_start_seconds': start, 'effective_end_seconds': start + dur, 'effective_duration_seconds': dur}] if row else []
        return intervals, float(event['start_seconds']), max([float(event['end_seconds'])] + [x['effective_end_seconds'] for x in intervals])


def _retire_state(event, t):
    if float(event['physical_start_seconds']) <= t < float(event['physical_end_seconds']):
        return (0.5, 0.5, 1.0, 1.0)
    return None


def _handoff_preserves_only_preexisting_visibility():
    event = {
        'event_id': 'OUT', 'render_mode': 'ROOT_ATOMIC', 'start_seconds': 10.0, 'end_seconds': 15.0,
        'physical_start_seconds': 10.0, 'physical_end_seconds': 15.0,
        'perceptual_hit_seconds': 9.95, 'preset_actions': [],
        'preset_exit': {'name': 'DISAPPEAR_DOWN_SCALE', 'start_seconds': 14.64, 'duration_seconds': 0.6},
    }
    assert integrity._retire_outgoing_truthful(_CrossStub, _RetireImpl(), _retire_state, event, 14.0, FPS)
    assert event['physical_end_seconds'] == 14.0
    assert event['motion_end_seconds'] <= event['physical_end_seconds']
    assert any(row.get('clipped_by_final_source_handoff') for row in event['motion_intervals'])

    visible = copy.deepcopy(event)
    visible.update({'end_seconds': 15.0, 'physical_end_seconds': 15.0, 'perceptual_hit_seconds': 12.0})
    assert integrity._retire_outgoing_truthful(_CrossStub, _RetireImpl(), _retire_state, visible, 14.0, FPS)
    assert _retire_state(visible, 12.0)[2] > 0.22


def _failure(card, a, b, t=1.0):
    return {'card_id': card, 'time_seconds': t, 'event_a': a, 'event_b': b}


def _residual_recovery_is_strictly_monotonic():
    msg = 'FINAL_PHYSICAL_CERTIFICATION_FAILED: VCARD_A@1.00s: motion-path overlap A x B=0.10>0.015 | VCARD_B@2.00s: motion-path overlap C x D=0.10>0.015'

    def base(events, cards, fps):
        raise ValueError(msg)

    impl = SimpleNamespace(_final_physical_certification=base)
    impl._final_certification_dynamic_collision_recovery_base = base
    legacy.install(impl)
    first = _failure('VCARD_A', 'A', 'B', 1.0)
    second = _failure('VCARD_B', 'C', 'D', 2.0)
    state = {'remaining': 2}

    def canonical(events, cards, fps):
        if state['remaining'] == 2: return [copy.deepcopy(first), copy.deepcopy(second)], {'pass': False}
        if state['remaining'] == 1: return [copy.deepcopy(second)], {'pass': False}
        return [], {'pass': True}

    def cross_attempt(impl, events, cards, fps, failure, previous, cross_mod, base_fn):
        if failure['event_a'] == 'A':
            state['remaining'] = 1
            return 'MONOTONIC', [copy.deepcopy(second)], {'pass': False}, {'type': 'FIRST'}, ValueError('residual')
        state['remaining'] = 0
        return 'PASS', [], {'pass': True, 'repairs': []}, {'type': 'SECOND'}, None

    with patch.object(integrity, '_canonical_state', side_effect=canonical), patch.object(integrity, '_cross_scene_attempts', side_effect=cross_attempt), patch.object(integrity, '_same_scene_attempt', return_value=None), patch.object(cross, '_scene_id', return_value=''):
        integrity.install(impl)
        result = impl._final_physical_certification([{'event_id': 'A'}, {'event_id': 'B'}, {'event_id': 'C'}, {'event_id': 'D'}], {'cards': []}, FPS)
    assert result['pass'] is True
    meta = result['final_certification_residual_recovery']
    assert meta == {'authority': 'FINAL_CERTIFICATION_MONOTONIC_RESIDUAL_RECOVERY', 'initial_conflict_pair_count': 2, 'repair_count': 2, 'remaining_conflict_pair_count': 0}
    assert result['recovery_validation_state'] == 'CI_VERIFIED_RENDER_PENDING'


def main():
    _legacy_gate_stays_render_pending()
    _causal_retime_is_truthful()
    _handoff_preserves_only_preexisting_visibility()
    _residual_recovery_is_strictly_monotonic()
    # The final-density recovery is a separate production failure family, but this
    # existing early suite entry invokes its dedicated regression so CI cannot omit it.
    from test_v31_final_density_recovery import main as density_recovery_main
    density_recovery_main()
    print('V31_RECOVERY_VALIDATION_GATE_PASS')


if __name__ == '__main__':
    main()
