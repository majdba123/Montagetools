from hexa_v31.layout.reference_perceptual_residual import _severity
from hexa_v31.layout.reference_quality_finalizer import _card_quality
from unittest.mock import patch

short=dict(start_seconds=0.,end_seconds=.7)
long=dict(start_seconds=1.,end_seconds=6.)
qshort=dict(underfilled_seconds=.7,underfilled_integral=.14,severe_underfilled_seconds=.7,mean_ink=0.,low_percentile_ink=0.,mean_population=0.)
qlong=dict(underfilled_seconds=5.,underfilled_integral=.65,severe_underfilled_seconds=5.,mean_ink=.07,low_percentile_ink=.04,mean_population=1.)
assert _severity(long,qlong)>_severity(short,qshort)*3
acceptable=dict(underfilled_seconds=0.,underfilled_integral=0.,severe_underfilled_seconds=0.,mean_ink=.25,low_percentile_ink=.24,mean_population=2.)
assert _severity(long,qlong)>_severity(long,acceptable)
with patch('hexa_v31.layout.reference_quality_finalizer._card_samples',return_value=[(0.,.05,1),(.25,.10,1),(.5,.3,2)]):
    q=_card_quality({},dict(start_seconds=0.,end_seconds=.6),.25)
assert abs(q['underfilled_integral']-.0625)<1e-6,q
assert q['minimum_ink']==.05 and q['low_percentile_ink']==.05
assert q['severe_underfilled_seconds']==.25
from hexa_v31.layout.reference_perceptual_residual import _commit_group
import copy
roots=[dict(event_id='A',visual_card_id='CARD',scene_id='SOURCE',card_rest_position_norm=[.3,.5]),
       dict(event_id='B',visual_card_id='CARD',scene_id='SOURCE',card_rest_position_norm=[.7,.5])]
original=copy.deepcopy(roots)
# Exhausted retry budget must restore IDs before any later single-root fallback.
with patch('hexa_v31.layout.reference_perceptual_residual.build_visual_density_report',return_value={}), \
     patch('hexa_v31.layout.reference_perceptual_residual._group_centroid',return_value=[.5,.5]):
    assert not _commit_group({'events':roots},{'card_id':'CARD'},roots,qlong,30.,{'candidates_evaluated':144})
assert roots==original
from test_v31_reference_perceptual_residual import event,plan
from hexa_v31.layout.reference_perceptual_residual import _commit_interval_frame
from hexa_v31.composition_solver import composition_state_at
from hexa_v31.composition_qa import composition_plan_qa
focal=event('SOLO',.35,.5,(0,0,.20,.30),primary=True,end=5.)
support=event('LATER_SUPPORT',.64,.5,(0,0,.20,.30),start=3.,end=5.)
p=plan([focal,support],end=5.);before=copy.deepcopy(p)
stats=dict(candidates_evaluated=0,sample_step_seconds=.1,commits=0,single_root_commits=0,event_ids=[],mutations=[])
assert _commit_interval_frame(p,p['visual_cards']['cards'][0],focal,dict(start_seconds=0.,end_seconds=5.),_card_quality(p,p['visual_cards']['cards'][0],.1),30.,stats)
assert composition_state_at(focal,1.5)[1]>1.2
assert composition_state_at(focal,3.)[1]==1.
assert stats['mutations'][0]['interval'][1]==3.
assert focal['card_rest_position_norm']==before['events'][0]['card_rest_position_norm']
assert support==before['events'][1]
assert composition_plan_qa(p)['pass']
assert stats['mutations'][0]['after_quality']['underfilled_integral']<stats['mutations'][0]['before_quality']['underfilled_integral']
# A short spoken introduction still has usable framing time during its entry.
# Waiting until the preset settles would discard this entire safe opportunity.
early=event('EARLY',.35,.5,(0,0,.20,.30),primary=True,end=4.)
early['preset_entry']=dict(name='APPEAR_HIGH_SCALE',start_seconds=0.,duration_seconds=.8)
later=event('INCOMING',.64,.5,(0,0,.20,.30),start=1.8,end=4.)
short_plan=plan([early,later],end=4.);original_entry=copy.deepcopy(early['preset_entry'])
short_stats=dict(candidates_evaluated=0,sample_step_seconds=.1,commits=0,single_root_commits=0,event_ids=[],mutations=[])
assert _commit_interval_frame(short_plan,short_plan['visual_cards']['cards'][0],early,
    dict(start_seconds=0.,end_seconds=4.),_card_quality(short_plan,short_plan['visual_cards']['cards'][0],.1),30.,short_stats)
assert early['preset_entry']==original_entry
assert composition_state_at(early,.8)[1]>1.2
assert composition_state_at(early,1.8)[1]==1.
assert composition_plan_qa(short_plan)['pass']
from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe
wide=copy.deepcopy(before);wide['events'][0]['layout_scale_multiplier']=2.
assert not _candidate_safe(wide,[wide['events'][0]],30.)
# Render the temporary framing through final sealing and the same runtime
# preparation/evaluation as shipping, then compare actual source pixels.
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from hexa_v31.render.scene_media import prepare_composition_actor
from hexa_v31.layout.composition_attribution import _gray_actor
from hexa_v31.interaction.director import finalize_interaction_motion_plan,assert_final_motion_plan_immutable
with tempfile.TemporaryDirectory() as raw:
    for i,e in enumerate(p['events']):
        path=Path(raw)/f'{i}.png';Image.new('RGBA',(384,324),(40,60+i*50,130,255)).save(path)
        e['source_path']=str(path);e['base_fit_scale_percent']=100.
    sealed=finalize_interaction_motion_plan(p);assert_final_motion_plan_immutable(sealed)
    runtime,image=prepare_composition_actor(sealed['events'][0],320,180)
    plain=dict(runtime,composition_participant_states=[])
    expanded=_gray_actor(runtime,image,1.5,320,180);rest=_gray_actor(plain,image,1.5,320,180)
    assert np.mean(np.abs(expanded.astype(float)-rest.astype(float)))/255>=.003
    assert np.mean(np.abs(expanded.astype(float)-rest.astype(float))>=10)>=.012
    assert np.array_equal(_gray_actor(runtime,image,3.2,320,180),_gray_actor(plain,image,3.2,320,180))
# A retained actor from the preceding card is visible encoded ink, even when
# its ownership forbids the current card from mutating it.
carried=event('CARRIED',.5,.5,(0,0,.3,.4),primary=True,end=5.)
carried['visual_card_id']='PREVIOUS_CARD'
carried_plan=plan([carried],end=5.)
assert _card_quality(carried_plan,carried_plan['visual_cards']['cards'][0],.25)['mean_ink']>.10
print('V31_SUSTAINED_SPARSE_SEVERITY_PASS')
