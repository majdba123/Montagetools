from __future__ import annotations
import pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
core=[
    ROOT/'extension/py/hexa_v31/story/scene_grammar.py',
    ROOT/'extension/py/hexa_v31/layout/composition_solver.py',
    ROOT/'extension/py/hexa_v31/layout/composition_qa.py',
    ROOT/'extension/py/hexa_v31/planning/preset_story_planner.py',
]
for p in core:
    s=p.read_text(encoding='utf-8')
    assert 'INSUFFICIENT_BALANCE' not in s
    assert 'HEXA_INSUFFICIENT' not in s
    # No instance-specific scene-ID branches are allowed in universal composition logic.
    assert not re.search(r'(?i)\b(if|elif)\b[^\n]*SCENE_[0-9]{3}',s),p
print('V31_NO_PROJECT_HARDCODING_PASS')
