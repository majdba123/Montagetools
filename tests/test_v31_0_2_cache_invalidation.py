import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
pipeline = (root/'extension/py/hexa_v31/pipeline.py').read_text(encoding='utf-8')
media = (root/'extension/py/hexa_v31/scene_media.py').read_text(encoding='utf-8')
vision = (root/'extension/py/hexa_v31/vision.py').read_text(encoding='utf-8')
assert 'animated_timeline_v31_0_20_readable_state_lifecycle_compiler' in pipeline
assert 'HEXA_SCENE_MEDIA_V31_0_9_SEMANTIC_PHASE_REPARTITION_COMPILER' in media
assert "V31_0_9_GLOBAL_STORY.mp4" in media
assert "V31_0_1_GLOBAL_STORY.mp4" not in media
assert "'algorithm':'HEXA_V31_VISION_9.0_LOCAL_STAGE_LEAK_REPAIR_TOP_LEVEL_ONLY'" in vision
print('V31_0_9_CACHE_INVALIDATION_PASS')
