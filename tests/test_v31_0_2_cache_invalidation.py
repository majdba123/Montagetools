import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
pipeline = (root/'extension/py/hexa_v31/pipeline.py').read_text(encoding='utf-8')
media = (root/'extension/py/hexa_v31/scene_media.py').read_text(encoding='utf-8')
vision = (root/'extension/py/hexa_v31/vision.py').read_text(encoding='utf-8')
assert 'animated_timeline_v31_0_25_typography_director_v3' in pipeline
assert 'HEXA_SCENE_MEDIA_V31_P2_REFERENCE_CHOREOGRAPHY' in media
assert "V31_0_25_GLOBAL_STORY.mp4" in media
assert "V31_0_1_GLOBAL_STORY.mp4" not in media
assert "'algorithm':'HEXA_V31_VISION_10.0_SAFE_HIERARCHICAL_ASSET_DECOMPOSER'" in vision
print('V31_0_9_CACHE_INVALIDATION_PASS')
