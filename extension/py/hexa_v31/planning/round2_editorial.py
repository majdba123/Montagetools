"""Round 2 editorial delivery corrections.

Generic compatibility overlay for the production planner. It does not inspect project,
scene, narration, or package identifiers. Decisions use semantic phase metadata,
physical safety flags, geometry, and installed preset durations only.
"""
from __future__ import annotations

import copy


def _explicit_react_semantics(event: dict) -> bool:
    explicit = {
        str(event.get('semantic_intent') or '').strip().upper(),
        str(event.get('relationship') or '').strip().upper(),
        str(event.get('interaction_action') or '').strip().upper(),
        str(event.get('semantic_action') or '').strip().upper(),
    }
    return bool(explicit.intersection({'REACT', 'REACTION', 'RESPOND'}))


def install(impl) -> None:
    if getattr(impl, '_round2_editorial_installed', False):
        return

    base_history_variant = impl._apply_composition_history_variant
    base_optical_scale = impl._optical_scale_optimize
    base_schedule = impl._schedule_event

    def apply_composition_history_variant(layout, grammar, history):
        variant = base_history_variant(layout, grammar, history)
        if variant != 'MIRRORED':
            return variant
        for phase in (layout.get('phase_placements') or {}).values():
            for placement in (phase or {}).values():
                center = list(placement.get('center_norm') or [])
                rect = list(placement.get('rect_norm') or [])
                if len(center) >= 2:
                    center[0] = round(1.0 - float(center[0]), 6)
                    placement['center_norm'] = center
                if len(rect) == 4:
                    rect[0] = round(1.0 - float(rect[0]) - float(rect[2]), 6)
                    placement['rect_norm'] = rect
        return variant

    def commit_editorial_phase_geometry(events, card, phase_plan, layout):
        phase_placements = layout.get('phase_placements') or {}
        by_id = {str(event.get('event_id')): event for event in events}
        for event in events:
            for container in ('composition_states', 'composition_participant_states'):
                kept = [state for state in (event.get(container) or []) if state.get('state_reason') != 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY']
                if kept:
                    event[container] = kept
                else:
                    event.pop(container, None)
        previous_state = {}
        phases = list(phase_plan.get('phases') or [])
        for index, phase in enumerate(phases):
            phase_id = str(phase.get('phase_id'))
            placements = phase_placements.get(phase_id) or {}
            start = float(phase.get('start_seconds', card.get('start_seconds', 0)))
            end = float(phase.get('end_seconds', start))
            duration = max(0.0, end - start)
            transition = 0.0 if index == 0 else min(.52, max(.26, duration * .22))
            for event_id, placement in placements.items():
                event = by_id.get(str(event_id))
                if event is None:
                    continue
                base = (layout.get('placements') or {}).get(str(event_id)) or placement
                scale = float(placement['scale']) / max(1e-9, float(base['scale']))
                state_id = f'{phase_id}::{event_id}::EDITORIAL_GEOMETRY'
                state = {
                    'state_id': state_id,
                    'scene_id': event.get('scene_id'),
                    'card_id': card.get('card_id'),
                    'semantic_beat': phase.get('semantic_beat'),
                    'start_seconds': round(start, 6),
                    'transition_duration_seconds': round(transition, 6),
                    'center_norm': list(placement['center_norm']),
                    'scale_multiplier': round(scale, 6),
                    'visibility': 1.0,
                    'role': placement.get('role'),
                    'focus_event_id': phase.get('focus_event_id'),
                    'participating_event_ids': list(phase.get('event_ids') or []),
                    'layout_archetype': phase.get('editorial_archetype') or (card.get('universal_scene_grammar') or {}).get('archetype'),
                    'state_reason': 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY',
                    'translation_safe': bool(event.get('translation_safe_after_occlusion', event.get('animation_safe', True))),
                }
                if str(event_id) in previous_state:
                    state['previous_state_id'] = previous_state[str(event_id)]
                container = 'composition_states' if str(event_id) == str(phase.get('focus_event_id')) else 'composition_participant_states'
                event.setdefault(container, []).append(state)
                event['editorial_phase_geometry_authority'] = 'SEMANTIC_ARCHETYPE_TEMPORAL_TOPOLOGY_V2'
                previous_state[str(event_id)] = state_id
                if len(placements) == 1 and scale > 1.001 and index < len(phases) - 1:
                    handoff_duration = min(.46, max(.26, duration * .20))
                    handoff_id = f'{phase_id}::{event_id}::HANDOFF_GEOMETRY'
                    handoff = dict(state, state_id=handoff_id, semantic_beat='HANDOFF_GEOMETRY', start_seconds=round(end - handoff_duration, 6), transition_duration_seconds=round(handoff_duration, 6), center_norm=list(base['center_norm']), scale_multiplier=1.0, previous_state_id=state_id)
                    event.setdefault('composition_states', []).append(handoff)
                    previous_state[str(event_id)] = handoff_id

    def optical_scale_optimize(events, cards, fps):
        protected = {
            str(event.get('event_id')): {key: copy.deepcopy(event.get(key)) for key in ('layout_scale_multiplier', 'planned_rect_norm', 'collision_envelope_rect_norm', 'premium_optical_scale_factor')}
            for event in events if event.get('editorial_phase_geometry_authority')
        }
        result = base_optical_scale(events, cards, fps)
        for event in events:
            snapshot = protected.get(str(event.get('event_id')))
            if snapshot is None:
                continue
            for key, value in snapshot.items():
                if value is None:
                    event.pop(key, None)
                else:
                    event[key] = value
            event['late_optical_scaling_blocked'] = 'PHASE_OWNED_GEOMETRY'
        if protected:
            result = dict(result)
            result['phase_owned_events_restored'] = len(protected)
        return result

    def _phase_state_for_start(event, phase_start):
        states = list(event.get('composition_states') or []) + list(event.get('composition_participant_states') or [])
        states = [s for s in states if s.get('state_reason') == 'SEMANTIC_ARCHETYPE_PHASE_GEOMETRY']
        if not states:
            return None
        return min(states, key=lambda s: abs(float(s.get('start_seconds', phase_start)) - float(phase_start)))

    def schedule_event(event, phase_window, card, index, total, **kwargs):
        base_schedule(event, phase_window, card, index, total, **kwargs)
        ps, pe = map(float, phase_window)
        duration = max(0.0, pe - ps)
        state = _phase_state_for_start(event, ps)
        beat = str((state or {}).get('semantic_beat') or '').upper()
        establish = beat in {'ESTABLISH', 'PROCESS_ESTABLISH', 'CONTEXT_ESTABLISH', 'BEFORE_ESTABLISH'}
        appearance_duration = float(impl.preset_duration('APPEAR_HIGH_SCALE'))
        if not establish or duration >= appearance_duration + .10 or _explicit_react_semantics(event):
            return
        if str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC' or event.get('partition_group_id'):
            return
        event['preset_entry'] = None
        event['preset_exit'] = None
        event['preset_actions'] = []
        event['appearance_method'] = 'READABLE_ESTABLISH'
        event['disappearance_method'] = 'SEMANTIC_HANDOFF'
        event['position_animated'] = False
        event['entry_direction'] = None
        event['start_seconds'] = round(ps, 6)
        event['settle_seconds'] = round(ps, 6)
        event['end_seconds'] = round(pe, 6)
        event['physical_start_seconds'] = round(ps, 6)
        event['physical_end_seconds'] = round(pe, 6)
        event['motion_start_seconds'] = round(ps, 6)
        event['motion_end_seconds'] = round(pe, 6)
        event['motion_intervals'] = []
        event['visual_impact_seconds'] = round(ps, 6)
        event['semantic_readable_not_before_seconds'] = round(ps, 6)
        event['pre_roll_duration_seconds'] = 0.0
        event['pre_roll_visibility_contract'] = 'IMMEDIATE_SOURCE_READABILITY'
        event['short_readable_establish'] = True

    impl._apply_composition_history_variant = apply_composition_history_variant
    impl._commit_editorial_phase_geometry = commit_editorial_phase_geometry
    impl._optical_scale_optimize = optical_scale_optimize
    impl._schedule_event = schedule_event
    impl._round2_editorial_installed = True
