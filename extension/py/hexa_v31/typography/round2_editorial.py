"""Round 2 role-specific typography motion refinement."""
from __future__ import annotations
import copy

_PROFILES = {
    'HERO': (.90, 1.08, .090, .036, .50),
    'RESULT': (.89, 1.075, .105, .034, .52),
    'VALUE': (.90, 1.085, .092, .040, .50),
    'WARNING': (.93, 1.045, .080, .052, .42),
    'STATUS': (.95, 1.035, .070, .032, .40),
    'KEYWORD': (.93, 1.055, .078, .028, .46),
    'COMPARISON_LABEL': (.95, 1.035, .072, .026, .44),
    'MICRO_LABEL': (.97, 1.020, .052, .020, .36),
}


def install(impl) -> None:
    if getattr(impl, '_round2_typography_installed', False):
        return
    base = impl.build_text_plan

    def build_text_plan(*args, **kwargs):
        plan = base(*args, **kwargs)
        if not plan:
            return plan
        out = copy.deepcopy(plan)
        for event in out.get('events') or []:
            role = str(event.get('typography_role') or event.get('semantic_role') or 'KEYWORD').upper()
            pop_from, pop_peak, dx_amp, dy_amp, entry = _PROFILES.get(role, (.95, 1.04, .070, .026, .44))
            slot = str(event.get('slot') or '')
            sx = dx_amp if 'LEFT' in slot else (-dx_amp if 'RIGHT' in slot else float(event.get('slide_dx_norm') or 0.0))
            sy = dy_amp if 'TOP' in slot else (-dy_amp if 'BOTTOM' in slot else float(event.get('slide_dy_norm') or 0.0))
            event['pop_scale_from'] = pop_from
            event['pop_scale_peak'] = pop_peak
            event['pop_scale_end'] = 1.0
            event['slide_dx_norm'] = round(sx, 6)
            event['slide_dy_norm'] = round(sy, 6)
            event['slide_duration_seconds'] = round(min(float(event.get('slide_duration_seconds') or entry), entry), 6)
            readable = max(.72, min(1.10, float(event.get('end_seconds', 0)) - float(event.get('settle_seconds', 0))))
            event['read_sweep_dx_norm'] = round(-sx * .18, 6)
            event['read_sweep_dy_norm'] = round(-sy * .14, 6)
            event['read_sweep_duration_seconds'] = round(readable, 6)
            event['editorial_typography_motion_authority'] = 'ROLE_DISTINCT_BEAT_MOTION_V1'
        out['editorial_typography_motion_authority'] = 'ROLE_DISTINCT_BEAT_MOTION_V1'
        return out

    impl.build_text_plan = build_text_plan
    impl._round2_typography_installed = True
