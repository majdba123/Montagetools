"""Round 3 shared transition-curve delivery.

Installs reference-preset timing into the canonical composition-state evaluator.  The
state still owns collision-certified endpoints; this module only selects the installed
preset's progress curve when a state explicitly names one.
"""
from __future__ import annotations

from hexa_v31.preset_authority import progress as preset_progress


def install(impl) -> None:
    if getattr(impl, '_round3_transition_installed', False):
        return

    def composition_destinations_at(states, t, center):
        scale = 1.0
        visibility = 1.0
        states = sorted(states, key=lambda x: (float(x.get('start_seconds', 0)), str(x.get('state_id') or '')))
        previous = {'center_norm': center, 'scale_multiplier': scale, 'visibility': visibility}
        for state in states:
            start = float(state.get('start_seconds', 0))
            transition = max(0.0, float(state.get('transition_duration_seconds') or 0.0))
            if t < start:
                break
            target_center = list(state.get('center_norm') or previous['center_norm'])
            target_scale = float(state.get('scale_multiplier', previous['scale_multiplier']))
            target_visibility = float(state.get('visibility', previous['visibility']))
            if transition > 1e-9 and t < start + transition:
                q = max(0.0, min(1.0, (t - start) / transition))
                transition_preset = str(state.get('transition_preset_name') or '')
                q = preset_progress(transition_preset, q) if transition_preset else q * q * (3.0 - 2.0 * q)
                center = [
                    float(previous['center_norm'][0]) + (float(target_center[0]) - float(previous['center_norm'][0])) * q,
                    float(previous['center_norm'][1]) + (float(target_center[1]) - float(previous['center_norm'][1])) * q,
                ]
                scale = float(previous['scale_multiplier']) + (target_scale - float(previous['scale_multiplier'])) * q
                visibility = float(previous['visibility']) + (target_visibility - float(previous['visibility'])) * q
                return center, scale, visibility
            center = [float(target_center[0]), float(target_center[1])]
            scale = target_scale
            visibility = target_visibility
            previous = {'center_norm': center, 'scale_multiplier': scale, 'visibility': visibility}
        return center, scale, visibility

    impl._composition_destinations_at = composition_destinations_at
    impl._round3_transition_installed = True
