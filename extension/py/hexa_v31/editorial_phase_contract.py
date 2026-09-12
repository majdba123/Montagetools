"""Shipping contract for material phase focus hierarchy.

The semantic planner may correctly name a focus actor while a collision-safe phase
solve leaves focus and context at the same relative scale.  That is metadata-only
focus and does not satisfy the viewer-facing editorial contract.  This compatibility
layer post-certifies phase geometry without changing actor lifetimes, source identity,
or protected P1 partition geometry.
"""
from __future__ import annotations

import copy

_MIN_FOCUS_FACTOR_GAP = 0.10
_EPS = 1e-9


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


def _scale_candidates(module, event: dict) -> list[float]:
    impl = module._implementation
    fp = impl._fp(event)
    return sorted({float(value) for value in impl._scale_candidates(fp, fp.primary)})


def _annotate_factors(layout: dict, placements: dict[str, dict]) -> None:
    for event_id, placement in placements.items():
        placement['phase_scale_factor'] = round(_factor(layout, event_id, placement), 6)


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

            # Prefer enlarging the semantic focus.  Candidate scales come from the
            # existing source/geometry solver; every candidate is then checked against
            # the exact phase-local safe bounds and collision envelope.
            promoted = False
            if not focus_protected and focus_id in by_id:
                for candidate in _scale_candidates(module, by_id[focus_id]):
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

            # If promotion is geometrically impossible, demote only unprotected
            # context, choosing the largest certified candidate that satisfies the
            # hierarchy.  Shrinking context cannot create a new collision, but the
            # same certification is still run so the contract is explicit.
            if not promoted:
                focus_factor = _factor(layout, focus_id, focus)
                max_context_factor = focus_factor - _MIN_FOCUS_FACTOR_GAP
                if max_context_factor > _EPS:
                    for event_id in context_ids:
                        placement = placements[event_id]
                        if placement.get('phase_geometry_protected') or event_id not in by_id:
                            continue
                        current_factor = _factor(layout, event_id, placement)
                        if current_factor <= max_context_factor + _EPS:
                            continue
                        stable_scale = float((layout.get('placements') or {}).get(event_id, {}).get('scale') or placement['scale'])
                        ceiling = stable_scale * max_context_factor
                        candidates = [value for value in _scale_candidates(module, by_id[event_id]) if value <= ceiling + _EPS]
                        for candidate in sorted(candidates, reverse=True):
                            safe, rect = _collision_safe(module, by_id, placements, event_id, candidate)
                            if not safe:
                                continue
                            placement['scale'] = round(candidate, 6)
                            placement['rect_norm'] = rect
                            placement['material_focus_hierarchy_adjusted'] = 'DEMOTE_CONTEXT'
                            changed += 1
                            break

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
        layout['material_focus_hierarchy_authority'] = 'CERTIFIED_PHASE_SCALE_HIERARCHY_V1'
        return layout

    solve_phase_layouts.__name__ = base_solve.__name__
    solve_phase_layouts.__doc__ = base_solve.__doc__
    module.solve_phase_layouts = solve_phase_layouts
    module._material_focus_hierarchy_contract_installed = True
