from __future__ import annotations

import copy

from hexa_v31.planning.preset_story_planner import _finalize_visual_lifetimes
from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa


def base_event(event_id, *, render_mode='ROOT_ATOMIC', physical_id=None, start=0.0, end=1.0,
               scene='SCENE_TEST', card='VCARD_TEST', root='ROOT_TEST'):
    return {
        'event_id': event_id,
        'scene_id': scene,
        'visual_card_id': card,
        'physical_id': physical_id or event_id,
        'partition_root_id': root,
        'render_mode': render_mode,
        'start_seconds': start,
        'end_seconds': end,
        'physical_start_seconds': start,
        'physical_end_seconds': end,
        'preset_entry': None,
        'preset_actions': [],
        'preset_exit': None,
        'suppressed_by_card_density': False,
        'independent_motion_allowed': render_mode != 'RESIDUAL_SUPPORT',
        'translation_safe_after_occlusion': render_mode != 'RESIDUAL_SUPPORT',
        'position_animated': False,
    }


cards={'cards':[{'card_id':'VCARD_TEST','start_seconds':0.0,'end_seconds':2.0}]}

# Regression class matching SCENE_043: a downstream timing pass may extend the
# final motion envelope beyond the provisional physical lifetime. Final commit
# must expand physical lifetime from the immutable final state, not weaken QA.
escaped=base_event('ESCAPED',start=.2,end=1.0)
escaped['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':.2,'duration_seconds':.3}
escaped['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.1,'duration_seconds':.4}
stats=_finalize_visual_lifetimes([escaped],cards)
assert stats['recommitted_event_count']==1,stats
assert escaped['motion_end_seconds']>=1.5-1e-6,escaped
assert escaped['physical_end_seconds']>=escaped['motion_end_seconds'],escaped

# Regression classes matching SCENE_007/037: child motion may be staggered,
# but every member of one certified partition owns one coherent carrier window.
a=base_event('CHILD_A',render_mode='CHILD_PARTITION',start=.0,end=1.0)
a['preset_entry']={'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':.1,'duration_seconds':.35}
a['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':.75,'duration_seconds':.25}
a['position_animated']=True
b=base_event('CHILD_B',render_mode='CHILD_PARTITION',start=.35,end=1.45)
b['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':.5,'duration_seconds':.3}
b['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.2,'duration_seconds':.25}
residual=base_event('RESIDUAL_SUPPORT',render_mode='RESIDUAL_SUPPORT',start=.0,end=1.25)
residual['animation_mode']='STATIC_SUPPORT'
events=[a,b,residual]
stats=_finalize_visual_lifetimes(events,cards)
assert stats['partition_group_count']==1,stats
windows={(e['physical_start_seconds'],e['physical_end_seconds']) for e in events}
assert len(windows)==1,events
assert len({e['motion_start_seconds'] for e in (a,b)})==2,(a,b)
carrier_end=a['partition_carrier_end_seconds']
assert abs((float(a['preset_exit']['start_seconds'])+float(a['preset_exit']['duration_seconds']))-carrier_end)<1e-6,a
assert abs((float(b['preset_exit']['start_seconds'])+float(b['preset_exit']['duration_seconds']))-carrier_end)<1e-6,b
assert a.get('partition_exit_retimed_to_carrier_end'),a
assert residual['position_animated'] is False and residual['independent_motion_allowed'] is False,residual
qa=visual_timeline_coverage_qa({'fps':30,'events':events,'visual_cards':{'cards':[{'card_id':'VCARD_TEST','start_seconds':min(x[0] for x in windows),'end_seconds':max(x[1] for x in windows)}]}})
assert qa['pass'],qa

# Certified partitions are source-survival atomic. Individual suppression must
# fail before render instead of redefining a partial composition as expected.
partial=[copy.deepcopy(a),copy.deepcopy(b),copy.deepcopy(residual)]
partial[1]['suppressed_by_card_density']=True
try:
    _finalize_visual_lifetimes(partial,cards)
except ValueError as exc:
    assert 'PARTIAL_CERTIFIED_PARTITION_SUPPRESSION' in str(exc),exc
else:
    raise AssertionError('partial certified partition suppression was accepted')

# The standalone QA must also reject an already-materialized partial partition.
for e in partial:
    e['physical_start_seconds']=0.0
    e['physical_end_seconds']=1.5
    e['partition_carrier_start_seconds']=0.0
    e['partition_carrier_end_seconds']=1.5
qa=visual_timeline_coverage_qa({'fps':30,'events':partial,'visual_cards':{'cards':[{'card_id':'VCARD_TEST','start_seconds':0.0,'end_seconds':1.5}]}})
assert not qa['pass'] and any('individually suppressed members' in x for x in qa['failures']),qa

print('V31_FINAL_VISUAL_LIFETIME_CONTRACT_PASS')


# Vision -> planner completeness: a certified reconstruction may not be reduced
# by planning before encoded QA establishes its expected evidence.
from hexa_v31.planning.preset_qa import _vision_planner_partition_completeness_qa

vision_result={
    'scene_id':'SCENE_TEST',
    'units':[
        {'physical_id':'CHILD_A','candidate_source':'FLORENCE_2','mask_path':'A.png'},
        {'physical_id':'CHILD_B','candidate_source':'FLORENCE_2','mask_path':'B.png'},
        {'physical_id':'CHILD_C','candidate_source':'FLORENCE_2','mask_path':'C.png'},
        {'physical_id':'RESIDUAL_SUPPORT','foundation_residual_support':True,'mask_path':'R.png'},
    ],
    'artifacts':{'foundation_vision':{'reconstruction_qa':{'partition_complete':True}}},
}
planner_complete={'events':[
    dict(base_event('A',render_mode='CHILD_PARTITION',physical_id='CHILD_A'),partition_complete=True),
    dict(base_event('B',render_mode='CHILD_PARTITION',physical_id='CHILD_B'),partition_complete=True),
    dict(base_event('C',render_mode='CHILD_PARTITION',physical_id='CHILD_C'),partition_complete=True),
    dict(base_event('R',render_mode='RESIDUAL_SUPPORT',physical_id='RESIDUAL_SUPPORT'),partition_complete=False),
]}
membership=_vision_planner_partition_completeness_qa(planner_complete,[vision_result])
assert membership['pass'],membership

planner_missing=copy.deepcopy(planner_complete)
planner_missing['events']=[e for e in planner_missing['events'] if e['physical_id']!='CHILD_B']
membership=_vision_planner_partition_completeness_qa(planner_missing,[vision_result])
assert not membership['pass'] and membership['groups'][0]['missing_member_ids']==['CHILD_B'],membership

planner_root_fallback={'events':[dict(base_event('ROOT',render_mode='ROOT_ATOMIC',physical_id='ROOT_COMPOSITE_FALLBACK'),partition_complete=False)]}
membership=_vision_planner_partition_completeness_qa(planner_root_fallback,[vision_result])
assert membership['pass'] and membership['groups'][0]['selection_mode']=='ROOT_ATOMIC_FALLBACK',membership
