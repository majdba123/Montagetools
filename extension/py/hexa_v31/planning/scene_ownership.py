from __future__ import annotations

import math
from collections import defaultdict

_AUTHORITY = 'GLOBAL_FRAME_SOURCE_SCENE_PIXEL_OWNERSHIP'
_PROTECTED_HANDOFF_AUTHORITY = 'PROTECTED_PARTITION_TO_INDEPENDENT_ROOT_OWNERSHIP_HANDOFF'
_EPS = 1e-9


def _active(events):
    return [event for event in events if not event.get('suppressed_by_card_density')]


def _scene_id(event):
    return str(event.get('scene_id') or '')


def _is_partition(event):
    return str(event.get('render_mode') or '').upper() in {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'}


def _is_independent_root(event):
    return (
        str(event.get('render_mode') or 'ROOT_ATOMIC').upper() == 'ROOT_ATOMIC'
        and not event.get('partition_group_id')
    )


def _source_start(event):
    return float(event.get('source_scene_start_seconds', event.get('start_seconds', 0.0)))


def _source_end(event):
    return float(event.get('source_scene_end_seconds', event.get('end_seconds', _source_start(event))))


def _physical_start(event):
    return float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))


def _physical_end(event):
    return float(event.get('physical_end_seconds', event.get('end_seconds', _physical_start(event))))


def _partition_carrier_start(event):
    return float(event.get('partition_carrier_start_seconds', _physical_start(event)))


def _partition_carrier_end(event):
    return float(event.get('partition_carrier_end_seconds', _physical_end(event)))


def _frame_floor(value, fps):
    return int(math.floor(float(value) * float(fps) + _EPS))


def _frame_ceil(value, fps):
    return int(math.ceil(float(value) * float(fps) - _EPS))


def _frame_time(frame, fps):
    return float(frame) / max(1.0, float(fps))


def _material_frames(events, fps, *, ignore_scene_ownership):
    from hexa_v31.composition_qa import _state

    if not events:
        return []
    first = min(_frame_floor(min(_source_start(e), _physical_start(e), float(e.get('start_seconds', 0.0))), fps)
                for e in events)
    last = max(_frame_ceil(max(_source_end(e), _physical_end(e), float(e.get('end_seconds', 0.0))), fps)
               for e in events)
    frames = []
    for frame in range(first, last + 1):
        t = _frame_time(frame, fps)
        if any(
            (state := _state(event, t, ignore_scene_ownership=ignore_scene_ownership)) is not None
            and float(state[2]) > 0.05
            for event in events
        ):
            frames.append(frame)
    return frames


def _raw_scene_pair_conflicts(events, fps):
    from hexa_v31.composition_qa import _state

    if not events:
        return set()
    first = min(_frame_floor(min(_source_start(e), _physical_start(e)), fps) for e in events)
    last = max(_frame_ceil(max(_source_end(e), _physical_end(e)), fps) for e in events)
    pairs = set()
    for frame in range(first, last + 1):
        t = _frame_time(frame, fps)
        scenes = sorted({
            _scene_id(event)
            for event in events
            if _scene_id(event)
            and (state := _state(event, t, ignore_scene_ownership=True)) is not None
            and float(state[2]) > 0.05
        })
        for index, scene_a in enumerate(scenes):
            for scene_b in scenes[index + 1:]:
                pairs.add((scene_a, scene_b))
    return pairs


