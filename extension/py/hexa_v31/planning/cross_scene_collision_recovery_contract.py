"""Fail-closed recovery for residual cross-scene motion-path collisions.

The canonical handoff reconciler prefers semantic overlap: shared geometry, bounded
incoming delay, then outgoing retirement once the successor is readable. A remaining
class of conflicts can happen *before* the successor is readable, while a spatial
entry trajectory crosses the outgoing source. In that case retiring the outgoing
source early would violate visual continuity, while relaxing collision thresholds
would hide a real render defect.

This contract adds the missing generic recovery: for an independent ROOT_ATOMIC
incoming source only, degrade the colliding spatial entry to the approved
APPEAR_HIGH_SCALE scale/opacity reveal while preserving the exact perceptual hit.
The candidate commits only if canonical swept-path QA proves the triggering pair is
removed, the card conflict set strictly decreases, and no new conflict pair appears.
No actor is suppressed, no threshold is changed, narration timing is unchanged, and
partition/residual geometry is never moved.
"""
from __future__ import annotations

import copy

_AUTHORITY = 'FINAL_CROSS_SCENE_SAFE_REVEAL_RECOVERY'
_SPATIAL_ENTRY_PREFIXES = ('ENTRY_', 'WITHIN_')
_EPS = 1e-6


def _event_id(event: dict) -> str:
    return str(event.get('event_id') or '')


def _scene_id(event: dict) -> str:
    return str(event.get('scene_id') or '')


def _source_order(event: dict) -> float:
    return float(
        event.get(
            'source_scene_start_seconds',
            event.get(
                'perceptual_hit_seconds',
                event.get('physical_start_seconds', event.get('start_seconds', 0.0)),
            ),
        )
    )


def _independent_root(event: dict) -> bool:
    return (
        str(event.get('render_mode') or 'ROOT_ATOMIC') == 'ROOT_ATOMIC'
        and not event.get('partition_group_id')
    )


def _pair(row: dict) -> tuple[str, str]:
    return tuple(sorted((_event_id({'event_id': row.get('event_a')}), _event_id({'event_id': row.get('event_b')}))))


def _pair_set(rows: list[dict]) -> set[tuple[str, str]]:
    return {
        tuple(sorted((str(row.get('event_a') or ''), str(row.get('event_b') or ''))))
        for row in rows
        if row.get('event_a') is not None and row.get('event_b') is not None
    }


def _recompile_lifetime(impl, event: dict) -> None:
    intervals, motion_start, motion_end = impl._compile_final_motion_intervals(event)
    event['motion_intervals'] = intervals
    event['motion_start_seconds'] = round(float(motion_start), 6)
    event['motion_end_seconds'] = round(float(motion_end), 6)
    physical_start = float(event.get('physical_start_seconds', event.get('start_seconds', 0.0)))
    physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', physical_start)))
    event['visibility_interval_seconds'] = [round(physical_start, 6), round(physical_end, 6)]


def _apply_safe_reveal_candidate(impl, incoming: dict, fps: float) -> bool:
    """Replace only a spatial entry with a scale/opacity reveal at the same hit."""
    entry = incoming.get('preset_entry') or {}
    current_name = str(entry.get('name') or '')
    if not current_name.startswith(_SPATIAL_ENTRY_PREFIXES):
        return False
    if not _independent_root(incoming):
        return False

    safe_name = 'APPEAR_HIGH_SCALE'
    duration = float(impl.preset_duration(safe_name))
    fraction = float(impl._entry_fraction({'preset_entry': {'name': safe_name}}))
    anchor = float(
        incoming.get(
            'perceptual_hit_seconds',
            float(entry.get('start_seconds', incoming.get('start_seconds', 0.0)))
            + float(impl._entry_fraction(incoming)) * float(entry.get('duration_seconds') or duration),
        )
    )
    new_start = anchor - fraction * duration
    physical_end = float(incoming.get('physical_end_seconds', incoming.get('end_seconds', anchor)))
    if new_start >= physical_end - (1.0 / max(1.0, float(fps))) * 0.5:
        return False

    # The safe reveal normally starts later than a spatial travel entry. Never move
    # the semantic hit; only replace the pre-hit trajectory that causes the collision.
    incoming['preset_entry'] = {
        'name': safe_name,
        'start_seconds': round(new_start, 6),
        'duration_seconds': duration,
        'perceptual_hit_seconds': round(anchor, 6),
        'authority': _AUTHORITY,
    }
    incoming['start_seconds'] = round(new_start, 6)
    incoming['physical_start_seconds'] = round(new_start, 6)
    incoming['settle_seconds'] = round(new_start + duration, 6)
    incoming['appearance_method'] = 'SCALE_POP'
    incoming['position_animated'] = False
    incoming['entry_direction'] = None
    incoming['final_cross_source_motion_fallback'] = 'SPATIAL_ENTRY_TO_SAFE_REVEAL'
    incoming['final_cross_source_handoff_authority'] = _AUTHORITY
    _recompile_lifetime(impl, incoming)
    return True


