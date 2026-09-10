from __future__ import annotations

"""Compile and physically apply bounded editorial beat choreography.

V31 already had a semantic beat diagnostic, but it did not materially affect
pixels. This implementation keeps the semantic compiler bounded and adds one
render-authoritative operation: source-backed, translation-safe ROOT_ATOMIC
actors that would otherwise only scale-pop may receive a deterministic
one-shot directional entry envelope. The envelope is validated by the same
trajectory and viewport QA used by the final plan and therefore cannot bypass
P1/P2 safety.
"""

import copy

from hexa_v31.composition_qa import card_motion_conflicts, viewport_clipping_qa
from hexa_v31.composition_solver import SAFE_X, SAFE_Y, _fp

_AUTHORITY = 'PRE_LAYOUT_PROGRESSIVE_SCENE_BEATS_V1'
_ENTRY_TRACK = 'EDITORIAL_ENTRY'

_BEATS = {
    'READ': ('ESTABLISH', 'SUPPORT_REVEAL', 'FOCUS_TRANSFER', 'RESULT_LOCK'),
    'BLOCK': ('ESTABLISH', 'BARRIER_REVEAL', 'RELATIONSHIP', 'RESOLVE'),
    'COMPARE': ('A_ESTABLISH', 'B_ESTABLISH', 'READABLE_OVERLAP', 'DIFFERENCE_EMPHASIS'),
    'TRANSFER': ('SOURCE', 'CONNECTION', 'DESTINATION', 'RESULT'),
    'CONNECT': ('ESTABLISH', 'SUPPORT_REVEAL', 'RELATIONSHIP', 'COMPOSITION_REBUILD'),
    'REVEAL': ('ESTABLISH', 'SUPPORT_REVEAL', 'FOCUS_TRANSFER', 'COMPOSITION_REBUILD'),
    'RESOLVE': ('ESTABLISH', 'RELATIONSHIP', 'RESULT_REVEAL', 'HANDOFF'),
    'PRESENT': ('ESTABLISH', 'SUPPORT_REVEAL', 'READABLE_OVERLAP', 'HANDOFF'),
}


def _existing_position_envelope(event: dict) -> bool:
    for key in ('composition_states', 'composition_participant_states'):
        for state in event.get(key) or []:
            if state.get('position_envelope'):
                return True
    return False


def _translation_eligible(event: dict) -> bool:
    if event.get('suppressed_by_card_density'):
        return False
    if str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
        return False
    if event.get('partition_group_id') or event.get('composite_atomic'):
        return False
    if not bool(event.get('translation_safe_after_occlusion', event.get('animation_safe', False))):
        return False
    if 'TRANSLATE' not in (event.get('visual_affordance_operations') or []):
        return False
    entry = event.get('preset_entry') or {}
    if str(entry.get('name') or '').startswith('ENTRY_'):
        return False
    if _existing_position_envelope(event):
        return False
    return bool(entry)


def _candidate_origins(event: dict) -> list[tuple[str, list[float], float]]:
    target = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    fp = _fp(event)
    scale = float(event.get('layout_scale_multiplier') or 1.0)
    width = fp.w * scale
    height = fp.h * scale
    candidates = {
        'LEFT': [SAFE_X[0] - width / 2.0 - 0.025, target[1]],
        'RIGHT': [SAFE_X[1] + width / 2.0 + 0.025, target[1]],
        'TOP': [target[0], SAFE_Y[0] - height / 2.0 - 0.025],
        'BOTTOM': [target[0], SAFE_Y[1] + height / 2.0 + 0.025],
    }
    edge_distance = {
        'LEFT': max(0.0, target[0] - SAFE_X[0]),
        'RIGHT': max(0.0, SAFE_X[1] - target[0]),
        'TOP': max(0.0, target[1] - SAFE_Y[0]),
        'BOTTOM': max(0.0, SAFE_Y[1] - target[1]),
    }
    bias = {name: 0.0 for name in candidates}
    if target[0] < 0.43:
        bias['LEFT'] -= 0.10
    elif target[0] > 0.57:
        bias['RIGHT'] -= 0.10
    if target[1] < 0.40:
        bias['TOP'] -= 0.07
    elif target[1] > 0.64:
        bias['BOTTOM'] -= 0.07
    rows = [(name, candidates[name], edge_distance[name] + bias[name]) for name in candidates]
    rows.sort(key=lambda row: (row[2], row[0]))
    return rows


