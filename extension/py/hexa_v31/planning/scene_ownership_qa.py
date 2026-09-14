from __future__ import annotations

from collections import defaultdict

from hexa_v31.planning.scene_ownership import (
    _AUTHORITY,
    _active,
    _frame_ceil,
    _frame_floor,
    _frame_time,
    _is_partition,
    _material_frames,
    _partition_carrier_end,
    _partition_carrier_start,
    _physical_end,
    _physical_start,
    _scene_id,
)

def scene_ownership_qa(plan: dict, fps: float = 30.0) -> dict:
    """Fail closed on mixed pixels, handoff gaps, protected truncation or hidden actions."""
    from hexa_v31.composition_qa import _state

    fps = max(1.0, float(fps or plan.get('fps') or 30.0))
    events = _active(list(plan.get('events') or []))
    by_scene = defaultdict(list)
    for event in events:
        if _scene_id(event):
            by_scene[_scene_id(event)].append(event)
    rows = []
    failures = []
    mixed_frames = []
    uncovered_handoffs = []

    compiler = plan.get('scene_ownership_compiler') or {}
    failures.extend(compiler.get('failures') or [])

    for handoff in compiler.get('handoffs') or []:
        frame = int(handoff['frame'])
        outgoing_sid = str(handoff['outgoing_scene_id'])
        incoming_sid = str(handoff['incoming_scene_id'])
        prev_t = _frame_time(max(0, frame - 1), fps)
        next_t = _frame_time(frame, fps)
        prev_visible = any((state := _state(e, prev_t)) is not None and float(state[2]) > 0.05
                           for e in by_scene.get(outgoing_sid, []))
        next_visible = any((state := _state(e, next_t)) is not None and float(state[2]) > 0.05
                           for e in by_scene.get(incoming_sid, []))
        if not (prev_visible and next_visible):
            uncovered_handoffs.append({**handoff, 'outgoing_visible_previous_frame': prev_visible,
                                        'incoming_visible_handoff_frame': next_visible})

    if events:
        first = min(_frame_floor(float(e.get('scene_ownership_start_seconds', _physical_start(e))), fps) for e in events)
        last = max(_frame_ceil(float(e.get('scene_ownership_end_seconds', _physical_end(e))), fps) for e in events)
        for frame in range(first, last + 1):
            t = _frame_time(frame, fps)
            scenes = sorted({
                _scene_id(event)
                for event in events
                if _scene_id(event)
                and (state := _state(event, t)) is not None
                and float(state[2]) > 0.05
            })
            if len(scenes) > 1:
                mixed_frames.append({'frame': frame, 'time_seconds': round(t, 6), 'scene_ids': scenes})

    # Protected Foundation physical/carrier metadata is immutable. Pixel ownership
    # must contain every frame on which the protected source is materially visible;
    # invisible pre-roll/tails do not force a hybrid-scene frame.
    groups = defaultdict(list)
    for event in events:
        if _is_partition(event):
            groups[(_scene_id(event), str(event.get('partition_root_id') or event.get('root_id') or ''))].append(event)
    protected_rows = []
    for (sid, root), members in groups.items():
        carrier_start = min(_partition_carrier_start(e) for e in members)
        carrier_end = max(_partition_carrier_end(e) for e in members)
        owner_start = min(float(e.get('scene_ownership_start_seconds', _physical_start(e))) for e in members)
        owner_end = max(float(e.get('scene_ownership_end_seconds', _physical_end(e))) for e in members)
        raw_material = _material_frames(members, fps, ignore_scene_ownership=True)
        material_start = _frame_time(min(raw_material), fps) if raw_material else None
        material_end = _frame_time(max(raw_material) + 1, fps) if raw_material else None
        material_preserved = (
            material_start is None
            or (owner_start <= material_start + 1e-6 and owner_end >= material_end - 1e-6)
        )
        collective_physical = (
            len({_physical_start(e) for e in members}) == 1
            and len({_physical_end(e) for e in members}) == 1
            and len({_partition_carrier_start(e) for e in members}) == 1
            and len({_partition_carrier_end(e) for e in members}) == 1
        )
        valid = bool(material_preserved and collective_physical)
        if not valid:
            failures.append(f'{sid}:{root}: scene ownership corrupts protected partition source survival')
        protected_rows.append({
            'scene_id': sid, 'partition_root_id': root,
            'carrier_start_seconds': round(carrier_start, 6),
            'carrier_end_seconds': round(carrier_end, 6),
            'material_start_seconds': round(material_start, 6) if material_start is not None else None,
            'material_end_seconds': round(material_end, 6) if material_end is not None else None,
            'ownership_start_seconds': round(owner_start, 6),
            'ownership_end_seconds': round(owner_end, 6),
            'collective_physical_lifetime_pass': collective_physical,
            'material_source_survival_pass': material_preserved,
            'pass': valid,
        })

    # Interaction actions are semantic evidence and may not be silently hidden by the
    # pixel ownership gate. Optional entry/exit pre-roll may be clipped, semantic actions may not.
    by_id = {str(event.get('event_id') or ''): event for event in events}
    hidden_actions = []
    for action in (plan.get('interaction_engine') or {}).get('physical_actions') or []:
        event = by_id.get(str(action.get('event_id') or ''))
        if event is None:
            continue
        owner_start = float(event.get('scene_ownership_start_seconds', _physical_start(event)))
        owner_end = float(event.get('scene_ownership_end_seconds', _physical_end(event)))
        start = float(action.get('start_seconds', 0.0)); end = float(action.get('end_seconds', start))
        if start < owner_start - 1e-6 or end > owner_end + 1e-6:
            hidden_actions.append({'interaction_id': action.get('interaction_id'), 'event_id': action.get('event_id'),
                                   'start_seconds': start, 'end_seconds': end,
                                   'ownership_start_seconds': owner_start, 'ownership_end_seconds': owner_end})
    if mixed_frames:
        failures.append('SCENE_OWNERSHIP_MIXED_SOURCE_PIXELS')
    if uncovered_handoffs:
        failures.append('SCENE_OWNERSHIP_HANDOFF_GAP')
    if hidden_actions:
        failures.append('SCENE_OWNERSHIP_HIDES_SEMANTIC_ACTION')

    rows.extend(compiler.get('handoffs') or [])
    return {
        'schema': 'HEXA_V31_SCENE_OWNERSHIP_QA',
        'version': '31.0.25',
        'authority': _AUTHORITY,
        'pass': not failures,
        'failures': failures,
        'handoffs': rows,
        'mixed_frame_count': len(mixed_frames),
        'mixed_frames': mixed_frames[:24],
        'uncovered_handoff_count': len(uncovered_handoffs),
        'uncovered_handoffs': uncovered_handoffs,
        'hidden_interaction_action_count': len(hidden_actions),
        'hidden_interaction_actions': hidden_actions,
        'protected_partition_groups': protected_rows,
        'protected_root_recoveries': compiler.get('protected_root_recoveries') or [],
    }
