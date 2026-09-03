import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
pipeline = (root/'extension/py/hexa_v31/app/pipeline.py').read_text(encoding='utf-8')
media = (root/'extension/py/hexa_v31/render/scene_media.py').read_text(encoding='utf-8')
vision = (root/'extension/py/hexa_v31/vision/vision.py').read_text(encoding='utf-8')
assert 'animated_timeline_v31_0_25_typography_director_v3' in pipeline
assert 'HEXA_SCENE_MEDIA_V31_P2_REFERENCE_CHOREOGRAPHY' in media
assert "V31_0_26_FOUNDATION_PARTITION_STORY.mp4" in media
assert "HEXA_SCENE_MEDIA_V31_RENDERER_AUTHORITY_3_FOUNDATION_PARTITION_CHOREOGRAPHY" in media
assert "V31_0_25_GLOBAL_STORY.mp4" not in media
assert "'vision':'VISION_10.1_FOUNDATION_CROP_INDEPENDENCE_CERTIFIED'" in vision
assert "'actor_qa':ACTOR_QA_VERSION" in vision
assert "'foundation_reconstruction':FOUNDATION_RECONSTRUCTION_VERSION" in vision
print('V31_0_9_CACHE_INVALIDATION_PASS')
