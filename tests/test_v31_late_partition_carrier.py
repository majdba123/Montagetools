"""Late fallback preserves source survival independently of attention."""
import copy
from hexa_v31.planning.preset_story_planner import _schedule_event

for fps in (24., 30., 60.):
    for phase_end in (1.25, 2.1, 3.0):
        event=dict(event_id='leaf-alpha', scene_id='drawing-oak', visual_card_id='sentence',
                   render_mode='CHILD_PARTITION', partition_root_id='branch',
                   partition_carrier_start_seconds=0., partition_carrier_end_seconds=4.,
                   physical_start_seconds=0., physical_end_seconds=4.,
                   card_rest_position_norm=[.3,.5], attention_priority='PRIMARY')
        sibling=copy.deepcopy(event); sibling['event_id']='leaf-beta'
        before=copy.deepcopy(sibling)
        _schedule_event(event,(.3,phase_end),{'end_seconds':4.},0,2,force_static=True,fps=fps)
        assert (event['physical_start_seconds'],event['physical_end_seconds'])==(0.,4.)
        assert event['semantic_focus_end_seconds']==phase_end
        assert event['visibility_interval_seconds']==[0.,4.]
        assert event['motion_end_seconds']<=4.+1e-6
        assert abs(next(x for x in event['motion_intervals'] if x['kind']=='EXIT')['effective_end_seconds']-4.)<1e-6
        assert sibling==before
print('late partition carrier PASS')

residual=copy.deepcopy(event)
residual['render_mode']='RESIDUAL_SUPPORT'
_schedule_event(residual,(.4,1.4),{'end_seconds':4.},0,2,force_static=True)
assert residual['physical_end_seconds']==4.
assert residual['preset_entry'] is None and residual['preset_exit'] is None
assert residual['motion_intervals']==[] and not residual['position_animated']
