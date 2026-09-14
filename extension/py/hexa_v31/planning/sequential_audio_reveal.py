from __future__ import annotations

import math

AUTHORITY = 'HEXA_AUDIO_SEQUENTIAL_REVEAL_V1'
TRACK = 'AUDIO_SEQUENTIAL_REVEAL'
_MIN_GAP_FRAMES = 5
_REVEAL_FADE_FRAMES = 4


def _unit_sort_key(key: str) -> tuple[int, str]:
    digits = ''.join(ch for ch in str(key) if ch.isdigit())
    return (int(digits) if digits else 10**9, str(key))


def _is_protected_partition(event: dict) -> bool:
    return bool(
        event.get('partition_complete')
        and str(event.get('render_mode') or '') in {'CHILD_PARTITION', 'RESIDUAL_SUPPORT'}
    )


def _semantic_group_key(event: dict) -> str:
    root = event.get('partition_root_id')
    if _is_protected_partition(event) and root:
        return 'PARTITION::' + str(root)
    semantic = event.get('semantic_unit_id') or event.get('semantic_scope_id')
    if semantic:
        return str(semantic)
    if root:
        return 'PARTITION::' + str(root)
    return 'EVENT::' + str(event.get('event_id'))


def _effective_owner_start(event: dict) -> float:
    return max(
        float(event.get('physical_start_seconds', event.get('start_seconds', 0.0))),
        float(event.get('scene_ownership_start_seconds', event.get('physical_start_seconds', event.get('start_seconds', 0.0)))),
    )


def _effective_owner_end(event: dict) -> float:
    return min(
        float(event.get('physical_end_seconds', event.get('end_seconds', 0.0))),
        float(event.get('scene_ownership_end_seconds', event.get('physical_end_seconds', event.get('end_seconds', 0.0)))),
    )


def _strip_competing_reveal_tracks(event: dict) -> int:
    removed = 0
    for field in ('composition_states', 'composition_participant_states'):
        kept = []
        for state in event.get(field) or []:
            track = str(state.get('envelope_track') or '')
            authority = str(state.get('authority') or '')
            if track == 'SEMANTIC_SEQUENCE' or authority == 'REFERENCE_SEMANTIC_STAGGERED_SEQUENCE_V1':
                removed += 1
                continue
            kept.append(state)
        if kept:
            event[field] = kept
        else:
            event.pop(field, None)
    return removed


def _append_visibility_reveal(event: dict, hidden_from: float, reveal_at: float, fade: float) -> None:
    center = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    base = f"{event.get('event_id')}::AUDIO_REVEAL"
    states = [
        {
            'state_id': base + '::HIDDEN',
            'authority': AUTHORITY,
            'sequence_envelope': True,
            'envelope_track': TRACK,
            'semantic_beat': 'WAIT_FOR_AUDIO_CUE',
            'start_seconds': round(hidden_from, 6),
            'transition_duration_seconds': 0.0,
            'center_norm': center,
            'scale_multiplier': 1.0,
            'visibility': 0.0,
            'position_envelope': False,
        },
        {
            'state_id': base + '::REVEAL',
            'previous_state_id': base + '::HIDDEN',
            'authority': AUTHORITY,
            'sequence_envelope': True,
            'envelope_track': TRACK,
            'semantic_beat': 'AUDIO_SYNCED_REVEAL',
            'start_seconds': round(reveal_at, 6),
            'transition_duration_seconds': round(fade, 6),
            'center_norm': center,
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'position_envelope': False,
        },
    ]
    event.setdefault('composition_participant_states', []).extend(states)
    event['audio_reveal_authority'] = AUTHORITY
    event['audio_reveal_seconds'] = round(reveal_at, 6)
    event['audio_reveal_fade_seconds'] = round(fade, 6)
    event['audio_reveal_group'] = _semantic_group_key(event)
    event['pre_audio_visibility_forbidden'] = True


