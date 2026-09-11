from __future__ import annotations

from hexa_v31.editorial_runtime import apply_editorial_runtime_state, promote_text_plan


def _event(*, archetype='GENERIC', beat='ESTABLISH', focus='A', event_id='A', role='LEAD', render_mode='ROOT_ATOMIC'):
    return {
        'event_id': event_id,
        'scene_id': 'SCENE_001',
        'visual_card_id': 'CARD_001',
        'render_mode': render_mode,
        'sequence_width': 1920.0,
        'sequence_height': 1080.0,
        'object_rest_position_px': [960.0, 540.0],
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 6.0,
        'composition_states': [{
            'state_id': f'S1::{event_id}',
            'start_seconds': 0.0,
            'transition_duration_seconds': 0.36,
            'semantic_beat': beat,
            'center_norm': [0.5, 0.5],
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'role': role,
            'focus_event_id': focus,
            'participating_event_ids': ['A', 'B'],
            'layout_archetype': archetype,
            'state_reason': 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY',
        }],
    }


def test_establish_focus_is_materially_centered_and_enlarged():
    event = _event(beat='ESTABLISH')
    state = apply_editorial_runtime_state(event, 1.0, ((700.0, 540.0), 1.0, 1.0))
    assert state is not None
    (x, y), scale, opacity = state
    assert abs(x - 960.0) < 5.0
    assert abs(y - 550.8) < 12.0
    assert scale >= 1.09
    assert opacity >= 0.94


def test_comparison_terms_do_not_collapse_to_same_center():
    a = _event(archetype='COMPARISON', beat='COMPARE_REVEAL', focus='B', event_id='A')
    b = _event(archetype='COMPARISON', beat='COMPARE_REVEAL', focus='B', event_id='B')
    a_state = apply_editorial_runtime_state(a, 1.0, ((960.0, 540.0), 1.0, 1.0))
    b_state = apply_editorial_runtime_state(b, 1.0, ((960.0, 540.0), 1.0, 1.0))
    assert a_state and b_state
    assert abs(a_state[0][0] - b_state[0][0]) > 500.0
    assert b_state[1] > a_state[1]


def test_process_has_directional_spatial_progression():
    a = _event(archetype='FLOW_PIPELINE', beat='PROCESS_ADVANCE', focus='B', event_id='A')
    b = _event(archetype='FLOW_PIPELINE', beat='PROCESS_ADVANCE', focus='B', event_id='B')
    a_state = apply_editorial_runtime_state(a, 1.0, ((960.0, 540.0), 1.0, 1.0))
    b_state = apply_editorial_runtime_state(b, 1.0, ((960.0, 540.0), 1.0, 1.0))
    assert a_state and b_state
    assert a_state[0][0] < b_state[0][0]
    assert abs(a_state[0][1] - b_state[0][1]) > 40.0


def test_result_payoff_becomes_dominant_center_event():
    result = _event(archetype='RESULT_PAYOFF', beat='PAYOFF', focus='B', event_id='B', role='RESULT')
    context = _event(archetype='RESULT_PAYOFF', beat='PAYOFF', focus='B', event_id='A', role='SUPPORT')
    r = apply_editorial_runtime_state(result, 1.0, ((960.0, 540.0), 1.0, 1.0))
    c = apply_editorial_runtime_state(context, 1.0, ((960.0, 540.0), 1.0, 1.0))
    assert r and c
    assert abs(r[0][0] - 960.0) < 8.0
    assert r[1] >= 1.20
    assert c[1] <= 0.75


def test_presenter_is_demoted_when_not_semantic_focus():
    presenter = _event(archetype='CHARACTER_EXPLAINS_OBJECT', beat='SUPPORT_REVEAL', focus='B', event_id='A', role='NARRATOR')
    state = apply_editorial_runtime_state(presenter, 1.0, ((960.0, 540.0), 1.0, 1.0))
    assert state
    (x, y), scale, _ = state
    assert abs(x - 960.0) > 350.0
    assert y > 640.0
    assert scale <= 0.72


def test_established_actor_never_becomes_pale_ghost_mid_phase():
    event = _event(archetype='COMPARISON', beat='COMPARE_REVEAL')
    state = apply_editorial_runtime_state(event, 2.0, ((960.0, 540.0), 1.0, 0.22))
    assert state
    assert state[2] >= 0.94


def test_partition_and_residual_carriers_are_untouched():
    original = ((700.0, 400.0), 0.83, 0.41)
    for mode in ('CHILD_PARTITION', 'RESIDUAL_SUPPORT'):
        event = _event(render_mode=mode)
        assert apply_editorial_runtime_state(event, 1.0, original) == original


def test_react_authority_is_untouched():
    event = _event()
    event['semantic_intent'] = 'REACT'
    original = ((700.0, 400.0), 0.83, 0.41)
    assert apply_editorial_runtime_state(event, 1.0, original) == original


def test_runtime_is_deterministic():
    event = _event(archetype='QUESTION_ANSWER', beat='SUPPORT_REVEAL', focus='B', event_id='A')
    original = ((960.0, 540.0), 1.0, 1.0)
    assert apply_editorial_runtime_state(event, 1.25, original) == apply_editorial_runtime_state(event, 1.25, original)


def test_semantic_roles_produce_pixel_distinct_text_motion_profiles():
    text_plan = {'events': [
        {'event_id': 'T1', 'semantic_role': 'RESULT', 'start_seconds': 0.0, 'end_seconds': 2.0},
        {'event_id': 'T2', 'semantic_role': 'WARNING', 'start_seconds': 0.0, 'end_seconds': 2.0},
        {'event_id': 'T3', 'semantic_role': 'MICRO_LABEL', 'start_seconds': 0.0, 'end_seconds': 2.0},
    ]}
    promoted = promote_text_plan(text_plan, {})
    rows = promoted['events']
    signatures = {(row['pop_scale_from'], row['pop_scale_peak'], row['slide_dx_norm'], row['slide_dy_norm']) for row in rows}
    assert len(signatures) == 3
    assert all(row['editorial_typography_runtime_authority'] == 'SEMANTIC_ROLE_MOTION_GRAPHICS_V1' for row in rows)
