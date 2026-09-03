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
escaped_exit=next(row for row in escaped['motion_intervals'] if row['kind']=='EXIT')
assert abs(float(escaped_exit['effective_visible_fraction'])-.6)<1e-6,escaped_exit
assert abs(float(escaped['motion_end_seconds'])-1.34)<1e-6,escaped
assert escaped['physical_end_seconds']>=escaped['motion_end_seconds'],escaped
assert float(escaped['preset_exit']['duration_seconds'])==.4,escaped

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
a_exit=next(row for row in a['motion_intervals'] if row['kind']=='EXIT')
b_exit=next(row for row in b['motion_intervals'] if row['kind']=='EXIT')
assert abs(float(a_exit['effective_end_seconds'])-carrier_end)<1e-6,a
assert abs(float(b_exit['effective_end_seconds'])-carrier_end)<1e-6,b
assert float(a['preset_exit']['duration_seconds'])==.25 and float(b['preset_exit']['duration_seconds'])==.25,(a,b)
assert a.get('partition_exit_retimed_to_carrier_end'),a
assert residual['position_animated'] is False and residual['independent_motion_allowed'] is False,residual
assert residual['preset_entry'] is None and residual['preset_exit'] is None and residual['motion_intervals']==[],residual
assert residual['motion_start_seconds']==residual['physical_start_seconds'],residual
qa=visual_timeline_coverage_qa({'fps':30,'events':events,'visual_cards':{'cards':[{'card_id':'VCARD_TEST','start_seconds':min(x[0] for x in windows),'end_seconds':max(x[1] for x in windows)}]}})
assert qa['pass'],qa

# A disappearance preset may have an authored fully-transparent nominal tail.
# The exact preset duration remains unchanged, while physical lifetime uses the
# source-visible envelope from the preset opacity authority.
invisible_tail=base_event('INVISIBLE_TAIL',render_mode='CHILD_PARTITION',start=0.0,end=2.0)
invisible_tail['preset_entry']={'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':0.0,'duration_seconds':1.0}
invisible_tail['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.64,'duration_seconds':0.6}
invisible_tail['position_animated']=True
tail_support=base_event('TAIL_SUPPORT',render_mode='RESIDUAL_SUPPORT',start=0.0,end=2.0)
tail_support['animation_mode']='STATIC_SUPPORT'
_finalize_visual_lifetimes([invisible_tail,tail_support],{'cards':[{'card_id':'VCARD_TEST','start_seconds':0.0,'end_seconds':2.0}]})
tail_exit=next(row for row in invisible_tail['motion_intervals'] if row['kind']=='EXIT')
assert float(invisible_tail['preset_exit']['duration_seconds'])==0.6,invisible_tail
assert abs(float(tail_exit['effective_visible_fraction'])-.6)<1e-6,tail_exit
assert abs(float(tail_exit['effective_end_seconds'])-2.0)<1e-6,tail_exit
assert invisible_tail['position_animated'] and not invisible_tail.get('final_partition_motion_fallback'),invisible_tail

# If final optimized motion cannot fit the legal partition/card carrier,
# preserve the actor with bounded reveal-only motion rather than failing or
# deleting source pixels.
overflow=base_event('OVERFLOW',render_mode='CHILD_PARTITION',start=.2,end=1.8)
overflow['preset_entry']={'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':.2,'duration_seconds':.35}
overflow['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':1.85,'duration_seconds':.6}
overflow['position_animated']=True
overflow_support=base_event('OVERFLOW_SUPPORT',render_mode='RESIDUAL_SUPPORT',start=.0,end=2.0)
overflow_support['animation_mode']='STATIC_SUPPORT'
overflow_cards={'cards':[{'card_id':'VCARD_TEST','start_seconds':0.0,'end_seconds':2.0}]}
_finalize_visual_lifetimes([overflow,overflow_support],overflow_cards)
assert overflow['physical_end_seconds']==2.0,overflow
assert overflow['motion_end_seconds']<=2.0+1e-6,overflow
assert not overflow['position_animated'] and overflow['foundation_motion_decision']=='REVEAL_ONLY',overflow
assert overflow.get('final_partition_motion_fallback')=='MOTION_ENVELOPE_OUTSIDE_CARRIER',overflow

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



# Cross-scene regression from the real Premiere BUILD failure class: two
# ordinary source events from scene A may collide with an incoming event from
# scene B after late lifetime commit. They are independent carriers and must be
# retired independently; grouping the whole scene as one carrier can make the
# handoff impossible and leave USER_PRESET_MOTION_QA_FAILED.
handoff_cards={'cards':[{'card_id':'VCARD_HANDOFF','start_seconds':0.0,'end_seconds':4.0}]}
def handoff_event(event_id, scene, source_start, start, end, x=.5, y=.5):
    e=base_event(event_id,render_mode='ROOT_ATOMIC',start=start,end=end,
                 scene=scene,card='VCARD_HANDOFF',root=event_id+'_ROOT')
    e.update({
        'source_scene_start_seconds':source_start,
        'source_scene_end_seconds':end,
        'source_bbox_norm':[0.30,0.30,0.32,0.32],
        'card_rest_position_norm':[x,y],
        'planned_rect_norm':[x-.16,y-.16,.32,.32],
        'collision_envelope_rect_norm':[x-.16,y-.16,.32,.32],
        'layout_scale_multiplier':1.0,
        'reference_camera_scale':1.0,
        'attention_priority':'PRIMARY',
        'perceptual_hit_seconds':start+.18,
        'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':start,'duration_seconds':0.4},
        'preset_exit':{'name':'DISAPPEAR_DOWN_SCALE','start_seconds':end-.36,'duration_seconds':0.6},
        'appearance_method':'SCALE_POP',
        'disappearance_method':'PRESET_DISAPPEARANCE',
    })
    return e

out_a=handoff_event('OUT_A','SCENE_A',0.0,0.0,2.2,.45,.50)
out_b=handoff_event('OUT_B','SCENE_A',0.0,0.15,2.25,.55,.50)
incoming=handoff_event('IN_B','SCENE_B',1.0,1.0,3.5,.50,.50)
handoff_events=[out_a,out_b,incoming]
from hexa_v31.composition_qa import card_motion_conflicts
before=card_motion_conflicts(handoff_events,0.0,4.0,30.0)
assert any({'OUT_A','IN_B'}=={r['event_a'],r['event_b']} for r in before),before
assert any({'OUT_B','IN_B'}=={r['event_a'],r['event_b']} for r in before),before
handoff_stats=_finalize_visual_lifetimes(handoff_events,handoff_cards,30.0)['partition_handoff_repair']
after=card_motion_conflicts(handoff_events,0.0,4.0,30.0)
assert not any('IN_B' in {r['event_a'],r['event_b']} and
               ({r['event_a'],r['event_b']} & {'OUT_A','OUT_B'})
               for r in after),(handoff_stats,after,handoff_events)
assert handoff_stats['trimmed_source_group_count']>=2,handoff_stats
assert {'OUT_A','OUT_B'}.issubset(set(handoff_stats['trimmed_event_ids'])),handoff_stats
assert not out_a.get('suppressed_by_card_density') and not out_b.get('suppressed_by_card_density'),handoff_events


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
