"""Shipping contract for material phase focus hierarchy.

The semantic planner may correctly name a focus actor while a collision-safe phase
solve leaves focus and context at the same relative scale. That is metadata-only
focus and does not satisfy the viewer-facing editorial contract. This compatibility
layer post-certifies phase geometry without changing actor lifetimes, source identity,
centers, or protected P1 partition geometry.
"""
from __future__ import annotations

import itertools
import math

_MIN_FOCUS_FACTOR_GAP = 0.10
_EPS = 1e-9
_MAX_CONTEXT_CANDIDATES = 6


def _factor(layout: dict, event_id: str, placement: dict) -> float:
    base = float((layout.get('placements') or {}).get(event_id, {}).get('scale') or 0.0)
    if base <= _EPS:
        return 1.0
    return float(placement.get('scale') or base) / base


def _candidate_rect(impl, event: dict, placement: dict, scale: float):
    fp = impl._fp(event)
    center = tuple(float(v) for v in placement['center_norm'])
    rect = impl._rect(center, fp, float(scale) * impl.MOTION_ENVELOPE_SCALE)
    return fp, rect


def _collision_safe(module, by_id: dict[str, dict], placements: dict[str, dict], event_id: str, scale: float) -> tuple[bool, list[float] | None]:
    impl = module._implementation
    event = by_id[event_id]
    fp, rect = _candidate_rect(impl, event, placements[event_id], scale)
    if not impl._in_safe(rect):
        return False, None
    for other_id, other in placements.items():
        if other_id == event_id:
            continue
        other_event = by_id.get(other_id)
        if other_event is None:
            continue
        other_fp, other_rect = _candidate_rect(impl, other_event, other, float(other['scale']))
        gap = impl.PRIMARY_GAP if (fp.primary or other_fp.primary) else impl.SUPPORT_GAP
        if impl._inter(impl._inflate(rect, gap), impl._inflate(other_rect, gap)) > 1e-8:
            return False, None
    return True, [round(float(v), 6) for v in rect]


def _scale_candidates(module, event: dict, current: float | None = None) -> list[float]:
    impl = module._implementation
    fp = impl._fp(event)
    values = {float(value) for value in impl._scale_candidates(fp, fp.primary)}
    if current is not None:
        values.add(float(current))
    return sorted(values)


def _annotate_factors(layout: dict, placements: dict[str, dict]) -> None:
    for event_id, placement in placements.items():
        placement['phase_scale_factor'] = round(_factor(layout, event_id, placement), 6)


