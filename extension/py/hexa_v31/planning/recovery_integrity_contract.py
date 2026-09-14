"""Truthful, fail-closed integrity layer for final motion recovery.

This contract does not weaken canonical QA. It fixes three integrity gaps that can
surface only after late finalizers have produced the exact render transform state:

* an already causally ordered reaction must not be labelled as a retime;
* a cross-scene retirement may preserve only visibility that existed beforehand,
  while its effective motion envelope must not outlive the shortened carrier;
* multiple independent residual motion-path collisions are recovered monotonically,
  one canonical pair at a time, with no new pair allowed to appear.

Every technically accepted repair remains ``CI_VERIFIED_RENDER_PENDING``. Nothing in
this module promotes Recovery memory to PROVEN or bypasses encoded/visual validation.
"""
from __future__ import annotations

import copy
import re

from hexa_v31.planning.same_scene_collision_recovery_contract import _apply_scene_layout
from hexa_v31.recovery.memory import RecoveryMemory

_AUTHORITY = 'FINAL_CERTIFICATION_DYNAMIC_CROSS_SCENE_HANDOFF_RECOVERY'
_SAME_SCENE_AUTHORITY = 'FINAL_CERTIFICATION_DYNAMIC_SAME_SCENE_LAYOUT_RECOVERY'
_BATCH_AUTHORITY = 'FINAL_CERTIFICATION_MONOTONIC_RESIDUAL_RECOVERY'
_PROBLEM_ID = 'HEXA_MOTION_PATH_OVERLAP'
_PROBLEM_NAME = 'motion-path overlap'
_DYNAMIC_RE = re.compile(
    r'(?P<card>VCARD_[^@:\s]+)@(?P<time>[0-9]+(?:\.[0-9]+)?)s:\s*'
    r'motion-path overlap\s+(?P<a>\S+)\s+x\s+(?P<b>\S+)='
)


def _restore_all(events, snapshots):
    for live, snapshot in zip(events, snapshots):
        live.clear()
        live.update(copy.deepcopy(snapshot))


def _restore_cards(cards, snapshot):
    cards.clear()
    cards.update(copy.deepcopy(snapshot))


def _parse_failures(message):
    rows = []
    seen = set()
    for match in _DYNAMIC_RE.finditer(str(message)):
        pair = tuple(sorted((match.group('a'), match.group('b'))))
        key = (match.group('card'), pair)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            'card_id': match.group('card'),
            'time_seconds': float(match.group('time')),
            'event_a': match.group('a'),
            'event_b': match.group('b'),
        })
    return rows


def _failure_key(row):
    return (
        str(row.get('card_id') or ''),
        tuple(sorted((str(row.get('event_a') or ''), str(row.get('event_b') or '')))),
    )


def _failure_keys(rows):
    return {_failure_key(row) for row in rows}


def _canonical_state(events, cards, fps):
    from hexa_v31.composition_qa import composition_plan_qa

    qa = composition_plan_qa({'events': events, 'visual_cards': cards, 'fps': fps})
    if qa.get('pass'):
        return [], qa
    failures = list(qa.get('failures') or [])
    rows = _parse_failures(' | '.join(str(row) for row in failures))
    if not rows:
        return None, qa
    parsed = _failure_keys(rows)
    for failure in failures:
        matches = _parse_failures(str(failure))
        if not matches or not _failure_keys(matches).issubset(parsed):
            return None, qa
    return rows, qa


def _card_by_id(cards, card_id):
    return next(
        (card for card in (cards or {}).get('cards') or []
         if str(card.get('card_id') or '') == str(card_id or '')),
        None,
    )


def _recompile_motion_to_carrier(impl, event, carrier_end):
    intervals, motion_start, _ = impl._compile_final_motion_intervals(event)
    clipped = []
    for source in intervals:
        row = dict(source)
        start = float(row.get('effective_start_seconds', row.get('start_seconds', motion_start)))
        old_end = float(row.get('effective_end_seconds', start))
        end = min(float(carrier_end), old_end)
        row['effective_end_seconds'] = round(end, 6)
        row['effective_duration_seconds'] = round(max(0.0, end - start), 6)
        if old_end > float(carrier_end) + 1e-6:
            row['clipped_by_final_source_handoff'] = True
        clipped.append(row)
    motion_end = max(
        [float(row.get('effective_end_seconds', motion_start)) for row in clipped]
        or [float(motion_start)]
    )
    event['motion_intervals'] = clipped
    event['motion_start_seconds'] = round(float(motion_start), 6)
    event['motion_end_seconds'] = round(float(motion_end), 6)


