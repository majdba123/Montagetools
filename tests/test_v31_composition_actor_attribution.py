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
print('V31_COMPOSITION_ACTOR_ATTRIBUTION_PASS')