def finalize_audio_sequential_reveal(plan: dict, fps: float = 30.0) -> dict:
    """Make semantic elements appear one-by-one on the narration clock.

    This is a visibility-only finalizer: source pixels, masks, settled geometry,
    preset families/durations, physical lifetimes and protected Foundation
    partitions are not rewritten. Existing late semantic-stagger visibility envelopes
    are removed so there is exactly one reveal authority, while positional editorial
    entry choreography remains intact.
    """
    fps = max(1.0, float(fps))
    frame = 1.0 / fps
    min_gap = _MIN_GAP_FRAMES * frame
    fade = _REVEAL_FADE_FRAMES * frame
    events = [e for e in (plan.get('events') or []) if not e.get('suppressed_by_card_density')]
    action_cues: dict[str, list[float]] = {}
    for action in (plan.get('interaction_engine') or {}).get('physical_actions') or []:
        if action.get('event_hit_seconds') is None:
            continue
        action_cues.setdefault(str(action.get('event_id') or ''), []).append(float(action['event_hit_seconds']))

    removed_tracks = sum(_strip_competing_reveal_tracks(e) for e in events)
    by_scene: dict[str, list[dict]] = {}
    for event in events:
        by_scene.setdefault(str(event.get('scene_id') or ''), []).append(event)

    rows = []
    changed = bool(removed_tracks)
    failures = []
    for scene_id, scene_events in sorted(by_scene.items()):
        groups: dict[str, list[dict]] = {}
        for event in scene_events:
            if str(event.get('render_mode') or '') == 'RESIDUAL_SUPPORT':
                continue
            groups.setdefault(_semantic_group_key(event), []).append(event)
        if not groups:
            continue

        source_start = min(float(e.get('source_scene_start_seconds', e.get('physical_start_seconds', 0.0))) for e in scene_events)
        source_end = max(float(e.get('source_scene_end_seconds', e.get('physical_end_seconds', source_start))) for e in scene_events)
        duration = max(frame, source_end - source_start)

        group_rows = []
        for key, members in groups.items():
            protected = any(_is_protected_partition(e) for e in members)
            owner_start = max(_effective_owner_start(e) for e in members)
            owner_end = min(_effective_owner_end(e) for e in members)
            role_rank = 0 if any(str(e.get('semantic_role') or e.get('attention_priority') or '').upper() == 'PRIMARY' for e in members) else 1
            member_cues = [cue for e in members for cue in action_cues.get(str(e.get('event_id') or ''), [])]
            audio_cue = max(source_start, min(member_cues)) if member_cues else source_start
            group_rows.append({
                'key': key,
                'members': members,
                'protected': protected,
                'owner_start': owner_start,
                'owner_end': owner_end,
                'role_rank': role_rank,
                'audio_cue': audio_cue,
            })
        group_rows.sort(key=lambda g: (g['role_rank'], _unit_sort_key(g['key']), g['key']))

        base = max(source_start, min(g['owner_start'] for g in group_rows))
        count = len(group_rows)
        spacing = min(0.28, max(min_gap, duration / max(4.0, count * 2.5)))

        protected_reveals = sorted(
            max(source_start, g['owner_start']) for g in group_rows if g['protected']
        )
        early_protected = [g for g in group_rows if g['protected'] and max(source_start, g['owner_start']) <= source_start + frame + 1e-9]
        if early_protected:
            early_ids = {id(g) for g in early_protected}
            group_rows = sorted(early_protected, key=lambda g: (g['owner_start'], g['key'])) + [g for g in group_rows if id(g) not in early_ids]

        previous = None
        independent_seen = 0
        scene_reveals = []
        for group in group_rows:
            natural = max(source_start, group['audio_cue'], group['owner_start'])

            if group['protected']:
                effective = max(source_start, group['owner_start'])
                scene_reveals.append({'group': group['key'], 'seconds': round(effective, 6), 'protected': True})
                previous = effective if previous is None else max(previous, effective)
                continue

            target = natural
            if previous is not None:
                target = max(target, previous + (min_gap if independent_seen == 0 else spacing))
            elif independent_seen > 0:
                target = max(target, base + independent_seen * spacing)

            for fixed in protected_reveals:
                if abs(target - fixed) < min_gap - 1e-9:
                    target = fixed + min_gap
                    if previous is not None:
                        target = max(target, previous + min_gap)

            hidden_from = group['owner_start']
            needs_envelope = target > hidden_from + 1e-9
            latest = group['owner_end'] - (fade + frame if needs_envelope else 1e-6)
            if target > latest + 1e-9:
                failures.append(
                    f"{scene_id}:{group['key']}: no legal sequential reveal window "
                    f"target={target:.3f} latest={latest:.3f}"
                )
                continue

            for event in group['members']:
                if needs_envelope:
                    _append_visibility_reveal(event, hidden_from, target, fade)
                else:
                    event['audio_reveal_authority'] = AUTHORITY
                    event['audio_reveal_seconds'] = round(target, 6)
                    event['audio_reveal_fade_seconds'] = 0.0
                    event['audio_reveal_group'] = _semantic_group_key(event)
                    event['audio_reveal_mode'] = 'ESTABLISHED_FIRST_BEAT'
                    event['pre_audio_visibility_forbidden'] = target >= source_start - frame
            scene_reveals.append({'group': group['key'], 'seconds': round(target, 6), 'protected': False})
            previous = target
            independent_seen += 1
            changed = True

        rows.append({
            'scene_id': scene_id,
            'source_audio_start_seconds': round(source_start, 6),
            'source_audio_end_seconds': round(source_end, 6),
            'semantic_group_count': count,
            'spacing_seconds': round(spacing, 6),
            'reveals': scene_reveals,
        })

    event_by_id = {str(e.get('event_id') or ''): e for e in events}
    for action in (plan.get('interaction_engine') or {}).get('physical_actions') or []:
        event = event_by_id.get(str(action.get('event_id') or ''))
        if event is None or str(action.get('source_kind') or '') != 'PRESET_ENTRY':
            continue
        if str(event.get('audio_reveal_authority') or '') != AUTHORITY or event.get('audio_reveal_seconds') is None:
            continue
        visible_start = float(event['audio_reveal_seconds'])
        action['visible_embodiment_authority'] = AUTHORITY
        visible_fade = float(event.get('audio_reveal_fade_seconds') or 0.0)
        material_start = visible_start + (frame if visible_fade > 1e-9 else 0.0)
        action['visible_embodiment_start_seconds'] = round(visible_start, 6)
        action['visible_embodiment_material_start_seconds'] = round(material_start, 6)
        action['visible_embodiment_fade_seconds'] = round(visible_fade, 6)
        action['pre_audio_preset_motion_suppressed'] = visible_start > float(action.get('start_seconds', visible_start)) + 1e-9

    report = audio_sequential_reveal_qa(plan, fps=fps)
    failures.extend(report.get('failures') or [])
    return {
        'schema': 'HEXA_AUDIO_SEQUENTIAL_REVEAL_FINALIZER_V1',
        'authority': AUTHORITY,
        'changed': changed,
        'removed_competing_reveal_state_count': removed_tracks,
        'scene_count': len(rows),
        'scenes': rows,
        'qa': report,
        'pass': not failures,
        'failures': failures,
    }