def compile_scene_ownership(plan: dict, fps: float = 30.0) -> dict:
    """Compile one source-scene pixel owner per encoded frame without retiming semantics.

    Source-scene ownership is deliberately independent from physical/source survival and
    semantic action timing.  The renderer may withhold an incoming scene's optional
    pre-roll until the outgoing scene releases ownership, but this function never moves
    ``start_seconds``, presets, interaction actions, or protected partition lifetimes.

    When an outgoing certified Foundation partition survives beyond the next scene's
    materially-visible pre-roll, the boundary is delayed to the partition carrier end.
    That recovery is legal only when the prematurely-visible incoming actors are
    independent roots; protected source pixels themselves are never shortened.
    """
    fps = max(1.0, float(fps or plan.get('fps') or 30.0))
    events = _active(list(plan.get('events') or []))
    by_scene = defaultdict(list)
    for event in events:
        sid = _scene_id(event)
        if sid:
            by_scene[sid].append(event)

    if not by_scene:
        report = {'authority': _AUTHORITY, 'pass': True, 'scene_count': 0, 'handoffs': [],
                  'protected_root_recoveries': [], 'raw_mixed_scene_pairs': [],
                  'final_mixed_scene_pairs': []}
        plan['scene_ownership_compiler'] = report
        return report

    # Clear stale ownership before measuring the truthful authored/render state.
    for event in events:
        for key in ('scene_ownership_start_seconds', 'scene_ownership_end_seconds',
                    'scene_ownership_authority', 'scene_ownership_index',
                    'scene_ownership_recovery_authority'):
            event.pop(key, None)

    raw_pairs = _raw_scene_pair_conflicts(events, fps)
    scene_rows = []
    for sid, members in by_scene.items():
        source_start = min(_source_start(event) for event in members)
        source_end = max(_source_end(event) for event in members)
        material = _material_frames(members, fps, ignore_scene_ownership=True)
        first_material = min(material) if material else _frame_ceil(source_start, fps)
        last_material = max(material) if material else max(first_material, _frame_floor(source_end, fps))
        protected = [event for event in members if _is_partition(event)]
        protected_material = _material_frames(protected, fps, ignore_scene_ownership=True) if protected else []
        protected_start = min((_partition_carrier_start(event) for event in protected), default=None)
        protected_end = max((_partition_carrier_end(event) for event in protected), default=None)
        scene_rows.append({
            'scene_id': sid,
            'members': members,
            'source_start': source_start,
            'source_end': source_end,
            'first_material_frame': first_material,
            'last_material_frame': last_material,
            'protected_start': protected_start,
            'protected_end': protected_end,
            'protected_first_material_frame': min(protected_material) if protected_material else None,
            'protected_last_material_frame': max(protected_material) if protected_material else None,
        })
    scene_rows.sort(key=lambda row: (row['source_start'], row['source_end'], row['scene_id']))

    # Scene windows are contiguous on the encoded frame grid. The ordinary
    # handoff cannot begin before the source scene itself begins, and it waits for
    # the incoming scene's first materially-visible frame so we never manufacture a
    # pre-semantic entry just to cover a cut. A materially-visible protected outgoing
    # partition may push the cut later. That changes only pixel ownership of the
    # incoming independent ROOT pre-roll; semantic/action timing stays untouched.
    boundaries = []
    recoveries = []
    failures = []
    for outgoing, incoming in zip(scene_rows, scene_rows[1:]):
        source_boundary_frame = _frame_ceil(incoming['source_start'], fps)
        boundary_frame = max(int(source_boundary_frame), int(incoming['first_material_frame']))
        reason = ('INCOMING_FIRST_MATERIAL_FRAME'
                  if boundary_frame > source_boundary_frame else 'SOURCE_SCENE_BOUNDARY')

        # Preserve all materially-visible pixels of a certified outgoing Foundation
        # partition. The raw physical/carrier fields themselves are never edited.
        protected_last = outgoing.get('protected_last_material_frame')
        if protected_last is not None:
            protected_release_frame = int(protected_last) + 1
            if protected_release_frame > boundary_frame:
                from hexa_v31.composition_qa import _state
                early = []
                for event in incoming['members']:
                    visible = any(
                        (state := _state(event, _frame_time(frame, fps), ignore_scene_ownership=True)) is not None
                        and float(state[2]) > 0.05
                        for frame in range(boundary_frame, protected_release_frame)
                    )
                    if visible:
                        early.append(event)
                illegal = [event for event in early if not _is_independent_root(event)]
                if illegal:
                    failures.append(
                        f"{outgoing['scene_id']}->{incoming['scene_id']}: protected partition handoff "
                        f"would suppress non-independent incoming actors "
                        f"{[str(e.get('event_id')) for e in illegal]}"
                    )
                else:
                    original_boundary = boundary_frame
                    boundary_frame = protected_release_frame
                    reason = 'PROTECTED_PARTITION_MATERIAL_RELEASE'
                    if early:
                        recoveries.append({
                            'authority': _PROTECTED_HANDOFF_AUTHORITY,
                            'outgoing_scene_id': outgoing['scene_id'],
                            'incoming_scene_id': incoming['scene_id'],
                            'protected_partition_event_ids': sorted(
                                str(e.get('event_id')) for e in outgoing['members'] if _is_partition(e)
                            ),
                            'delayed_independent_root_event_ids': sorted(str(e.get('event_id')) for e in early),
                            'original_ownership_handoff_frame': int(original_boundary),
                            'ownership_handoff_frame': int(boundary_frame),
                            'ownership_handoff_seconds': round(_frame_time(boundary_frame, fps), 6),
                        })

        boundaries.append({
            'outgoing_scene_id': outgoing['scene_id'],
            'incoming_scene_id': incoming['scene_id'],
            'frame': int(boundary_frame),
            'seconds': round(_frame_time(boundary_frame, fps), 6),
            'source_boundary_frame': int(source_boundary_frame),
            'reason': reason,
        })

    # Even if a recovery is impossible, stamp deterministic windows so QA can report
    # exact violations. The caller remains fail-closed on report.pass.
    first_start = min(_frame_floor(min(row['source_start'], min(_physical_start(e) for e in row['members'])), fps)
                      for row in scene_rows)
    last_end = max(_frame_ceil(max(row['source_end'], max(_physical_end(e) for e in row['members'])), fps)
                   for row in scene_rows)
    starts = [first_start] + [int(row['frame']) for row in boundaries]
    ends = [int(row['frame']) for row in boundaries] + [last_end]
    for index, (row, start_frame, end_frame) in enumerate(zip(scene_rows, starts, ends)):
        if end_frame <= start_frame:
            failures.append(f"{row['scene_id']}: non-positive scene ownership window {start_frame}->{end_frame}")
            end_frame = start_frame + 1
        start_seconds = _frame_time(start_frame, fps)
        end_seconds = _frame_time(end_frame, fps)
        for event in row['members']:
            # Keep the exact frame/fps quotient in runtime metadata. Decimal
            # rounding (for example 74/30 -> 2.466667) can move a half-open gate
            # past its own encoded frame and manufacture a one-frame handoff gap.
            event['scene_ownership_start_seconds'] = start_seconds
            event['scene_ownership_end_seconds'] = end_seconds
            event['scene_ownership_authority'] = _AUTHORITY
            event['scene_ownership_index'] = int(index)
            if any(str(event.get('event_id')) in recovery['delayed_independent_root_event_ids'] for recovery in recoveries):
                event['scene_ownership_recovery_authority'] = _PROTECTED_HANDOFF_AUTHORITY

    final_pairs = scene_ownership_conflict_pairs(plan, fps=fps)
    if final_pairs:
        failures.append(f'cross-scene pixel ownership remains after compilation: {sorted(final_pairs)}')
    if final_pairs - raw_pairs:
        failures.append(f'ownership compilation introduced new mixed-scene pairs: {sorted(final_pairs - raw_pairs)}')

    report = {
        'authority': _AUTHORITY,
        'pass': not failures,
        'failures': failures,
        'scene_count': len(scene_rows),
        'handoffs': boundaries,
        'protected_root_recoveries': recoveries,
        'raw_mixed_scene_pairs': [list(pair) for pair in sorted(raw_pairs)],
        'final_mixed_scene_pairs': [list(pair) for pair in sorted(final_pairs)],
        'strict_conflict_set_improvement': bool(not raw_pairs or final_pairs < raw_pairs),
    }
    plan['scene_ownership_compiler'] = report
    return report


def scene_ownership_conflict_pairs(plan: dict, fps: float = 30.0) -> set[tuple[str, str]]:
    from hexa_v31.composition_qa import _state

    events = _active(list(plan.get('events') or []))
    if not events:
        return set()
    first = min(_frame_floor(float(event.get('scene_ownership_start_seconds', _physical_start(event))), fps)
                for event in events)
    last = max(_frame_ceil(float(event.get('scene_ownership_end_seconds', _physical_end(event))), fps)
               for event in events)
    pairs = set()
    for frame in range(first, last + 1):
        t = _frame_time(frame, fps)
        scenes = sorted({
            _scene_id(event)
            for event in events
            if _scene_id(event)
            and (state := _state(event, t)) is not None
            and float(state[2]) > 0.05
        })
        for index, scene_a in enumerate(scenes):
            for scene_b in scenes[index + 1:]:
                pairs.add((scene_a, scene_b))
    return pairs

