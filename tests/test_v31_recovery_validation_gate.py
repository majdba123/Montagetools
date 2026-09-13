from __future__ import annotations

from types import SimpleNamespace

import hexa_v31.planning.final_certification_dynamic_collision_recovery_contract as contract


def main():
    original_shift = contract._shift_incoming
    original_retire = contract._retire_outgoing
    try:
        contract._shift_incoming = lambda impl, incoming, delay, fps, max_sync: True
        contract._retire_outgoing = lambda impl, state, outgoing, handoff_end, fps: True

        def base(events, cards, fps):
            if not any(event.get('final_certification_dynamic_recovery_authority') for event in events):
                raise ValueError(
                    'FINAL_PHYSICAL_CERTIFICATION_FAILED: '
                    'VCARD_TEST@2.50s: motion-path overlap OUT x IN=0.050>0.015'
                )
            return {'pass': True, 'repairs': []}

        impl = SimpleNamespace(_final_physical_certification=base)
        contract.install(impl)
        events = [
            {
                'event_id': 'OUT',
                'scene_id': 'S1',
                'render_mode': 'ROOT_ATOMIC',
                'attention_priority': 'PRIMARY',
                'source_scene_start_seconds': 0.0,
                'preset_exit': {'name': 'EXIT_MIDDLE_TO_LEFT'},
            },
            {
                'event_id': 'IN',
                'scene_id': 'S2',
                'render_mode': 'ROOT_ATOMIC',
                'attention_priority': 'PRIMARY',
                'source_scene_start_seconds': 2.0,
                'preset_entry': {'name': 'ENTRY_RIGHT_TO_MIDDLE'},
            },
        ]
        result = impl._final_physical_certification(events, {'cards': []}, 30.0)
        assert result['pass'] is True
        assert result['recovery_problem_id'] == 'HEXA_MOTION_PATH_OVERLAP'
        assert result['recovery_validation_state'] == 'CI_VERIFIED_RENDER_PENDING'
        repairs = [
            row for row in result['repairs']
            if row.get('type') == 'FINAL_CERTIFICATION_DYNAMIC_CROSS_SCENE_HANDOFF'
        ]
        assert len(repairs) == 1
        repair = repairs[0]
        assert repair['problem_id'] == 'HEXA_MOTION_PATH_OVERLAP'
        assert repair['problem_source'] == 'CI'
        assert repair['recovery_validation_state'] == 'CI_VERIFIED_RENDER_PENDING'
        assert repair.get('recovery_validation_state') != 'PROVEN'
        assert repair['outgoing_event_id'] == 'OUT'
        assert repair['incoming_event_id'] == 'IN'

        print('V31_RECOVERY_VALIDATION_GATE_PASS')
    finally:
        contract._shift_incoming = original_shift
        contract._retire_outgoing = original_retire


if __name__ == '__main__':
    main()