def _retire_outgoing_truthful(cross, impl, state_fn, event, handoff_end, fps):
    if not cross._is_independent_root(event):
        return False
    step = 1.0 / max(1.0, float(fps))
    physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
    current_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
    new_end = min(float(handoff_end), current_end)
    if new_end <= physical_start + step * 0.5 or new_end >= current_end - step * 0.25:
        return False

    anchor = float(event.get('perceptual_hit_seconds', event.get('start_seconds', physical_start)))
    if str(event.get('perceptual_hit_source') or '').upper() == 'VOICE_TRIGGER' and anchor >= new_end - step * 0.25:
        return False
    anchor_state_before = state_fn(event, anchor)
    anchor_was_materially_visible = (
        anchor_state_before is not None and float(anchor_state_before[2]) > 0.22
    )

    duration = float(impl.preset_duration('DISAPPEAR_DOWN_SCALE'))
    visible_fraction = float(impl._motion_interval_effective_fraction('EXIT', 'DISAPPEAR_DOWN_SCALE'))
    exit_start = max(physical_start, new_end - duration * visible_fraction)
    event['preset_actions'] = []
    event['preset_exit'] = {
        'name': 'DISAPPEAR_DOWN_SCALE',
        'start_seconds': round(exit_start, 6),
        'duration_seconds': duration,
        'authority': cross._AUTHORITY,
    }
    event['disappearance_method'] = 'PRESET_DISAPPEARANCE'
    event['end_seconds'] = round(new_end, 6)
    event['physical_end_seconds'] = round(new_end, 6)
    event['visibility_interval_seconds'] = [round(physical_start, 6), round(new_end, 6)]
    event['final_cross_source_handoff_authority'] = cross._AUTHORITY
    event['final_cross_source_motion_fallback'] = 'OPTIONAL_MOTION_REMOVED_FOR_VISIBLE_ONSET_HANDOFF'
    _recompile_motion_to_carrier(impl, event, new_end)

    if anchor_was_materially_visible:
        state = state_fn(event, anchor)
        if state is None or float(state[2]) <= 0.22:
            return False
    return True


def _patch_choreography_truthfulness():
    from hexa_v31.interaction import choreography

    original = choreography._retime_reaction_after_cause
    if getattr(original, '_hexa_truthful_retime', False):
        return

    def truthful(event, intent, fps, not_before):
        row = choreography._entry_manifestation(event, 'REACTION')
        if not row:
            return None
        if str(intent.get('semantic_action') or '') != 'REACT' or str(intent.get('causal_direction') or '') != 'OBJECT_CAUSES_SUBJECT_REACTION':
            return None
        if 'TRANSLATE' in set(row.get('required_operations') or []):
            return None
        dd = float(row['duration_seconds'])
        original_start = float(row['start_seconds'])
        new_start = max(original_start, float(not_before))
        new_end = new_start + dd
        physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', new_start)))
        physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', new_end)))
        if new_start < physical_start - 1e-6 or new_end > physical_end + 1e-6:
            return None
        px = event.get('preset_exit') or {}
        if px and new_end > float(px.get('start_seconds', physical_end)) + 1e-6:
            return None
        if any(float(action.get('start_seconds', physical_end)) < new_end - 1e-6 for action in event.get('preset_actions') or []):
            return None
        if new_start <= original_start + 1e-6:
            adopted = dict(row)
            adopted.update({
                'semantic_anchor_match': False,
                'causal_order_already_satisfied': True,
                'authority': 'CAUSALLY_ORDERED_EXISTING_ENTRY',
                'key': '|'.join((str(event.get('event_id')), str(row['preset']), f'{original_start:.6f}', 'REACTION_CAUSAL_FIXED')),
            })
            return adopted
        retimed = dict(row)
        retimed.update({
            'start_seconds': round(new_start, 6),
            'end_seconds': round(new_end, 6),
            'perceptual_impact_seconds': round(new_start + choreography._entry_fraction(str(row['preset'])) * dd, 6),
            'retime_existing_entry': True,
            'original_start_seconds': original_start,
            'original_end_seconds': float(row['end_seconds']),
            'retime_reason': 'REACT_CAUSAL_ORDER_REACTION_DELAY',
            'semantic_anchor_match': False,
            'key': '|'.join((str(event.get('event_id')), str(row['preset']), f'{new_start:.6f}', 'REACTION_CAUSAL_DELAY')),
        })
        return retimed

    truthful._hexa_truthful_retime = True
    choreography._retime_reaction_after_cause = truthful


def _run_candidate(base, events, cards, fps, previous_keys, target_key):
    try:
        result = base(events, cards, fps)
    except ValueError as exc:
        rows, qa = _canonical_state(events, cards, fps)
        if rows is None:
            return 'REJECT', None, None, exc
        new_keys = _failure_keys(rows)
        if target_key in new_keys or not new_keys < previous_keys:
            return 'REJECT', None, None, exc
        return 'MONOTONIC', rows, qa, exc
    if not result or not result.get('pass'):
        return 'REJECT', None, None, None
    return 'PASS', [], result, None