def audio_sequential_reveal_qa(plan: dict, fps: float = 30.0) -> dict:
    fps = max(1.0, float(fps))
    min_gap = _MIN_GAP_FRAMES / fps
    events = [e for e in (plan.get('events') or []) if not e.get('suppressed_by_card_density')]
    by_scene: dict[str, dict[str, list[dict]]] = {}
    for event in events:
        if str(event.get('render_mode') or '') == 'RESIDUAL_SUPPORT':
            continue
        by_scene.setdefault(str(event.get('scene_id') or ''), {}).setdefault(_semantic_group_key(event), []).append(event)

    failures = []
    rows = []
    burst_count = 0
    pre_audio_count = 0
    for scene_id, groups in sorted(by_scene.items()):
        reveals = []
        scene_events = [e for members in groups.values() for e in members]
        if not scene_events:
            continue
        source_start = min(float(e.get('source_scene_start_seconds', e.get('physical_start_seconds', 0.0))) for e in scene_events)
        source_end = max(float(e.get('source_scene_end_seconds', e.get('physical_end_seconds', source_start))) for e in scene_events)
        for key, members in groups.items():
            protected = any(_is_protected_partition(e) for e in members)
            if protected:
                reveal = max(source_start, max(_effective_owner_start(e) for e in members))
            else:
                values = [e.get('audio_reveal_seconds') for e in members if e.get('audio_reveal_seconds') is not None]
                if not values:
                    if len(groups) > 1:
                        failures.append(f'{scene_id}:{key}: missing audio sequential reveal authority')
                    reveal = max(source_start, max(_effective_owner_start(e) for e in members))
                else:
                    reveal = min(map(float, values))
            if reveal < source_start - 1.0 / fps:
                failures.append(f'{scene_id}:{key}: reveal precedes spoken scene')
                pre_audio_count += 1
            if reveal > source_end + 0.65:
                failures.append(f'{scene_id}:{key}: reveal lags spoken scene by more than 0.65s')
            reveals.append((reveal, key, protected))
        reveals.sort()
        for a, b in zip(reveals, reveals[1:]):
            if b[0] - a[0] < min_gap - 1e-6:
                failures.append(f'{scene_id}: semantic reveal burst {a[1]}->{b[1]} gap={b[0]-a[0]:.3f}s')
                burst_count += 1
        rows.append({'scene_id': scene_id, 'reveals': [{'seconds': round(t, 6), 'group': k, 'protected': p} for t, k, p in reveals]})

    return {
        'schema': 'HEXA_AUDIO_SEQUENTIAL_REVEAL_QA_V1',
        'authority': AUTHORITY,
        'pass': not failures,
        'failures': failures,
        'burst_count': burst_count,
        'pre_audio_reveal_count': pre_audio_count,
        'minimum_inter_group_gap_frames': _MIN_GAP_FRAMES,
        'rows': rows,
    }