def _joint_scale_rebalance(module, layout: dict, by_id: dict[str, dict], placements: dict[str, dict], focus_id: str) -> bool:
    """Jointly solve scales at fixed certified centers when one-sided edits cannot.

    The search is intentionally phase-local and bounded. It only uses scale candidates
    already accepted by the production solver, preserves every center, keeps protected
    geometry fixed, and certifies safe bounds plus pairwise motion-envelope gaps for the
    complete candidate combination before applying it atomically.
    """
    impl = module._implementation
    event_ids = list(placements)
    context_ids = [event_id for event_id in event_ids if event_id != focus_id]
    if focus_id not in by_id or not context_ids:
        return False

    stable = layout.get('placements') or {}
    current_scales = {event_id: float(placements[event_id]['scale']) for event_id in event_ids}
    stable_scales = {
        event_id: float((stable.get(event_id) or {}).get('scale') or current_scales[event_id])
        for event_id in event_ids
    }

    focus_row = placements[focus_id]
    if focus_row.get('phase_geometry_protected'):
        focus_candidates = [current_scales[focus_id]]
    else:
        focus_candidates = _scale_candidates(module, by_id[focus_id], current_scales[focus_id])

    best = None
    for focus_scale in focus_candidates:
        focus_factor = focus_scale / max(_EPS, stable_scales[focus_id])
        context_factor_ceiling = focus_factor - _MIN_FOCUS_FACTOR_GAP
        if context_factor_ceiling <= _EPS:
            continue

        per_context = []
        possible = True
        for event_id in context_ids:
            placement = placements[event_id]
            current = current_scales[event_id]
            if placement.get('phase_geometry_protected'):
                if current / max(_EPS, stable_scales[event_id]) > context_factor_ceiling + _EPS:
                    possible = False
                    break
                candidates = [current]
            else:
                ceiling = stable_scales[event_id] * context_factor_ceiling
                candidates = [
                    value for value in _scale_candidates(module, by_id[event_id], current)
                    if value <= ceiling + _EPS
                ]
                if not candidates:
                    possible = False
                    break
                # Keep the largest candidates first; lower scales are only fallbacks
                # for collision clearance, not a density shortcut.
                candidates = sorted(candidates, reverse=True)[:_MAX_CONTEXT_CANDIDATES]
            per_context.append(candidates)
        if not possible:
            continue

        for context_scales in itertools.product(*per_context):
            scale_by_id = {focus_id: focus_scale}
            scale_by_id.update(dict(zip(context_ids, context_scales)))
            rects = {}
            fps = {}
            safe = True
            visible_density = 0.0

            for event_id in event_ids:
                event = by_id.get(event_id)
                if event is None:
                    safe = False
                    break
                fp, rect = _candidate_rect(impl, event, placements[event_id], scale_by_id[event_id])
                if not impl._in_safe(rect):
                    safe = False
                    break
                fps[event_id] = fp
                rects[event_id] = rect
                visible_density += float(rect[2]) * float(rect[3]) * float(fp.fill)
            if not safe:
                continue

            for index, event_id in enumerate(event_ids):
                for other_id in event_ids[index + 1:]:
                    fp, other_fp = fps[event_id], fps[other_id]
                    gap = impl.PRIMARY_GAP if (fp.primary or other_fp.primary) else impl.SUPPORT_GAP
                    if impl._inter(impl._inflate(rects[event_id], gap), impl._inflate(rects[other_id], gap)) > 1e-8:
                        safe = False
                        break
                if not safe:
                    break
            if not safe:
                continue

            final_focus_factor = scale_by_id[focus_id] / max(_EPS, stable_scales[focus_id])
            final_context_factor = max(
                scale_by_id[event_id] / max(_EPS, stable_scales[event_id])
                for event_id in context_ids
            )
            if final_focus_factor - final_context_factor < _MIN_FOCUS_FACTOR_GAP - _EPS:
                continue

            deviation = sum(
                abs(math.log(max(_EPS, scale_by_id[event_id]) / max(_EPS, current_scales[event_id])))
                for event_id in event_ids
            )
            density_penalty = max(0.0, 0.24 - visible_density) * 18.0 + max(0.0, visible_density - 0.56) * 12.0
            excess_gap = max(0.0, final_focus_factor - final_context_factor - _MIN_FOCUS_FACTOR_GAP)
            score = deviation + density_penalty + excess_gap * 0.20
            candidate = (score, scale_by_id, rects)
            if best is None or candidate[0] < best[0] - _EPS:
                best = candidate

    if best is None:
        return False

    _, scale_by_id, rects = best
    changed = False
    for event_id in event_ids:
        new_scale = float(scale_by_id[event_id])
        if abs(new_scale - current_scales[event_id]) <= _EPS:
            continue
        placements[event_id]['scale'] = round(new_scale, 6)
        placements[event_id]['rect_norm'] = [round(float(v), 6) for v in rects[event_id]]
        placements[event_id]['material_focus_hierarchy_adjusted'] = 'JOINT_SCALE_REBALANCE'
        changed = True
    return changed


