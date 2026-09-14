import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from hexa_v31.composition_solver import _fp, _rect, composition_state_at
from hexa_v31.composition_qa import composition_plan_qa, _state
from hexa_v31.layout.reference_staggered_sequence import finalize_reference_staggered_sequence
from hexa_v31.interaction.director import finalize_interaction_motion_plan, assert_final_motion_plan_immutable
from hexa_v31.render.scene_media import _composition_cache_signature, render_scene_media


def fixture(root, count=2, duration=5.):
    events=[]
    for i,(x,y,w,h) in enumerate([(.28,.5,.27,.50),(.72,.30,.22,.28),(.72,.72,.20,.24)][:count]):
        path=root/f'{i}.png'
        image=Image.new('RGBA',(round(w*1920),round(h*1080)),(35+i*50,50,120,255))
        draw=ImageDraw.Draw(image);draw.rectangle((20,20,image.width-20,image.height-20),outline='white',width=12)
        image.save(path)
        e=dict(event_id=f'ACTOR_{i}',scene_id='SOURCE',visual_card_id='CARD',source_path=str(path),
            source_bbox_norm=[0,0,w,h],visible_ink_fraction=1.,base_fit_scale_percent=100,
            render_mode='ROOT_ATOMIC',attention_priority='PRIMARY' if i==0 else 'SUPPORTING',
            semantic_role=['LEAD','SUPPORT','CONTEXT'][i],card_rest_position_norm=[x,y],layout_scale_multiplier=1.,
            start_seconds=0.,end_seconds=duration,physical_start_seconds=0.,physical_end_seconds=duration,
            motion_start_seconds=0.,motion_end_seconds=duration,settle_seconds=.3,
            preset_entry=dict(name='APPEAR_HIGH_SCALE',start_seconds=0.,duration_seconds=.3),
            preset_actions=[],preset_exit=None,animation_safe=False,translation_safe_after_occlusion=False)
        e['planned_rect_norm']=list(_rect((x,y),_fp(e),1.12));events.append(e)
    return dict(fps=30.,events=events,scenes=[dict(start_seconds=0.,end_seconds=duration)],
        visual_cards=dict(cards=[dict(card_id='CARD',start_seconds=0.,end_seconds=duration,
            story_phase_plan=dict(phases=[dict(phase_id='PHASE',start_seconds=0.,end_seconds=duration,event_ids=[e['event_id'] for e in events])]))]))


