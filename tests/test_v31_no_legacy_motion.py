from pathlib import Path
for name in ['preset_story_planner.py','visual_cards.py']:
    t=(Path(__file__).resolve().parents[1]/'extension/py/hexa_v31'/name).read_text()
    assert 'continuous_drift\':True' not in t
# Production override is intentionally after the old forensic renderer and never calls bridge.
s=(Path(__file__).resolve().parents[1]/'extension/py/hexa_v31/scene_media.py').read_text()
idx=s.rfind('def render_scene_media(');tail=s[idx:]
assert '_bridge(' not in tail and '_object_only_bridge(' not in tail
assert 'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND' in tail
print('V31_NO_LEGACY_MOTION_PASS')