def install(module) -> None:
    """Install an idempotent post-certifier around ``solve_phase_layouts``."""
    if getattr(module, '_material_focus_hierarchy_contract_installed', False):
        return

    base_solve = module.solve_phase_layouts

    def solve_phase_layouts(events: list[dict], grammar: dict, phase_plan: dict) -> dict:
        layout = base_solve(events, grammar, phase_plan)
        if not layout.get('pass'):
            return layout

        phase_placements = layout.get('phase_placements') or {}
        if not phase_placements:
            return layout

        by_id = {
            str(event.get('event_id')): event
            for event in events
            if not event.get('suppressed_by_card_density')
        }
        phase_by_id = {
            str(phase.get('phase_id')): phase
            for phase in (phase_plan.get('phases') or [])
        }
        changed = 0
        unresolved = []

        for phase_id, placements in phase_placements.items():
            if not placements:
                continue
            _annotate_factors(layout, placements)
            phase = phase_by_id.get(str(phase_id)) or {}
            focus_id = str(phase.get('focus_event_id') or '')
            if focus_id not in placements or len(placements) < 2:
                continue

            context_ids = [event_id for event_id in placements if event_id != focus_id]
            focus_factor = _factor(layout, focus_id, placements[focus_id])
            context_max = max(_factor(layout, event_id, placements[event_id]) for event_id in context_ids)
            if focus_factor - context_max >= _MIN_FOCUS_FACTOR_GAP - _EPS:
                continue

            focus = placements[focus_id]
            focus_protected = bool(focus.get('phase_geometry_protected'))
            stable_focus_scale = float((layout.get('placements') or {}).get(focus_id, {}).get('scale') or focus['scale'])
            required_factor = context_max + _MIN_FOCUS_FACTOR_GAP
            required_scale = stable_focus_scale * required_factor

            # First try the smallest one-sided focus promotion that satisfies the gap.
            promoted = False
            if not focus_protected and focus_id in by_id:
                for candidate in _scale_candidates(module, by_id[focus_id], float(focus['scale'])):
                    if candidate <= float(focus['scale']) + _EPS:
                        continue
                    if candidate + _EPS < required_scale:
                        continue
                    safe, rect = _collision_safe(module, by_id, placements, focus_id, candidate)
                    if not safe:
                        continue
                    focus['scale'] = round(candidate, 6)
                    focus['rect_norm'] = rect
                    focus['material_focus_hierarchy_adjusted'] = 'PROMOTE_FOCUS'
                    promoted = True
                    changed += 1
                    break

            # When promotion cannot fit beside the current context, solve all phase
            # scales jointly at the existing certified centers. This is the key case
            # for a retained large context plus a newly entering payoff actor.
            if not promoted:
                before = {event_id: float(row['scale']) for event_id, row in placements.items()}
                if _joint_scale_rebalance(module, layout, by_id, placements, focus_id):
                    changed += sum(
                        1 for event_id, row in placements.items()
                        if abs(float(row['scale']) - before[event_id]) > _EPS
                    )

            _annotate_factors(layout, placements)
            final_focus = _factor(layout, focus_id, placements[focus_id])
            final_context = max(_factor(layout, event_id, placements[event_id]) for event_id in context_ids)
            if final_focus - final_context < _MIN_FOCUS_FACTOR_GAP - _EPS:
                unresolved.append({
                    'phase_id': str(phase_id),
                    'focus_event_id': focus_id,
                    'focus_factor': round(final_focus, 6),
                    'context_factor': round(final_context, 6),
                })

        layout['material_focus_hierarchy_adjustment_count'] = changed
        layout['material_focus_hierarchy_unresolved'] = unresolved
        layout['material_focus_hierarchy_authority'] = 'CERTIFIED_PHASE_SCALE_HIERARCHY_V2'
        return layout

    solve_phase_layouts.__name__ = base_solve.__name__
    solve_phase_layouts.__doc__ = base_solve.__doc__
    module.solve_phase_layouts = solve_phase_layouts
    module._material_focus_hierarchy_contract_installed = True