def _same_scene_attempt(impl, events, cards, fps, failure, previous_keys, cross, base):
    by_id = {str(event.get('event_id') or ''): event for event in events}
    a = by_id.get(failure['event_a']); b = by_id.get(failure['event_b'])
    if a is None or b is None:
        return None
    scene_id = cross._scene_id(a)
    if not scene_id or scene_id != cross._scene_id(b):
        return None
    if not (cross._is_independent_root(a) and cross._is_independent_root(b)):
        return None
    card = _card_by_id(cards, failure['card_id'])
    if card is None:
        return None
    event_snapshot = [copy.deepcopy(event) for event in events]
    card_snapshot = copy.deepcopy(cards)
    changed, stale_count = _apply_scene_layout(impl, card, events, scene_id)
    if not changed:
        _restore_all(events, event_snapshot); _restore_cards(cards, card_snapshot)
        return None
    status, rows, qa_or_result, error = _run_candidate(
        base, events, cards, fps, previous_keys, _failure_key(failure)
    )
    if status == 'REJECT':
        _restore_all(events, event_snapshot); _restore_cards(cards, card_snapshot)
        return None
    card['final_certification_dynamic_same_scene_recovery_authority'] = _SAME_SCENE_AUTHORITY
    return status, rows, qa_or_result, {
        'type': 'FINAL_CERTIFICATION_DYNAMIC_SAME_SCENE_LAYOUT',
        'authority': _SAME_SCENE_AUTHORITY,
        'problem_id': _PROBLEM_ID,
        'problem_name': _PROBLEM_NAME,
        'problem_source': 'CI',
        'recovery_validation_state': 'CI_VERIFIED_RENDER_PENDING',
        'visual_card_id': failure['card_id'],
        'scene_id': scene_id,
        'event_ids': sorted((failure['event_a'], failure['event_b'])),
        'stale_phase_geometry_state_count': int(stale_count),
    }, error


def _cross_scene_attempts(impl, events, cards, fps, failure, previous_keys, cross, base):
    from hexa_v31.composition_qa import _state

    by_id = {str(event.get('event_id') or ''): event for event in events}
    a = by_id.get(failure['event_a']); b = by_id.get(failure['event_b'])
    if a is None or b is None or cross._scene_id(a) == cross._scene_id(b):
        return None
    if not (cross._is_independent_root(a) and cross._is_independent_root(b)):
        return None
    if cross._source_order(a) < cross._source_order(b) - 1e-6:
        outgoing_id, incoming_id = str(a.get('event_id')), str(b.get('event_id'))
    elif cross._source_order(b) < cross._source_order(a) - 1e-6:
        outgoing_id, incoming_id = str(b.get('event_id')), str(a.get('event_id'))
    else:
        return None

    step = 1.0 / max(1.0, float(fps)); max_sync_frames = 6
    max_lead_frames = max(6, int(round(float(fps) * 0.8)))
    family = '|'.join((
        'DYNAMIC_CROSS_SCENE',
        str(by_id[outgoing_id].get('attention_priority') or 'UNKNOWN').upper(),
        str(by_id[incoming_id].get('attention_priority') or 'UNKNOWN').upper(),
        'ENTRY:' + str((by_id[incoming_id].get('preset_entry') or {}).get('name') or 'NONE').upper(),
        'EXIT:' + str((by_id[outgoing_id].get('preset_exit') or {}).get('name') or 'NONE').upper(),
    ))
    schedules = [(d, l) for d in range(max_sync_frames + 1) for l in range(1, max_lead_frames + 1)]
    by_strategy = {f'DELAY_{d}_LEAD_{l}': (d, l) for d, l in schedules}
    order = RecoveryMemory().rank(family, list(by_strategy))
    attempted = 0
    for strategy in order:
        delay_frames, lead_frames = by_strategy[strategy]
        event_snapshot = [copy.deepcopy(event) for event in events]
        card_snapshot = copy.deepcopy(cards)
        live = {str(event.get('event_id') or ''): event for event in events}
        outgoing = live[outgoing_id]; incoming = live[incoming_id]
        if not cross._shift_incoming(impl, incoming, delay_frames, fps, max_sync_frames):
            continue
        handoff_end = float(failure['time_seconds']) + delay_frames * step - lead_frames * step
        if not _retire_outgoing_truthful(cross, impl, _state, outgoing, handoff_end, fps):
            _restore_all(events, event_snapshot); _restore_cards(cards, card_snapshot)
            continue
        attempted += 1
        outgoing['final_certification_dynamic_recovery_authority'] = _AUTHORITY
        incoming['final_certification_dynamic_recovery_authority'] = _AUTHORITY
        status, rows, qa_or_result, error = _run_candidate(
            base, events, cards, fps, previous_keys, _failure_key(failure)
        )
        if status == 'REJECT':
            _restore_all(events, event_snapshot); _restore_cards(cards, card_snapshot)
            continue
        return status, rows, qa_or_result, {
            'type': 'FINAL_CERTIFICATION_DYNAMIC_CROSS_SCENE_HANDOFF',
            'authority': _AUTHORITY,
            'problem_id': _PROBLEM_ID,
            'problem_name': _PROBLEM_NAME,
            'problem_source': 'CI',
            'recovery_validation_state': 'CI_VERIFIED_RENDER_PENDING',
            'visual_card_id': failure['card_id'],
            'outgoing_event_id': outgoing_id,
            'incoming_event_id': incoming_id,
            'handoff_seconds': round(handoff_end, 6),
            'incoming_delay_frames': int(delay_frames),
            'lead_frames': int(lead_frames),
            'recovery_memory_family': family,
            'recovery_strategy': strategy,
            'attempted_strategy_count': attempted,
        }, error
    return None


