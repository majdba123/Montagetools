import copy
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from hexa_v31.layout.composition_attribution import attribute_composition,_gray_actor
from hexa_v31.render.scene_media import prepare_composition_actor


with tempfile.TemporaryDirectory() as raw:
    path=Path(raw)/'actor.png'
    Image.new('RGBA',(480,400),(35,70,140,255)).save(path)
    def actor(eid,x):
        return {'event_id':eid,'source_path':str(path),'base_fit_scale_percent':100,
            'source_bbox_norm':[0,0,.25,400/1080],'planned_rect_norm':[x-.125,.5-200/1080,.25,400/1080],
            'render_mode':'ROOT_ATOMIC','attention_priority':'PRIMARY','semantic_type':'CONCEPT',
            'layout_scale_multiplier':1,'card_rest_position_norm':[x,.5],
            'start_seconds':0,'end_seconds':3,'physical_start_seconds':0,'physical_end_seconds':3,
            'motion_start_seconds':0,'motion_end_seconds':3,'settle_seconds':0,
            'preset_entry':None,'preset_exit':None,'preset_actions':[],
            'composition_states':[{'state_id':eid+'::A','start_seconds':0,'center_norm':[x,.5]},
                {'state_id':eid+'::B','start_seconds':1,'transition_duration_seconds':.4,
                 'center_norm':[1-x,.5],'participating_event_ids':[eid]}]}
    def frames(events):
        pair=[np.full((360,640),255,dtype=np.uint8) for _ in range(2)]
        for e in events:
            runtime,image=prepare_composition_actor(e,640,360)
            for i,t in enumerate((.8,1.6)):
                np.minimum(pair[i],_gray_actor(runtime,image,t,640,360),out=pair[i])
        return pair
    owner=actor('FOCUS',.25)
    def check(events,focus=owner):
        before,after=frames(events)
        return attribute_composition(focus,focus['composition_states'][1],before,after,(.8,1.6),{'events':events})
    positive=check([owner]);assert positive['actor_attributable_pass'],positive
    # A full-frame change from another actor cannot certify a static owner,
    # even when that motion crosses the owner's own ROI.
    held=copy.deepcopy(owner);held['composition_states'][1]['center_norm']=[.25,.5]
    unrelated=actor('OTHER',.75)
    negative=check([held,unrelated],held)
    assert not negative['actor_attributable_pass'] and negative['owner_delta']==0,negative
    assert negative['unrelated_delta']>0,negative
    # Opaque unrelated artwork covering a genuinely moving owner is not proof
    # that the owner's authored change survived into encoded pixels.
    covering=actor('COVER',.5);covering['layout_scale_multiplier']=4
    covering['composition_states'][1]['center_norm']=[.5,.5]
    obscured=check([owner,covering]);assert not obscured['actor_attributable_pass'],obscured
    before,after=frames([owner])
    missing=attribute_composition(owner,owner['composition_states'][1],before,after,(.8,1.6),None)
    assert not missing['actor_attributable_pass'],missing
    # Ordinary preset motion alone, with a no-op composition destination,
    # cannot earn composition credit.
    assert all(r['authored_state_delta']==0 for r in negative['actors']),negative
    mismatched=copy.deepcopy(owner);mismatched['composition_states'][1]['center_norm']=[.5,.5]
    mismatch=attribute_composition(owner,owner['composition_states'][1],before,after,(.8,1.6),{'events':[mismatched]})
    assert mismatch['attribution_failure']=='PLANNER_RENDER_COMPOSITION_STATE_MISMATCH',mismatch
    # A real encoded short handoff must be inspected while its actors exist.
    # The unchanged full-frame sample is deliberately after physical retirement.
    from hexa_v31.render.scene_media import render_scene_media
    from hexa_v31.layout.encoded_composition_qa import verify_encoded_composition
    short=copy.deepcopy(owner)
    short['end_seconds']=short['physical_end_seconds']=short['motion_end_seconds']=1.4
    replacement=actor('REPLACEMENT',.5);replacement['composition_states']=[]
    replacement['start_seconds']=replacement['physical_start_seconds']=replacement['motion_start_seconds']=1.4
    replacement['end_seconds']=replacement['physical_end_seconds']=replacement['motion_end_seconds']=2.
    edit={'events':[short,replacement]}
    motion={**edit,'scenes':[{'start_seconds':0,'end_seconds':2}],
        'visual_cards':{'cards':[{'card_id':'SHORT_HANDOFF','start_seconds':0,'end_seconds':2}]},'hard_invariants':{}}
    root=Path(raw)
    manifest=render_scene_media(edit,motion,[],{'events':[]},{'events':[]},root/'out',root/'cache',width=640,height=360,fps=30)
    qa=verify_encoded_composition(manifest['clips'][0]['source_path'],motion,render_edit_map=edit)
    assert qa['pass'] and qa['actor_attributable_verified_count']==1,qa
    assert qa['rows'][0]['attribution_sample_authority']=='AUTHORED_TRANSITION_MIDPOINT',qa
    # A very thin owner cannot certify a later large source reveal through
    # its own scale change. The source needs a linked, material focus state.
    from hexa_v31.layout.reference_geometry_finalizer import _author_reveal_participant
    thin_path=root/'thin.png'
    Image.new('RGBA',(24,400),(35,70,140,255)).save(thin_path)
    thin=actor('THIN_CONTEXT',.2)
    thin.update(source_path=str(thin_path),source_bbox_norm=[0,0,24/1920,400/1080],
                visible_ink_fraction=1.,visual_card_id='SEMANTIC_CARD')
    thin['composition_states'][1].update(center_norm=[.2,.5],scale_multiplier=1.14,
        participating_event_ids=['THIN_CONTEXT','REVEALED_SOURCE'],card_id='SEMANTIC_CARD')
    revealed=actor('REVEALED_SOURCE',.65)
    revealed.update(composition_states=[],visible_ink_fraction=1.,
        start_seconds=.9,physical_start_seconds=.9,motion_start_seconds=.9,
        preset_entry=dict(name='APPEAR_HIGH_SCALE',start_seconds=.9,duration_seconds=.5))
    weak=check([thin,revealed],thin)
    assert not weak['actor_attributable_pass'],weak
    assert _author_reveal_participant(thin,revealed,thin['composition_states'][1])
    linked=check([thin,revealed],thin)
    assert linked['actor_attributable_pass'] and linked['participant_delta'] > .003,linked
    assert not _author_reveal_participant(thin,revealed,thin['composition_states'][1])
    assert revealed['composition_participant_states'][1]['scale_multiplier']==1.
    assert all(s['center_norm']==[.65,.5] for s in revealed['composition_participant_states'])
    print('V31_THIN_OWNER_LINKED_REVEAL_ATTRIBUTION_PASS')

    # The residual P4 author must itself create an actor-attributable pixel
    # change. A planner-only focus beat or a preset reveal earning accidental
    # credit is not sufficient.
    from hexa_v31.layout.reference_residual_closure import finalize_reference_residual_closure
    residual_owner=actor('RESIDUAL_FOCUS_OWNER',.30)
    residual_owner.update(
        visual_card_id='RESIDUAL_FOCUS_CARD',semantic_role='LEAD',composition_role='LEAD',
        visible_ink_fraction=1.,visible_ink_fraction_basis='SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        layout_scale_multiplier=1.6,composition_states=[],perceptual_hit_seconds=.55,
        planned_rect_norm=[.10,.204,.40,.592],collision_envelope_rect_norm=[.10,.204,.40,.592],
    )
    residual_target=actor('RESIDUAL_FOCUS_TARGET',.74)
    residual_target.update(
        visual_card_id='RESIDUAL_FOCUS_CARD',attention_priority='SUPPORTING',semantic_role='SUPPORTING',composition_role='SUPPORT',
        visible_ink_fraction=1.,visible_ink_fraction_basis='SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        composition_states=[],perceptual_hit_seconds=2.0,
        preset_entry={'name':'APPEAR_HIGH_SCALE','start_seconds':1.35,'duration_seconds':.8},
    )
    residual_card={
        'card_id':'RESIDUAL_FOCUS_CARD','start_seconds':0.,'end_seconds':3.,'duration_seconds':3.,
        'story_phase_plan':{'phases':[{'phase_id':'FOCUS_PHASE','start_seconds':0.,'end_seconds':3.,
            'event_ids':['RESIDUAL_FOCUS_OWNER','RESIDUAL_FOCUS_TARGET']}]},
        'constraint_layout':{'placements':{
            'RESIDUAL_FOCUS_OWNER':{'center_norm':[.30,.5],'scale':1.6,'rect_norm':[.10,.204,.40,.592]},
            'RESIDUAL_FOCUS_TARGET':{'center_norm':[.74,.5],'scale':1.,'rect_norm':list(residual_target['planned_rect_norm'])},
        }},
    }
    residual_plan={'fps':30.,'events':[residual_owner,residual_target],
        'visual_cards':{'cards':[residual_card]}}
    residual_stats=finalize_reference_residual_closure(residual_plan)
    assert residual_stats['focus_candidates_committed']==1,residual_stats
    residual_state=residual_owner['composition_states'][-1]
    times=(float(residual_state['start_seconds'])-.12,
           float(residual_state['start_seconds'])+float(residual_state['transition_duration_seconds'])+.12)
    residual_frames=[np.full((360,640),255,dtype=np.uint8) for _ in range(2)]
    for e in (residual_owner,residual_target):
        runtime,image=prepare_composition_actor(e,640,360)
        for i,t in enumerate(times):
            np.minimum(residual_frames[i],_gray_actor(runtime,image,t,640,360),out=residual_frames[i])
    residual_attribution=attribute_composition(
        residual_owner,residual_state,residual_frames[0],residual_frames[1],times,
        {'events':[residual_owner,residual_target]})
    assert residual_attribution['actor_attributable_pass'],residual_attribution
    assert residual_attribution['participant_delta']>=.003,residual_attribution
    assert residual_attribution['attributed_changed_pixel_ratio']>=.012,residual_attribution
    print('V31_RESIDUAL_FOCUS_ACTOR_ATTRIBUTION_PASS')
print('V31_COMPOSITION_ACTOR_ATTRIBUTION_PASS')
