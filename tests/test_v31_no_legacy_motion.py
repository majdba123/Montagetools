import ast
from pathlib import Path
for name in ['preset_story_planner.py','visual_cards.py']:
    t=(Path(__file__).resolve().parents[1]/'extension/py/hexa_v31'/name).read_text()
    assert 'continuous_drift\':True' not in t
# The continuous renderer is the sole public production entrypoint.  The
# forensic per-scene implementation may exist only as an explicitly private helper.
s=(Path(__file__).resolve().parents[1]/'extension/py/hexa_v31/render/scene_media.py').read_text()
tree=ast.parse(s)
public=[node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=='render_scene_media']
assert public==['render_scene_media'],public
assert '_render_scene_media_per_scene_legacy' in s
idx=s.index('def render_scene_media(');tail=s[idx:]
assert '_bridge(' not in tail and '_object_only_bridge(' not in tail
assert 'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND' in tail
assert 'inspect.getsource(render_scene_media)' in tail
print('V31_SINGLE_PRODUCTION_RENDERER_PASS')
