from __future__ import annotations

"""Collision semantics for certified source partitions.

A complete CHILD_PARTITION is one source-backed semantic composition slot even when
Foundation exposes several independently renderable physical children. Bounding-box
intersection between two children of that same certified partition is therefore an
internal source-composite property, not a collision between independent composition
slots. External actors, different partition roots, different source scenes and
incomplete partitions remain under the unchanged hard collision thresholds.
"""


def _partition_root(event: dict) -> str:
    return str(event.get('partition_root_id') or '').strip()


def same_certified_partition_slot(a: dict, b: dict) -> bool:
    """Return True only for siblings inside one complete source-backed partition."""
    if str(a.get('scene_id') or '') != str(b.get('scene_id') or ''):
        return False
    if str(a.get('render_mode') or '') != 'CHILD_PARTITION':
        return False
    if str(b.get('render_mode') or '') != 'CHILD_PARTITION':
        return False
    if not bool(a.get('partition_complete')) or not bool(b.get('partition_complete')):
        return False
    root_a = _partition_root(a)
    root_b = _partition_root(b)
    return bool(root_a and root_a == root_b)


def install(qa_module) -> None:
    if getattr(qa_module, '_partition_collision_contract_installed', False):
        return

    base_card_motion_conflicts = qa_module.card_motion_conflicts

    def card_motion_conflicts(events: list[dict], start_seconds: float, end_seconds: float, fps: float = 30.0) -> list[dict]:
        """Keep hard collision QA between composition slots, not within one partition."""
        rows = base_card_motion_conflicts(events, start_seconds, end_seconds, fps)
        by_id = {str(event.get('event_id')): event for event in events}
        kept = []
        for row in rows:
            a = by_id.get(str(row.get('event_a')))
            b = by_id.get(str(row.get('event_b')))
            if a is not None and b is not None and same_certified_partition_slot(a, b):
                continue
            kept.append(row)
        return kept

    def composition_plan_qa(motion_plan: dict) -> dict:
        failures = []
        warnings = []
        cards = (motion_plan.get('visual_cards') or {}).get('cards') or []
        events = motion_plan.get('events') or []
        fps = float(motion_plan.get('fps') or 30.0)
        by_card = {str(card.get('card_id')): [] for card in cards}
        for event in events:
            if not event.get('suppressed_by_card_density'):
                by_card.setdefault(str(event.get('visual_card_id')), []).append(event)

        total_pairs = 0
        bad_pairs = 0
        dynamic_samples = 0
        internal_partition_pairs = 0

        for card in cards:
            card_id = str(card.get('card_id'))
            card_events = by_card.get(card_id, [])
            phase_plan = card.get('story_phase_plan') or {}
            phases = phase_plan.get('phases') or []
            if not phases:
                failures.append(f'{card_id}: no visual story phases compiled')
                continue
            event_map = {str(event.get('event_id')): event for event in card_events}

            for phase in phases:
                rows = [event_map[event_id] for event_id in phase.get('event_ids') or [] if event_id in event_map]
                for event in rows:
                    rect, visibility = qa_module._phase_settled_rect(event, phase)
                    if visibility <= 0.05:
                        continue
                    if not qa_module._in_safe(rect):
                        failures.append(
                            f"{card_id}/{phase.get('phase_id')}:{event.get('event_id')}: settled bbox outside safe frame"
                        )

                rects = qa_module._phase_common_settled_rects(rows, phase)
                for index, (a, rect_a) in enumerate(rects):
                    for b, rect_b in rects[index + 1:]:
                        if same_certified_partition_slot(a, b):
                            internal_partition_pairs += 1
                            continue
                        total_pairs += 1
                        overlap = qa_module.overlap_ratio(rect_a, rect_b)
                        primary_a = qa_module._norm(a.get('attention_priority')) == 'PRIMARY'
                        primary_b = qa_module._norm(b.get('attention_priority')) == 'PRIMARY'
                        limit = 0.002 if primary_a and primary_b else (0.01 if primary_a or primary_b else 0.025)
                        if overlap > limit:
                            bad_pairs += 1
                            failures.append(
                                f"{card_id}/{phase.get('phase_id')}: settled overlap "
                                f"{a.get('event_id')} x {b.get('event_id')}={overlap:.3f}>{limit:.3f}"
                            )

                occupancy = sum(rect[2] * rect[3] for _, rect in rects)
                if occupancy > 0.62:
                    warnings.append(
                        f"{card_id}/{phase.get('phase_id')}: bbox occupancy {occupancy:.3f}>0.62; visual density high"
                    )

            card_start = float(card.get('start_seconds', 0))
            card_end = float(card.get('end_seconds', card_start))
            step = 1.0 / max(12.0, min(20.0, fps))
            dynamic_samples += int(max(0.0, card_end - card_start) / step + 1) * max(
                0, len(card_events) * (len(card_events) - 1) // 2
            )
            for row in card_motion_conflicts(card_events, card_start, card_end, fps):
                bad_pairs += 1
                failures.append(
                    f"{card_id}@{row['time_seconds']:.2f}s: motion-path overlap "
                    f"{row['event_a']} x {row['event_b']}={row['overlap_ratio']:.3f}>{row['limit']:.3f}"
                )

        failures = list(dict.fromkeys(failures))
        warnings = list(dict.fromkeys(warnings))
        viewport = qa_module.viewport_clipping_qa(events, fps)
        failures.extend(viewport['failures'])
        return {
            'pass': not failures,
            'failures': failures,
            'warnings': warnings,
            'checked_pair_count': total_pairs,
            'dynamic_pair_samples': dynamic_samples,
            'bad_pair_count': bad_pairs,
            'visual_card_count': len(cards),
            'viewport_clipping_qa': viewport,
            'partition_internal_pair_count': internal_partition_pairs,
            'partition_collision_authority': 'CERTIFIED_PARTITION_IS_ONE_SEMANTIC_COMPOSITION_SLOT',
            'authority': 'V31_PHASE_DESTINATION_COMPOSITION__COMMON_SETTLED_AND_MOTION_PATH_HARD_GATE',
        }

    qa_module.card_motion_conflicts = card_motion_conflicts
    qa_module.composition_plan_qa = composition_plan_qa
    qa_module.same_certified_partition_slot = same_certified_partition_slot
    qa_module._partition_collision_contract_installed = True
