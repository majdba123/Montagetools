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
a['position_animated']=True
b=base_event('CHILD_B',render_mode='CHILD_PARTITION',start=.35,end=1.45)
b['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':.5,'duration_seconds':.3}
residual=base_event('RESIDUAL_SUPPORT',render_mode='RESIDUAL_SUPPORT',start=.0,end=1.25)
residual['animation_mode']='STATIC_SUPPORT'
events=[a,b,residual]
stats=_finalize_visual_lifetimes(events,cards)
assert stats['partition_group_count']==1,stats
windows={(e['physical_start_seconds'],e['physical_end_seconds']) for e in events}
assert len(windows)==1,events
assert len({e['motion_start_seconds'] for e in (a,b)})==2,(a,b)
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