def _entry_states(event: dict, origin: list[float], direction: str, fps: float) -> list[dict] | None:
    entry = event.get('preset_entry') or {}
    start = float(entry.get('start_seconds', event.get('start_seconds', 0.0)))
    preset_duration = max(0.0, float(entry.get('duration_seconds') or 0.0))
    physical_end = float(event.get('physical_end_seconds', event.get('end_seconds', start)))
    action_starts = [float(a.get('start_seconds')) for a in event.get('preset_actions') or [] if a.get('start_seconds') is not None]
    hard_end = min([physical_end, *action_starts]) if action_starts else physical_end
    frame = 1.0 / max(1.0, fps)
    transition = min(0.72, max(0.42, preset_duration * 0.82 if preset_duration else 0.58))
    settle_start = start + frame
    transition = min(transition, hard_end - settle_start - 0.08)
    if transition < 0.32:
        return None
    target = list(event.get('card_rest_position_norm') or [0.5, 0.5])
    base = f"{event.get('event_id')}::EDITORIAL_ENTRY"
    common = {
        'authority': _AUTHORITY,
        # These are ordinary composition states, deliberately ordered before
        # any later focus/rebuild states. A persistent sequence track would
        # otherwise keep forcing the rest center and cancel later composition.
        'envelope_track': _ENTRY_TRACK,
        'position_envelope': True,
        'card_id': event.get('visual_card_id'),
        'editorial_motion_family': 'DIRECTIONAL_ENTRY',
        'entry_direction': direction,
    }
    origin_state = dict(
        common,
        state_id=base + '::ORIGIN',
        semantic_beat='ENTRY_ORIGIN',
        start_seconds=round(start, 6),
        transition_duration_seconds=0.0,
        center_norm=[round(float(origin[0]), 6), round(float(origin[1]), 6)],
        scale_multiplier=0.96,
        visibility=0.0,
    )
    settle_state = dict(
        common,
        state_id=base + '::SETTLE',
        previous_state_id=origin_state['state_id'],
        semantic_beat='DIRECTIONAL_REVEAL',
        start_seconds=round(settle_start, 6),
        transition_duration_seconds=round(transition, 6),
        center_norm=[round(float(target[0]), 6), round(float(target[1]), 6)],
        scale_multiplier=1.0,
        visibility=1.0,
    )
    return [origin_state, settle_state]


def _try_directional_entry(event: dict, local_events: list[dict], fps: float) -> tuple[str | None, str | None]:
    if not _translation_eligible(event):
        return None, 'NOT_TRANSLATION_ELIGIBLE'
    start = min(float(e.get('physical_start_seconds', e.get('start_seconds', 0.0))) for e in local_events)
    end = max(float(e.get('physical_end_seconds', e.get('end_seconds', start))) for e in local_events)
    for direction, origin, _ in _candidate_origins(event):
        states = _entry_states(event, origin, direction, fps)
        if not states:
            return None, 'INSUFFICIENT_ENTRY_WINDOW'
        trial = copy.deepcopy(event)
        trial.setdefault('composition_states', []).extend(copy.deepcopy(states))
        candidate = [trial if e is event else copy.deepcopy(e) for e in local_events]
        if card_motion_conflicts(candidate, start, end, fps):
            continue
        if not viewport_clipping_qa([trial], fps).get('pass'):
            continue
        event.setdefault('composition_states', []).extend(states)
        event['editorial_entry_direction'] = direction
        event['editorial_entry_motion_family'] = 'DIRECTIONAL_COMPOSITION_ENTRY'
        event['editorial_entry_authority'] = _AUTHORITY
        return direction, None
    return None, 'NO_SAFE_DIRECTION'


class BeatChoreographyCompiler:
    version = 'HEXA_BEAT_CHOREOGRAPHY_COMPILER_V2'

    def compile(self, events, sentences, fps: float = 30.0):
        sentence_by_id = {s['sentence_id']: s for s in sentences}
        rows = []
        direction_counts = {name: 0 for name in ('LEFT', 'RIGHT', 'TOP', 'BOTTOM')}
        rejection_counts: dict[str, int] = {}
        directional_count = 0
        staggered_count = 0

        for sentence_id, sentence in sorted(sentence_by_id.items()):
            members = sorted(
                (e for e in events if e.get('semantic_visual_sentence_id') == sentence_id and not e.get('suppressed_by_card_density')),
                key=lambda e: (
                    float(e.get('physical_start_seconds', e.get('start_seconds', 0.0))),
                    float(e.get('perceptual_hit_seconds', 0.0)),
                    str(e.get('event_id')),
                ),
            )
            action = str(sentence.get('action') or 'PRESENT')
            sequence = _BEATS.get(action, ('ESTABLISH', 'SUPPORT_REVEAL', 'READABLE_OVERLAP', 'HANDOFF'))
            starts = [round(float(e.get('physical_start_seconds', e.get('start_seconds', 0.0))), 4) for e in members]
            staggered = len(set(starts)) >= 2 if len(members) >= 2 else False
            staggered_count += int(staggered)

            applied = []
            for event in members:
                direction, reason = _try_directional_entry(event, members, fps)
                if direction:
                    directional_count += 1
                    direction_counts[direction] += 1
                    applied.append({'event_id': event.get('event_id'), 'direction': direction})
                elif reason and reason != 'NOT_TRANSLATION_ELIGIBLE':
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

            row = {
                'sentence_id': sentence_id,
                'action': action,
                'beat_sequence': list(sequence),
                'event_ids': [e.get('event_id') for e in members],
                'physical_start_seconds': starts,
                'staggered_reveal': staggered,
                'directional_entries': applied,
                'fallback_static': not bool(members),
                'authority': _AUTHORITY,
            }
            rows.append(row)
            for event in members:
                event['beat_choreography_id'] = sentence_id
                event['beat_choreography_sequence'] = row['beat_sequence']
                event['beat_choreography_fallback_static'] = row['fallback_static']

        return {
            'version': self.version,
            'beat_count': len(rows),
            'beats': rows,
            'consumed_by_planner': True,
            'directional_entry_count': directional_count,
            'direction_counts': direction_counts,
            'staggered_sentence_count': staggered_count,
            'directional_entry_rejections': rejection_counts,
            'authority': _AUTHORITY,
        }
