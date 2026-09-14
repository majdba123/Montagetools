from copy import deepcopy

from hexa_v31.planning.preset_story_planner import (
    _adaptive_composition_state_optimize, _compile_final_motion_intervals,
    _finalize_visual_lifetimes,
)
from hexa_v31.composition_solver import composition_state_at
from hexa_v31.render.preview import _event_state
from hexa_v31.composition_qa import _state
from hexa_v31.interaction.director import _final_timing_sha256, assert_final_motion_plan_immutable


def actor(eid, x, start, end, hit):
    return dict(event_id=eid,scene_id='SOURCE',visual_card_id='CARD',
                physical_id=eid,partition_root_id='ROOT',render_mode='ROOT_ATOMIC',
                start_seconds=start,end_seconds=end,physical_start_seconds=start,
                physical_end_seconds=end,motion_start_seconds=start,motion_end_seconds=end,
                settle_seconds=start+.8,perceptual_hit_seconds=hit,
                card_rest_position_norm=[x,.5],source_bbox_norm=[0,0,.12,.2],
                planned_rect_norm=[x-.06,.4,.12,.2],layout_scale_multiplier=1.,
                attention_priority='PRIMARY',translation_safe_after_occlusion=False,
                independent_motion_allowed=False,position_animated=False,
                preset_entry=None,preset_exit=None,preset_actions=[])


cards={'cards':[dict(card_id='CARD',start_seconds=0.,end_seconds=5.)]}
for reveal,end,expected in [(2.,5.,True),(2.6,3.,True),(2.79,2.84,False)]:
    focal=actor('FOCAL',.25,0.,5.,.5)
    support=actor('SUPPORT',.75,reveal,end,2.8)
    before=deepcopy(support)
    stats=_adaptive_composition_state_optimize([focal,support],cards,30.)
    assert bool(stats['candidates_committed'])==expected,stats
    if not expected:
        assert support==before and not focal.get('composition_states')
        continue
    a,b=support['composition_participant_states']
    assert reveal<=a['start_seconds']<=b['start_seconds']
    assert a['start_seconds']+a['transition_duration_seconds']<=b['start_seconds']+1e-6
    assert b['start_seconds']+b['transition_duration_seconds']<=end+1e-6
    for key in ('start_seconds','end_seconds','physical_start_seconds','physical_end_seconds',
                'motion_start_seconds','motion_end_seconds','translation_safe_after_occlusion'):
        assert support[key]==before[key],key
    for t in (reveal-.01,reveal,b['start_seconds'],min(end-.01,b['start_seconds']+.5)):
        qa=_state(support,t);render=_event_state(support,t)
        assert (qa is None)==(render is None),(t,qa,render)
        if qa:
            assert qa[0]==[.75,.5] and composition_state_at(support,t)[0]==[.75,.5]
            assert abs(qa[1]-render[1])<1e-6,(qa,render)
    intervals,_,_= _compile_final_motion_intervals(support)
    assert len([r for r in intervals if r['kind']=='COMPOSITION_PARTICIPANT_STATE'])==2
    plan={'events':[focal,support]}
    plan['finalization_barrier']={'timing_sha256':_final_timing_sha256(plan)}
    assert_final_motion_plan_immutable(plan)
    support['composition_participant_states'][1]['transition_duration_seconds']+=.01
    try:
        assert_final_motion_plan_immutable(plan)
    except ValueError as exc:
        assert 'FINAL_MOTION_PLAN_MUTATED_AFTER_CERTIFICATION' in str(exc)
    else:
        raise AssertionError('participant mutation escaped final timing seal')

# Both state kinds obey the existing immutable partition/card boundary.
for field in ('composition_states','composition_participant_states'):
    child=actor('CHILD',.25,0.,2.,.5);child['render_mode']='CHILD_PARTITION'
    residual=actor('RESIDUAL',.75,0.,2.,.5);residual['render_mode']='RESIDUAL_SUPPORT'
    child[field]=[dict(state_id='HANDOFF',start_seconds=1.8,
                       transition_duration_seconds=.5,scale_multiplier=1.10)]
    _finalize_visual_lifetimes([child,residual],{'cards':[dict(card_id='CARD',start_seconds=0.,end_seconds=2.)]},30.)
    assert child['physical_end_seconds']==residual['physical_end_seconds']==2.
    state=child[field][0]
    assert state['start_seconds']+state['transition_duration_seconds']<=2.+1e-6
    assert child['motion_end_seconds']<=2.+1e-6
print('V31_COMPOSITION_PARTICIPANT_CONTRACT_PASS')
