"""Typography layer and compatibility exports for ``hexa_v31.typography``."""
from . import typography as _implementation
from .round2_editorial import install as _install_round2_typography
_install_round2_typography(_implementation)
globals().update({key: value for key, value in vars(_implementation).items() if not key.startswith('__')})

# Premium V31 art direction is intentionally a narrow overlay above the literal-copy
# planner. It preserves source grounding and all compatibility exports while making
# viewer-facing selection/lifetime/render treatment materially production quality.
# V2 adds a distinct HERO/title treatment while retaining the V1 copy-quality gate.
from .premium_v2 import build_text_plan as build_text_plan, render_text_rgba as render_text_rgba
