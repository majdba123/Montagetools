from __future__ import annotations

import copy
import pathlib
import tempfile

import numpy as np
from PIL import Image

from hexa_v31.extraction.asset_fidelity import ASSET_FIDELITY_AUTHORITY, certify_extracted_layers
from hexa_v31.planning.sequential_audio_reveal import AUTHORITY, audio_sequential_reveal_qa, finalize_audio_sequential_reveal


def _event(event_id: str, unit: str, *, end: float = 3.0, protected: bool = False, mode: str = 'ROOT_ATOMIC') -> dict:
    event = {
        'event_id': event_id,
        'scene_id': 'SCENE_TEST',
        'semantic_unit_id': unit,
        'render_mode': mode,
        'source_scene_start_seconds': 0.0,
        'source_scene_end_seconds': end,
        'start_seconds': 0.0,
        'end_seconds': end,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': end,
        'scene_ownership_start_seconds': 0.0,
        'scene_ownership_end_seconds': end,
        'card_rest_position_norm': [0.5, 0.5],
        'attention_priority': 'SUPPORTING',
    }
    if protected:
        event.update({'partition_complete': True, 'partition_root_id': 'ROOT_P', 'partition_group_id': 'GROUP_P'})
    return event


def _asset_fidelity_contract() -> None:
    with tempfile.TemporaryDirectory(prefix='hexa_asset_fidelity_') as td:
        root = pathlib.Path(td)
        source = np.full((48, 64, 3), 255, np.uint8)
        source[10:38, 0:28] = [20, 80, 180]
        rgba = np.zeros((48, 64, 4), np.uint8)
        rgba[:, :, :3] = 255
        rgba[10:38, 0:28, :3] = source[10:38, 0:28]
        rgba[10:38, 0:28, 3] = 255
        Image.fromarray(rgba, 'RGBA').save(root / 'layer.png')
        unit = {
            'physical_id': 'EDGE', 'layer_path': 'layer.png',
            'crop_origin_px': [4, 14], 'crop_size_px': [12, 10],
            'translation_safe_after_occlusion': True, 'animation_mode': 'TRANSLATE_SAFE',
            'matting': {'opaque_stage_leak_fraction': 0.0},
        }
        report = certify_extracted_layers([unit], source, root)
        assert report['pass'], report
        assert unit['asset_fidelity_authority'] == ASSET_FIDELITY_AUTHORITY
        assert unit['asset_fidelity_qa']['previous_crop_contained_alpha'] is False
        assert unit['asset_fidelity_qa']['alpha_bbox_px'] == [0, 10, 28, 38]
        assert unit['crop_origin_px'][0] == 0
        assert unit['translation_safe_after_occlusion'] is False
        assert unit['animation_mode'] == 'IN_PLACE_ACTING_ONLY'
        assert unit['asset_fidelity_qa']['opaque_source_rgb_mae'] == 0.0

        bad = copy.deepcopy(unit)
        bad['physical_id'] = 'LEAK'
        bad['matting'] = {'opaque_stage_leak_fraction': 0.01}
        rejected = certify_extracted_layers([bad], source, root)
        assert not rejected['pass'], rejected
        assert any('white-stage leak' in failure for failure in rejected['failures'])


def _audio_sequential_reveal_contract() -> None:
    primary = _event('A', 'UNIT_001')
    primary['attention_priority'] = 'PRIMARY'
    supporting = _event('B', 'UNIT_002')
    plan = {'fps': 30.0, 'events': [primary, supporting]}
    report = finalize_audio_sequential_reveal(plan, 30.0)
    assert report['pass'], report
    assert primary['audio_reveal_authority'] == AUTHORITY
    assert supporting['audio_reveal_authority'] == AUTHORITY
    assert supporting['audio_reveal_seconds'] - primary['audio_reveal_seconds'] >= 5 / 30 - 1e-6
    qa = audio_sequential_reveal_qa(plan, 30.0)
    assert qa['pass'] and qa['burst_count'] == 0 and qa['pre_audio_reveal_count'] == 0, qa

    first = _event('X1', 'UNIT_X')
    second = _event('X2', 'UNIT_X')
    later = _event('Z', 'UNIT_Z')
    later['attention_priority'] = 'PRIMARY'
    atomic = {'fps': 30.0, 'events': [first, second, later]}
    assert finalize_audio_sequential_reveal(atomic, 30.0)['pass']
    assert first['audio_reveal_seconds'] == second['audio_reveal_seconds']

    protected = _event('P', 'UNIT_P', protected=True, mode='CHILD_PARTITION')
    independent = _event('Q', 'UNIT_Q')
    independent['attention_priority'] = 'PRIMARY'
    partitioned = {'fps': 30.0, 'events': [protected, independent]}
    assert finalize_audio_sequential_reveal(partitioned, 30.0)['pass']
    assert 'audio_reveal_seconds' not in protected
    assert not any(state.get('envelope_track') == 'AUDIO_SEQUENTIAL_REVEAL' for state in protected.get('composition_participant_states') or [])

    short_a = _event('S1', 'U1', end=0.18)
    short_a['attention_priority'] = 'PRIMARY'
    short_b = _event('S2', 'U2', end=0.18)
    impossible = {'fps': 30.0, 'events': [short_a, short_b]}
    rejected = finalize_audio_sequential_reveal(impossible, 30.0)
    assert not rejected['pass']
    assert any('no legal sequential reveal window' in failure for failure in rejected['failures'])


def main() -> None:
    _asset_fidelity_contract()
    _audio_sequential_reveal_contract()
    print('V31_ASSET_FIDELITY_AUDIO_REVEAL_PASS')


if __name__ == '__main__':
    main()