def install(impl) -> None:
    if getattr(impl, '_cross_scene_collision_recovery_contract_installed', False):
        return

    base_reconcile = impl._reconcile_final_partition_handoffs

    def reconcile_final_partition_handoffs(events, cards, fps):
        base_stats = base_reconcile(events, cards, fps)
        stats = dict(base_stats or {})
        stats.setdefault('safe_reveal_candidates_evaluated', 0)
        stats.setdefault('safe_reveal_recoveries_committed', 0)
        stats.setdefault('safe_reveal_event_ids', [])
        stats.setdefault('safe_reveal_repairs', [])

        active = [event for event in events if not event.get('suppressed_by_card_density')]
        card_rows = list(cards.get('cards') or [])
        max_passes = max(1, len(active) * 2)

        for _ in range(max_passes):
            committed = False
            for card in card_rows:
                card_id = str(card.get('card_id') or '')
                card_start = float(card.get('start_seconds', 0.0))
                card_end = float(card.get('end_seconds', card_start))
                local = [
                    event for event in active
                    if str(event.get('visual_card_id') or '') == card_id
                ]
                conflicts = impl.card_motion_conflicts(local, card_start, card_end, fps)
                if not conflicts:
                    continue
                before_pairs = _pair_set(conflicts)
                by_id = {_event_id(event): event for event in local}

                for row in sorted(
                    conflicts,
                    key=lambda item: (
                        float(item.get('time_seconds', 0.0)),
                        str(item.get('event_a') or ''),
                        str(item.get('event_b') or ''),
                    ),
                ):
                    event_a = by_id.get(str(row.get('event_a') or ''))
                    event_b = by_id.get(str(row.get('event_b') or ''))
                    if event_a is None or event_b is None:
                        continue
                    if not _scene_id(event_a) or _scene_id(event_a) == _scene_id(event_b):
                        continue

                    if _source_order(event_a) < _source_order(event_b) - _EPS:
                        incoming = event_b
                    elif _source_order(event_b) < _source_order(event_a) - _EPS:
                        incoming = event_a
                    else:
                        continue
                    if not _independent_root(incoming):
                        continue

                    entry_name = str((incoming.get('preset_entry') or {}).get('name') or '')
                    if not entry_name.startswith(_SPATIAL_ENTRY_PREFIXES):
                        continue

                    stats['safe_reveal_candidates_evaluated'] += 1
                    snapshot = copy.deepcopy(incoming)
                    trigger_pair = tuple(sorted((str(row.get('event_a')), str(row.get('event_b')))))
                    if not _apply_safe_reveal_candidate(impl, incoming, fps):
                        incoming.clear(); incoming.update(snapshot)
                        continue

                    after_rows = impl.card_motion_conflicts(local, card_start, card_end, fps)
                    after_pairs = _pair_set(after_rows)
                    no_new_pairs = not (after_pairs - before_pairs)
                    improved = trigger_pair not in after_pairs and len(after_pairs) < len(before_pairs)

                    if not (improved and no_new_pairs):
                        incoming.clear(); incoming.update(snapshot)
                        continue

                    # Full canonical composition QA must not acquire a new failure
                    # class from the fallback. Existing unrelated failures remain the
                    # responsibility of their owning recovery stages.
                    qa = impl.composition_plan_qa({
                        'events': events,
                        'visual_cards': cards,
                        'fps': fps,
                    })
                    failures = list(qa.get('failures') or [])
                    if any(
                        str(incoming.get('event_id')) in str(failure)
                        and card_id not in str(failure)
                        for failure in failures
                    ):
                        incoming.clear(); incoming.update(snapshot)
                        continue

                    stats['safe_reveal_recoveries_committed'] += 1
                    stats['safe_reveal_event_ids'].append(_event_id(incoming))
                    repair = {
                        'visual_card_id': card_id,
                        'incoming_scene_id': _scene_id(incoming),
                        'incoming_event_id': _event_id(incoming),
                        'trigger_conflict': dict(row),
                        'from_entry': entry_name,
                        'to_entry': 'APPEAR_HIGH_SCALE',
                        'authority': _AUTHORITY,
                    }
                    stats['safe_reveal_repairs'].append(repair)
                    stats.setdefault('repairs', []).append(repair)
                    committed = True
                    break

                if committed:
                    break
            if not committed:
                break

            # A safe reveal can expose a later ordered conflict. Give the canonical
            # handoff reconciler another bounded chance to solve it semantically.
            followup = base_reconcile(events, cards, fps)
            for key in (
                'candidate_conflict_count', 'candidate_schedules_evaluated',
                'handoffs_committed', 'handoffs_rejected',
                'trimmed_partition_group_count', 'trimmed_source_group_count',
                'motion_fallback_count',
            ):
                stats[key] = int(stats.get(key) or 0) + int((followup or {}).get(key) or 0)
            stats.setdefault('incoming_delay_frames', []).extend((followup or {}).get('incoming_delay_frames') or [])
            stats.setdefault('trimmed_event_ids', []).extend((followup or {}).get('trimmed_event_ids') or [])
            stats.setdefault('repairs', []).extend((followup or {}).get('repairs') or [])

        stats['safe_reveal_event_ids'] = sorted(set(stats['safe_reveal_event_ids']))
        stats['trimmed_event_ids'] = sorted(set(stats.get('trimmed_event_ids') or []))
        return stats

    # Dependencies are explicitly attached so the contract stays testable and does
    # not reach through hidden globals.
    from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa
    impl.card_motion_conflicts = card_motion_conflicts
    impl.composition_plan_qa = composition_plan_qa
    reconcile_final_partition_handoffs.__name__ = base_reconcile.__name__
    reconcile_final_partition_handoffs.__doc__ = base_reconcile.__doc__
    impl._reconcile_final_partition_handoffs = reconcile_final_partition_handoffs
    impl._cross_scene_collision_recovery_contract_installed = True