with tempfile.TemporaryDirectory() as raw:
    root=Path(raw)
    for count in (2,3):
        plan=fixture(root,count);baseline=copy.deepcopy(plan)
        stats=finalize_reference_staggered_sequence(plan)
        assert stats['changed'],stats
        sequence=stats['sequences'][0]
        assert sequence['reveal_onsets']==sorted(set(sequence['reveal_onsets']))
        assert sequence['overlap_interval'][1]-sequence['overlap_interval'][0]>=.65
        assert sequence['after_static_hold_estimate']<sequence['before_static_hold_estimate']-.10,sequence
        assert sequence['after_simultaneous_actor_population']['max_population']==count
        for result in sequence['encoded_attribution_expectation']['attribution']:
            assert result['actor_attributable_pass'] and result['attributed_changed_pixel_ratio']>=.012,result
        incoming=sequence['reveal_onsets'][1]
        assert _state(plan['events'][1],incoming-.01)[2]==0
        for t in np.arange(incoming+.65,incoming+1.3,1/30):
            assert all(_state(e,float(t))[2]>.22 for e in plan['events'][:2])
        assert composition_plan_qa(plan)['pass'],composition_plan_qa(plan)
        for e in plan['events']:
            for t in np.arange(0,5,1/30):
                assert composition_state_at(e,float(t))[0]==e['card_rest_position_norm']
        repeat=copy.deepcopy(baseline)
        assert finalize_reference_staggered_sequence(repeat)==stats
        assert repeat==plan
        # Existing P2 actions/entry/exit and all lifetimes remain exact.
        for a,b in zip(baseline['events'],plan['events']):
            for key in ('preset_entry','preset_actions','preset_exit','physical_start_seconds','physical_end_seconds'):
                assert a[key]==b[key]
        signed=finalize_interaction_motion_plan(plan)
        assert_final_motion_plan_immutable(signed)
        loaded=json.loads(json.dumps(signed));assert_final_motion_plan_immutable(loaded)
        sig=_composition_cache_signature({'events':loaded['events']})
        loaded['events'][0]['composition_states'][-1]['scale_multiplier']+=.01
        assert sig!=_composition_cache_signature({'events':loaded['events']})
        try:assert_final_motion_plan_immutable(loaded)
        except ValueError:pass
        else:raise AssertionError('Unsealed sequence mutation')
        # Final plan -> renderer -> short encoded MP4, using the real source.
        manifest=render_scene_media({'events':signed['events']},signed,[],{'events':[]},{'events':[]},
            root/f'out{count}',root/f'cache{count}',width=320,height=180,fps=30)
        ffmpeg=os.environ.get('HEXA_FFMPEG') or shutil.which('ffmpeg')
        assert ffmpeg, 'FFmpeg executable is required for staggered encoded attribution test'
        encoded=subprocess.check_output([ffmpeg,'-v','error','-i',manifest['clips'][0]['source_path'],
            '-vf','fps=4,scale=320:180:flags=area','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        frames=np.frombuffer(encoded,np.uint8).reshape(-1,180,320,3)
        motion=(np.abs(np.diff(frames.astype(np.int16),axis=0)).max(axis=3)>13).mean(axis=(1,2))
        assert float((motion<.005).mean())<sequence['before_static_hold_estimate']-.10
        assert motion.max()>=.012
        from hexa_v31.layout.encoded_composition_qa import verify_encoded_composition
        qa=verify_encoded_composition(manifest['clips'][0]['source_path'],signed,render_edit_map={'events':signed['events']})
        assert qa['pass'] and qa['actor_attributable_verified_count']>=2,qa
    causal=fixture(root)
    long_idea=fixture(root,3,duration=12.)
    long_stats=finalize_reference_staggered_sequence(long_idea)
    assert long_stats['changed'],long_stats
    sentence=long_stats['sequences'][0]
    assert sentence['reveal_onsets'][2]>4.,sentence
    assert sentence['focus_transfer_interval'][0]>6.,sentence
    assert sentence['recomposition_interval'][0]>9.,sentence
    assert .45 <= sentence['handoff_interval'][1]-sentence['handoff_interval'][0] <= 1.,sentence
    assert composition_plan_qa(long_idea)['pass']
    causal['events'][0]['preset_entry']['interaction_id']='EXPLICIT_CAUSE'
    original=copy.deepcopy(causal)
    assert finalize_reference_staggered_sequence(causal)['changed']
    assert causal['events'][0]['preset_entry']==original['events'][0]['preset_entry']
    for t in (.05,.1,.2):
        assert _state(causal['events'][0],t)[2]==_state(original['events'][0],t)[2]
    # Guards are tested against exact event bytes, not just mutation counts.
    for kind in ('travel','partition','unrelated','split_phase','short','single','collision','weak'):
        p=fixture(root,1 if kind=='single' else 2,duration=1. if kind=='short' else 5.)
        if kind=='travel':p['events'][1]['position_animated']=True
        if kind=='partition':p['events'][1]['render_mode']='CHILD_PARTITION'
        if kind=='unrelated':
            p['events'][1]['scene_id']='OTHER'
            p['visual_cards']['cards'][0]['story_phase_plan']['phases'][0]['event_ids']=['ACTOR_0']
        if kind=='split_phase':
            p['visual_cards']['cards'][0]['story_phase_plan']['phases']=[
                dict(phase_id='FIRST',event_ids=['ACTOR_0']),dict(phase_id='SECOND',event_ids=['ACTOR_1'])]
        if kind=='weak':
            for e in p['events']:Image.new('RGBA',(20,20),'white').save(e['source_path'])
        before=copy.deepcopy(p)
        if kind=='collision':
            with patch('hexa_v31.layout.reference_staggered_sequence._candidate_safe',return_value=False):
                result=finalize_reference_staggered_sequence(p)
        else:result=finalize_reference_staggered_sequence(p)
        assert not result['changed'] and p==before,(kind,result)
        if kind=='single':assert result['source_limited_card_ids']==['CARD']
print('V31_REFERENCE_STAGGERED_SEQUENCE_PIXEL_CONTRACT_PASS')
