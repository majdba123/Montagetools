from __future__ import annotations

import importlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from PIL import Image, ImageDraw


vision_module = importlib.import_module('hexa_v31.vision.vision')


with tempfile.TemporaryDirectory(prefix='hexa_vision_cache_') as raw:
    root = Path(raw)
    image_path = root / 'SCENE_TEST.png'
    image = Image.new('RGB', (320, 180), 'white')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 35, 250, 155), radius=18, fill=(45, 135, 220), outline=(20, 30, 45), width=6)
    draw.rectangle((110, 70, 210, 120), fill='white', outline=(20, 30, 45), width=5)
    image.save(image_path)
    scene = {
        'scene_id': 'SCENE_TEST',
        'units': [{'unit_id': 'UNIT_001', 'semantic_name': 'fixture', 'type': 'CONCEPT', 'role': 'PRIMARY'}],
    }
    cache_root = root / 'scene_vision'
    alignment_cache = root / 'alignment_cache_v20.json'
    alignment_cache.write_text('{"sentinel":"preserve"}\n', encoding='utf-8')

    generated = vision_module.analyze_scene(scene, image_path, cache_root)
    assert generated.cache_state['status'] == 'GENERATED', generated.cache_state
    hit = vision_module.analyze_scene(scene, image_path, cache_root)
    assert hit.cache_state['status'] == 'HIT', hit.cache_state

    damaged = Path(hit.artifacts['layers'][0]['path'])
    payload = damaged.read_bytes()
    damaged.write_bytes(payload[:len(payload)//2])
    assert not vision_module._cache_artifacts_complete({'artifacts': hit.artifacts})
    repaired = vision_module.analyze_scene(scene, image_path, cache_root)
    assert repaired.cache_state['status'] != 'HIT'
    assert vision_module._cache_artifacts_complete({'artifacts': repaired.artifacts})
    assert alignment_cache.read_text(encoding='utf-8') == '{"sentinel":"preserve"}\n'

    from hexa_v31.interaction.source_framing import normalize_render_sources
    from hexa_v31.image_cache import cached_image_complete
    source = root/'padded.png'
    padded=Image.new('RGBA',(320,180),'white')
    ImageDraw.Draw(padded).rectangle((130,60,190,120),fill='blue')
    padded.save(source)
    render_map={'events':[{'event_id':'fixture','source_path':str(source),
                          'planned_rect_norm':[.2,.2,.3,.3],'render_mode':'ROOT_ATOMIC'}]}
    framed,_=normalize_render_sources(render_map,root/'framing')
    crop=Path(framed['events'][0]['source_path'])
    assert crop != source
    original=crop.read_bytes()
    crop.write_bytes(original[:len(original)//2])
    assert not cached_image_complete(crop)
    reframed,_=normalize_render_sources(render_map,root/'framing')
    assert reframed['events'][0]['source_path']==str(crop)
    assert cached_image_complete(crop) and crop.read_bytes()==original
    assert list(crop.parent.glob('*.png'))==[crop]

    from hexa_v31.image_cache import save_cached_image
    real_save=Image.Image.save
    attempts=[]
    def short_first_write(image, stream, **kwargs):
        attempts.append(1)
        if len(attempts)==1:
            stream.write(b'broken PNG')
        else:
            real_save(image,stream,**kwargs)
    with patch.object(Image.Image,'save',short_first_write):
        save_cached_image(padded,crop)
    assert len(attempts)==2 and cached_image_complete(crop,padded.size)
    preserved=crop.read_bytes()
    with patch.object(Image.Image,'save',side_effect=OSError('write failed')):
        try:
            save_cached_image(padded,crop)
            raise AssertionError('persistent write failure accepted')
        except OSError:
            pass
    assert crop.read_bytes()==preserved
    assert list(crop.parent.glob('*.png'))==[crop]

    for dependency in ('vision', 'extraction_matting', 'hierarchy_decomposition', 'occlusion', 'foundation_reconstruction', 'actor_qa'):
        scene_dir = cache_root / scene['scene_id']
        stale_phys = scene_dir / 'PHYS_99.png'
        stale_phys.write_bytes(b'stale')
        vision_json = json.loads((scene_dir / 'vision.json').read_text(encoding='utf-8'))
        vision_json['stale_vision_marker'] = dependency
        vision_json['artifacts']['matting_summary']['stale_matting_marker'] = dependency
        (scene_dir / 'vision.json').write_text(json.dumps(vision_json), encoding='utf-8')

        old_value = vision_module.VISION_CACHE_DEPENDENCIES[dependency]
        vision_module.VISION_CACHE_DEPENDENCIES[dependency] = old_value + '__TEST_CHANGE'
        refreshed = vision_module.analyze_scene(scene, image_path, cache_root)
        assert refreshed.cache_state['status'] == 'INVALIDATED_DEPENDENCY_CHANGED', (dependency, refreshed.cache_state)
        assert not stale_phys.exists(), f'stale physical layer survived {dependency} invalidation'
        refreshed_json = json.loads((scene_dir / 'vision.json').read_text(encoding='utf-8'))
        assert 'stale_vision_marker' not in refreshed_json
        assert 'stale_matting_marker' not in refreshed_json['artifacts']['matting_summary']
        assert not list(cache_root.glob('.SCENE_TEST.stage-*')), 'atomic staging directory survived'
        assert not list(cache_root.glob('.SCENE_TEST.backup-*')), 'atomic backup directory survived'

    changed_scene = dict(scene)
    changed_scene['units'] = [dict(scene['units'][0], semantic_name='changed fixture')]
    input_miss = vision_module.analyze_scene(changed_scene, image_path, cache_root)
    assert input_miss.cache_state['status'] == 'MISS_INPUT_CHANGED', input_miss.cache_state
    assert alignment_cache.read_text(encoding='utf-8') == '{"sentinel":"preserve"}\n'

pipeline_source = (Path(__file__).resolve().parents[1] / 'extension' / 'py' / 'hexa_v31' / 'app' / 'pipeline.py').read_text(encoding='utf-8')
assert "cache_state=(vr.get('cache_state') or {}).get('status')" in pipeline_source
assert "'SCENE_VISION_CACHE_HIT'" in pipeline_source
assert "'SCENE_VISION_CACHE_INVALIDATED'" in pipeline_source
assert "'SCENE_VISION_ANALYZED'" in pipeline_source

print('V31_SCENE_VISION_CACHE_DEPENDENCIES_PASS')
