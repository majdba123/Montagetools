from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from hexa_v31.layout.composition_attribution import attribute_composition, _gray_actor
from hexa_v31.layout.encoded_composition_qa import _authored_states, _exact_sample_metrics
from hexa_v31.render.scene_media import prepare_composition_actor


def actor(eid: str, x: float, path: Path) -> dict:
    return {
        'event_id': eid,
        'physical_id': eid,
        'scene_id': 'S1',
        'visual_card_id': 'C1',
        'source_path': str(path),
        'base_fit_scale_percent': 100.0,
        'source_bbox_norm': [0.0, 0.0, .22, .28],
        'planned_rect_norm': [x-.11, .36, .22, .28],
        'collision_envelope_rect_norm': [x-.11, .36, .22, .28],
        'render_mode': 'ROOT_ATOMIC',
        'attention_priority': 'PRIMARY' if eid == 'OWNER' else 'SUPPORTING',
        'semantic_type': 'CONCEPT',
        'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': [x, .5],
        'start_seconds': 0.0,
        'end_seconds': 2.0,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 2.0,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 2.0,
        'settle_seconds': 0.0,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'composition_states': [],
        'composition_participant_states': [],
    }


with tempfile.TemporaryDirectory(prefix='hexa_p34_encoded_contract_') as raw:
    root=Path(raw)
    source=root/'actor.png'
    Image.new('RGBA',(600,500),(45,90,180,255)).save(source)

    owner=actor('OWNER',.26,source)
    participant=actor('PARTICIPANT',.70,source)
    participant['composition_participant_states']=[
        {
            'state_id':'PARTICIPANT::A','owner_state_id':'OWNER::FOCUS',
            'start_seconds':0.0,'transition_duration_seconds':0.0,
            'center_norm':[.70,.5],'scale_multiplier':1.0,'visibility':1.0,
            'sequence_envelope':True,'envelope_track':'SEMANTIC_SEQUENCE',
            'participating_event_ids':['OWNER','PARTICIPANT'],
        },
        {
            'state_id':'PARTICIPANT::B','owner_state_id':'OWNER::FOCUS',
            'previous_state_id':'PARTICIPANT::A',
            'start_seconds':1.0,'transition_duration_seconds':.4,
            'center_norm':[.70,.5],'scale_multiplier':1.45,'visibility':1.0,
            'sequence_envelope':True,'envelope_track':'SEMANTIC_SEQUENCE',
            'semantic_beat':'FOCUS_TRANSFER',
            'participating_event_ids':['OWNER','PARTICIPANT'],
        },
    ]

    motion={'events':[owner,participant]}
    authored=_authored_states(motion)
    assert len(authored)==1,authored
    assert authored[0][0]['event_id']=='PARTICIPANT'
    assert authored[0][2]=='composition_participant_states'

    frames=[np.full((360,640),255,dtype=np.uint8) for _ in range(2)]
    for event in (owner,participant):
        runtime,image=prepare_composition_actor(event,640,360)
        for index,t in enumerate((.8,1.6)):
            np.minimum(frames[index],_gray_actor(runtime,image,t,640,360),out=frames[index])
    state=participant['composition_participant_states'][1]
    attribution=attribute_composition(
        participant,state,frames[0],frames[1],(.8,1.6),{'events':[owner,participant]})
    assert attribution['actor_attributable_pass'],attribution
    assert attribution['owner_delta']>.003,attribution
    assert attribution['attributed_changed_pixel_ratio']>=.012,attribution

    exact=_exact_sample_metrics([.26,.25,.24,.23],[.14,.15,.16])
    assert exact['occupancy_mean']>=.24,exact
    assert exact['occupancy_median']>=.20,exact
    assert exact['frames_lt10_ratio']==0.0,exact
    assert exact['frames_lt15_ratio']==0.0,exact
    assert .13<=exact['motion_mean']<=.20,exact
    assert exact['near_static_ratio']==0.0,exact

print('V31_P34_ENCODED_CLOSURE_CONTRACT_PASS')
