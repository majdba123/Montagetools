from __future__ import annotations

from hexa_v31.planning.preset_qa import hierarchical_render_evidence_qa
from hexa_v31.preset_story_planner import _foundation_partition_motion_contract, _hierarchical_render_metadata


def residual(**updates):
    event={
        'event_id':'SCENE_018_RESIDUAL_SUPPORT',
        'hierarchy_level':1,
        'render_mode':'RESIDUAL_SUPPORT',
        'source_layer_path':'scene_018_residual.png',
        'foundation_residual_support':True,
        'independent_motion_allowed':False,
        'translation_safe_after_occlusion':False,
        'animation_mode':'STATIC_SUPPORT',
        'position_animated':False,
        'preset_actions':[],
    }
    event.update(updates)
    return event


valid_residual=residual()
propagated=_hierarchical_render_metadata({
    **valid_residual,'layer_path':valid_residual['source_layer_path'],
})
for key in ('render_mode','source_layer_path','independent_motion_allowed','translation_safe_after_occlusion','foundation_residual_support','animation_mode'):
    assert propagated[key]==valid_residual[key],(key,propagated)
case_a=hierarchical_render_evidence_qa([valid_residual])
assert case_a['pass'] and not case_a['failures'],case_a
contract=_foundation_partition_motion_contract([valid_residual])
assert contract['eligible_foundation_actor_count']==0 and contract['independently_animated_actor_count']==0,contract

for attempted_motion in ({'independent_motion_allowed':True},{'position_animated':True}):
    case_b=hierarchical_render_evidence_qa([residual(**attempted_motion)])
    assert not case_b['pass'] and case_b['failures'],case_b

invalid_child={
    'event_id':'SCENE_018_CHILD_1','hierarchy_level':1,'render_mode':'CHILD_PARTITION',
    'partition_complete':False,'source_layer_path':'','reveal_safe':True,
}
case_c=hierarchical_render_evidence_qa([invalid_child])
assert not case_c['pass'] and case_c['failures']==['SCENE_018_CHILD_1: hierarchical child lacks certified partition render evidence'],case_c

valid_child={**invalid_child,'partition_complete':True,'source_layer_path':'scene_018_child_1.png'}
case_d=hierarchical_render_evidence_qa([valid_child])
assert case_d['pass'] and not case_d['failures'],case_d

print('V31_RESIDUAL_SUPPORT_QA_PASS')