def install(impl):
    if getattr(impl, '_recovery_integrity_contract_installed', False):
        return

    _patch_choreography_truthfulness()

    from hexa_v31.planning import final_cross_scene_handoff_recovery_contract as cross
    from hexa_v31.planning import final_certification_dynamic_collision_recovery_contract as dynamic

    cross._retire_outgoing = lambda impl_, state_fn, event, handoff_end, fps: _retire_outgoing_truthful(
        cross, impl_, state_fn, event, handoff_end, fps
    )
    dynamic._retire_outgoing = cross._retire_outgoing

    base = getattr(impl, '_final_certification_dynamic_collision_recovery_base', None)
    if base is None:
        raise RuntimeError('RECOVERY_INTEGRITY_REQUIRES_DYNAMIC_BASE')

    def wrapped(events, cards, fps):
        global_events = [copy.deepcopy(event) for event in events]
        global_cards = copy.deepcopy(cards)
        try:
            return base(events, cards, fps)
        except ValueError as exc:
            original_error = exc
            if not _parse_failures(str(exc)):
                raise

        rows, _ = _canonical_state(events, cards, fps)
        if not rows:
            _restore_all(events, global_events); _restore_cards(cards, global_cards)
            raise original_error
        initial_keys = _failure_keys(rows)
        current_rows = rows
        repairs = []

        for _ in range(len(initial_keys)):
            previous_keys = _failure_keys(current_rows)
            progressed = False
            for failure in sorted(
                current_rows,
                key=lambda row: (
                    str(row.get('card_id') or ''),
                    float(row.get('time_seconds') or 0.0),
                    tuple(sorted((str(row.get('event_a') or ''), str(row.get('event_b') or '')))),
                ),
            ):
                by_id = {str(event.get('event_id') or ''): event for event in events}
                a = by_id.get(failure['event_a']); b = by_id.get(failure['event_b'])
                if a is None or b is None:
                    continue
                if cross._scene_id(a) and cross._scene_id(a) == cross._scene_id(b):
                    attempt = _same_scene_attempt(impl, events, cards, fps, failure, previous_keys, cross, base)
                else:
                    attempt = _cross_scene_attempts(impl, events, cards, fps, failure, previous_keys, cross, base)
                if not attempt:
                    continue
                status, next_rows, qa_or_result, repair, _ = attempt
                repairs.append(repair); progressed = True
                if status == 'PASS':
                    result = qa_or_result
                    merged = list(result.get('repairs') or []); merged.extend(repairs)
                    result['repairs'] = merged
                    result['recovery_validation_state'] = 'CI_VERIFIED_RENDER_PENDING'
                    result['recovery_problem_id'] = _PROBLEM_ID
                    result['final_certification_residual_recovery'] = {
                        'authority': _BATCH_AUTHORITY,
                        'initial_conflict_pair_count': len(initial_keys),
                        'repair_count': len(repairs),
                        'remaining_conflict_pair_count': 0,
                    }
                    return result
                current_rows = next_rows or []
                break
            if not progressed:
                _restore_all(events, global_events); _restore_cards(cards, global_cards)
                raise original_error

        _restore_all(events, global_events); _restore_cards(cards, global_cards)
        raise original_error

    wrapped.__name__ = base.__name__
    wrapped.__doc__ = base.__doc__
    impl._final_physical_certification = wrapped
    impl._recovery_integrity_contract_installed = True
