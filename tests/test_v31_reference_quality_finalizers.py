from __future__ import annotations

from hexa_v31.composition_solver import MOTION_ENVELOPE_SCALE, _fp, _rect
from hexa_v31.layout.reference_geometry_finalizer import finalize_reference_geometry
from hexa_v31.layout.reference_quality_finalizer import finalize_reference_density_topology
from hexa_v31.layout.reference_quality_finalizer import _card_quality


def event(eid, x, y, bbox, *, start=0.0, end=4.0, hit=1.0, primary=False,
          render_mode='ROOT_ATOMIC', ink=1.0, partition_root=None):
    row = {
        'event_id': eid,
        'scene_id': 'SCENE_A',
        'visual_card_id': 'CARD_A',
        'render_mode': render_mode,
        'source_bbox_norm': list(bbox),
        'visible_ink_fraction': ink,
        'visible_ink_fraction_basis': 'SOURCE_ALPHA_WITHIN_DECLARED_OBJECT_BBOX',
        'matting': {'opaque_foreground_fraction': ink},
        'reference_camera_scale': 1.0,
        'layout_scale_multiplier': 1.0,
        'card_rest_position_norm': [x, y],
        'attention_priority': 'PRIMARY' if primary else 'SUPPORTING',
        'composition_role': 'LEAD' if primary else 'SUPPORT',
        'start_seconds': start,
        'end_seconds': end,
        'physical_start_seconds': start,
        'physical_end_seconds': end,
        'motion_start_seconds': start,
        'motion_end_seconds': end,
        'settle_seconds': min(end, start + .8),
        'perceptual_hit_seconds': hit,
        'preset_entry': None,
        'preset_exit': None,
        'preset_actions': [],
        'translation_safe_after_occlusion': False,
        'animation_safe': False,
        'position_animated': False,
    }
    if partition_root is not None:
        row['partition_root_id'] = partition_root
        row['partition_complete'] = True
    fp = _fp(row)
    row['planned_rect_norm'] = list(_rect((x, y), fp, MOTION_ENVELOPE_SCALE))
    row['collision_envelope_rect_norm'] = list(row['planned_rect_norm'])
    return row


def card(events, *, end=4.0):
    return {
        'card_id': 'CARD_A',
        'start_seconds': 0.0,
        'end_seconds': end,
        'duration_seconds': end,
        'story_phase_plan': {
            'phases': [{
                'phase_id': 'CARD_A_P1',
                'start_seconds': 0.0,
                'end_seconds': end,
                'event_ids': [row['event_id'] for row in events],
            }]
        },
        'constraint_layout': {
            'placements': {
                row['event_id']: {
                    'center_norm': list(row['card_rest_position_norm']),
                    'scale': row['layout_scale_multiplier'],
                    'rect_norm': list(row['planned_rect_norm']),
                }
                for row in events
            }
        },
    }


# P3 topology regression: the outgoing source-backed context is already dense
# enough on its own. The incoming focus is deliberately sparse; once context
# retires, a sustained underfilled interval appears and must be rescued by
# retaining that real predecessor state rather than inventing new pixels.
context = event('CONTEXT', .30, .52, (0, 0, .40, .52), start=0.0, end=2.0, hit=.7, ink=1.0)
focus = event('FOCUS', .72, .52, (0, 0, .30, .32), start=1.5, end=4.0, hit=2.0, primary=True, ink=1.0)
card_a = card([context, focus])
plan = {'fps': 30.0, 'events': [context, focus], 'visual_cards': {'cards': [card_a]}}

topology = finalize_reference_density_topology(plan, fps=30.0)
assert topology['pass'], topology
assert topology['holds_committed'] >= 1, topology
assert float(context['end_seconds']) > 3.5, context
assert context['reference_density_hold_authority'] == 'SOURCE_BACKED_PREDECESSOR_STATE_CONTINUITY'
assert topology['after_underfilled_seconds'] < topology['before_underfilled_seconds'], topology


# P3 partition regression: certified source partitions remain atomic, but the
# whole partition may grow through one uniform transform. No child receives an
# independent source-ink scale authority.
left = event('PART_L', .39, .52, (0, 0, .08, .18), end=2.0, hit=.5,
             render_mode='CHILD_PARTITION', ink=1.0, partition_root='ROOT_X')
right = event('PART_R', .61, .52, (0, 0, .08, .18), end=2.0, hit=.5,
              render_mode='CHILD_PARTITION', ink=1.0, partition_root='ROOT_X')
partition_card = card([left, right], end=2.0)
partition_plan = {'fps': 30.0, 'events': [left, right], 'visual_cards': {'cards': [partition_card]}}
old_distance = abs(left['card_rest_position_norm'][0] - right['card_rest_position_norm'][0])
partition_stats = finalize_reference_geometry(partition_plan, fps=30.0)
assert partition_stats['pass'], partition_stats
assert partition_stats['partition_groups_committed'] >= 1, partition_stats
assert left['layout_scale_multiplier'] == right['layout_scale_multiplier'], (left, right)
assert left['layout_scale_multiplier'] > 1.0, (left, right)
new_distance = abs(left['card_rest_position_norm'][0] - right['card_rest_position_norm'][0])
assert new_distance > old_distance, (old_distance, new_distance)
assert left['reference_partition_scale_authority'] == 'SOURCE_BACKED_PARTITION_UNIFORM_TRANSFORM_FULL_LIFETIME_CERTIFIED'
assert right['reference_partition_scale_authority'] == left['reference_partition_scale_authority']
assert 'final_visible_ink_scale_authority' not in left
assert 'final_visible_ink_scale_authority' not in right


# P4 regression: after richer lifetimes exist, the reference geometry stage gets
# a second chance to compile a semantic focus transfer at the real next reveal.
# This is source-owned editorial choreography, never idle camera drift.
lead = event('LEAD', .28, .52, (0, 0, .16, .22), start=0.0, end=4.0, hit=.8, primary=True, ink=.9)
support = event('SUPPORT', .72, .52, (0, 0, .16, .22), start=1.4, end=4.0, hit=2.4, ink=.9)
cascade_card = card([lead, support])
cascade_plan = {'fps': 30.0, 'events': [lead, support], 'visual_cards': {'cards': [cascade_card]}}
cascade_stats = finalize_reference_geometry(cascade_plan, fps=30.0)
assert cascade_stats['pass'], cascade_stats
assert cascade_stats['semantic_cascade_committed'] >= 1, cascade_stats
assert lead.get('meaningful_recomposition'), lead
assert len(lead.get('composition_states') or []) >= 2, lead
assert len(support.get('composition_participant_states') or []) >= 2, support
assert float(lead['composition_states'][-1]['start_seconds']) <= float(support['perceptual_hit_seconds']), lead

print('V31_REFERENCE_QUALITY_FINALIZERS_PASS')

# A/B: a continuously sparse phase must consider a predecessor that retires
# inside the sparse interval, even though both actors are already present.
tiny_context=event('SMALL_CONTEXT',.28,.52,(0,0,.18,.25),end=2.,hit=.5)
tiny_focus=event('SMALL_FOCUS',.72,.52,(0,0,.18,.25),start=1.,hit=1.8,primary=True)
small_card=card([tiny_context,tiny_focus])
small_plan={'fps':30.,'events':[tiny_context,tiny_focus],'visual_cards':{'cards':[small_card]}}
assert _card_quality(small_plan,small_card,.1)['underfilled_seconds']>=3.9
small_result=finalize_reference_density_topology(small_plan)
assert small_result['holds_committed']==1,small_result
assert tiny_context['end_seconds']==4.
# C/I: temporal adjacency alone cannot retain unrelated source material.
unrelated=event('UNRELATED',.28,.52,(0,0,.18,.25),end=2.,hit=.5)
next_focus=event('NEXT',.72,.52,(0,0,.18,.25),start=2.,hit=2.8,primary=True)
next_focus['scene_id']='UNRELATED_SCENE'
separate_card=card([unrelated,next_focus])
separate_card['story_phase_plan']['phases']=[dict(phase_id='OLD',event_ids=['UNRELATED']),dict(phase_id='NEW',event_ids=['NEXT'])]
separate={'events':[unrelated,next_focus],'visual_cards':{'cards':[separate_card]}}
assert finalize_reference_density_topology(separate)['holds_committed']==0
assert not unrelated.get('composition_states') and unrelated['end_seconds']==2.
# D/E: a complete, off-center partition can be fitted as one group; suppressed
# members must never be silently dropped to authorize a partial-group scale.
parts=[event('LEFT',.65,.64,(0,0,.08,.18),end=2.,render_mode='CHILD_PARTITION',partition_root='OFFCENTER'),
       event('RIGHT',.82,.64,(0,0,.08,.18),end=2.,render_mode='CHILD_PARTITION',partition_root='OFFCENTER')]
group_plan={'events':parts,'visual_cards':{'cards':[card(parts,end=2.)]}}
group_result=finalize_reference_geometry(group_plan)
assert group_result['partition_groups_committed']==1,group_result
factor=parts[0]['reference_partition_scale_factor']
assert abs(parts[1]['card_rest_position_norm'][0]-parts[0]['card_rest_position_norm'][0]-.17*factor)<2e-6
assert parts[1]['reference_partition_scale_factor']==factor
from hexa_v31.layout.reference_geometry_finalizer import _partition_groups
parts.append(dict(parts[0],event_id='MISSING',suppressed_by_card_density=True))
assert not _partition_groups(parts)
print('V31_REFERENCE_TOPOLOGY_CONTINUITY_AND_GROUP_FIT_PASS')

# C: context may not survive into a colliding successor, even if retaining it
# would improve the projected ink score. Failed candidates restore lifetimes.
blocked_context = event('BLOCKED_CONTEXT', .5, .52, (0, 0, .30, .35), end=2., hit=.5)
blocked_focus = event('BLOCKED_FOCUS', .5, .52, (0, 0, .30, .35), start=2., hit=2.8, primary=True)
blocked_plan = {'events': [blocked_context, blocked_focus],
                'visual_cards': {'cards': [card([blocked_context, blocked_focus])]}}
blocked_plan['visual_cards']['cards'][0]['story_phase_plan']['phases'] = [
    dict(phase_id='BEFORE', start_seconds=0., end_seconds=2., event_ids=['BLOCKED_CONTEXT']),
    dict(phase_id='AFTER', start_seconds=2., end_seconds=4., event_ids=['BLOCKED_FOCUS']),
]
blocked_result = finalize_reference_density_topology(blocked_plan)
assert blocked_result['holds_committed'] == 0, blocked_result
assert blocked_context['physical_end_seconds'] == 2.

# F: fitting an off-center scale-only root is a single static destination, not
# a trajectory. Every evaluated absolute state must retain that same center.
from hexa_v31.composition_solver import composition_state_at
root = event('OFFCENTER_ROOT', .78, .66, (0, 0, .24, .32), primary=True)
root['composition_states'] = [
    dict(state_id='ROOT_A', start_seconds=.8, transition_duration_seconds=0.,
         center_norm=[.78, .66], scale_multiplier=1.),
    dict(state_id='ROOT_B', start_seconds=2., transition_duration_seconds=.48,
         center_norm=[.78, .66], scale_multiplier=1.14),
]
root_plan = {'events': [root], 'visual_cards': {'cards': [card([root])]}}
root_result = finalize_reference_geometry(root_plan)
assert root_result['root_actors_committed'] == 1, root_result
assert root['layout_scale_multiplier'] > 1.1
assert root['card_rest_position_norm'] != [.78, .66]
for sample in (0., .8, 1.9, 2.1, 2.48, 3.9):
    assert composition_state_at(root, sample)[0] == root['card_rest_position_norm']
assert not root['position_animated'] and not root['translation_safe_after_occlusion']
print('V31_REFERENCE_ROOT_STATIC_FIT_AND_COLLISION_ROLLBACK_PASS')

# A card clock alone can miss a brief overlap in an actor's authored envelope.
# Both geometry and subsequent hierarchy finishing must reject that candidate.
from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe
from hexa_v31.layout.perceptual_finalizer import _candidate_safe as perceptual_safe
pulse = event('PULSE', .4, .52, (0, 0, .2, .2), start=.006667, end=1., primary=True)
neighbor = event('NEIGHBOR', .62, .52, (0, 0, .2, .2), end=1.)
pulse['composition_states'] = [
    dict(state_id='ESTABLISHED', start_seconds=.1, transition_duration_seconds=0.,
         center_norm=[.4, .52], scale_multiplier=1.),
    dict(state_id='REACTION', start_seconds=.301667, transition_duration_seconds=.005,
         center_norm=[.4, .52], scale_multiplier=1.5),
    dict(state_id='SETTLED', start_seconds=.306667, transition_duration_seconds=.005,
         center_norm=[.4, .52], scale_multiplier=1.),
]
pulse_plan = {'events': [pulse, neighbor],
              'visual_cards': {'cards': [card([pulse, neighbor], end=1.)]}}
assert not card_motion_conflicts([pulse, neighbor], 0., 1., 30.)
assert not _candidate_safe(pulse_plan, [pulse], 30.)
assert not perceptual_safe(pulse_plan, pulse, 30.)
print('V31_REFERENCE_PHYSICAL_CLOCK_COLLISION_REJECTION_PASS')

# H/I: a long card can reuse its established focal actor at a second real
# source reveal. Extending duration alone is not a semantic opportunity.
long_lead = event('LONG_LEAD', .25, .52, (0, 0, .12, .16), end=6., hit=.5, primary=True)
first_reveal = event('FIRST_REVEAL', .72, .28, (0, 0, .12, .16), start=1.4, end=6., hit=2.4)
second_reveal = event('SECOND_REVEAL', .72, .74, (0, 0, .12, .16), start=3.8, end=6., hit=4.8)
long_events = [long_lead, first_reveal, second_reveal]
long_plan = {'events': long_events, 'visual_cards': {'cards': [card(long_events, end=6.)]}}
long_result = finalize_reference_geometry(long_plan)
assert len(long_lead['composition_states']) == 3, (long_result, long_lead)
later = long_lead['composition_states'][-1]
assert later['participating_event_ids'] == ['LONG_LEAD', 'SECOND_REVEAL']
assert abs(later['start_seconds'] + later['transition_duration_seconds'] - 4.8) < 1e-6
assert composition_state_at(long_lead, 5.)[1] > composition_state_at(long_lead, 3.)[1] + .12
assert all(s['center_norm'] == long_lead['card_rest_position_norm'] for s in long_lead['composition_states'])
import copy
no_trigger = copy.deepcopy(long_plan)
no_trigger['events'] = [no_trigger['events'][0]]
no_trigger['events'][0]['end_seconds'] = 12.
no_trigger['events'][0]['physical_end_seconds'] = 12.
state_count = len(no_trigger['events'][0]['composition_states'])
from hexa_v31.layout.reference_geometry_finalizer import _continue_semantic_sequences
_continue_semantic_sequences(no_trigger, 30., long_result)
assert len(no_trigger['events'][0]['composition_states']) == state_count
print('V31_REFERENCE_LATER_SEMANTIC_REVEAL_PASS')

# C: collision-free geometry does not authorize a third concurrent primary.
outgoing = event('OUTGOING', .2, .52, (0, 0, .1, .2), end=2., hit=.5, primary=True)
incoming = event('INCOMING', .5, .52, (0, 0, .1, .2), start=2., hit=2.8, primary=True)
continuing = event('CONTINUING', .8, .52, (0, 0, .1, .2), hit=.7, primary=True)
budget_card = card([outgoing, incoming, continuing])
budget_card['story_phase_plan']['phases'] = [
    dict(phase_id='BEFORE', start_seconds=0., end_seconds=2., event_ids=['OUTGOING', 'CONTINUING']),
    dict(phase_id='AFTER', start_seconds=2., end_seconds=4., event_ids=['INCOMING', 'CONTINUING']),
]
budget_plan = {'events': [outgoing, incoming, continuing], 'visual_cards': {'cards': [budget_card]}}
assert finalize_reference_density_topology(budget_plan)['holds_committed'] == 0
assert outgoing['physical_end_seconds'] == 2.
print('V31_REFERENCE_PRIMARY_POPULATION_LIMIT_PASS')

# A retained source must hold a readable pose, then use its unmodified exit
# duration at the new retirement. Do not carry an already-faded tail forward.
from hexa_v31.composition_qa import _state
held = event('READABLE_CONTEXT', .28, .52, (0, 0, .18, .25), end=2., hit=.5)
held['preset_exit'] = dict(name='DISAPPEAR_DOWN_SCALE', start_seconds=1.1, duration_seconds=.6)
revealed = event('NEW_CONTEXT', .72, .52, (0, 0, .18, .25), start=1., hit=1.8, primary=True)
readable_plan = {'events': [held, revealed], 'visual_cards': {'cards': [card([held, revealed])]}}
readable_result = finalize_reference_density_topology(readable_plan)
assert readable_result['holds_committed'] == 1, readable_result
assert abs(held['preset_exit']['start_seconds'] + .6 - held['physical_end_seconds']) < 1e-6
assert _state(held, 2.5)[2] >= .85 and _state(held, 3.2)[2] >= .85
assert _state(held, 3.8)[2] < _state(held, 3.2)[2]  # intentional exit is preserved

# The same hierarchy decision is independent of IDs, absolute narration time,
# and duration; amplitude changes with ink/role/available geometric headroom.
from hexa_v31.layout.reference_geometry_finalizer import _hierarchy_scale_candidates
focal = event('PACKAGE_X_FOCAL', .5, .52, (0, 0, .18, .24), primary=True, ink=.4)
reveal = event('PACKAGE_X_RESULT', .8, .52, (0, 0, .1, .12), hit=2.8)
reveal['composition_role'] = 'RESULT'
base_candidates = _hierarchy_scale_candidates(focal, reveal, [focal, reveal], [.5, .52], 1.14)
assert base_candidates and len(base_candidates) <= 4
renamed = copy.deepcopy(focal)
renamed.update(event_id='OTHER_FOCAL', scene_id='OTHER_SCENE', visual_card_id='OTHER_CARD',
               start_seconds=21., end_seconds=38., perceptual_hit_seconds=24.)
assert _hierarchy_scale_candidates(renamed, reveal, [renamed, reveal], [.5, .52], 1.14) == base_candidates
support_role = dict(focal, attention_priority='SUPPORTING')
assert _hierarchy_scale_candidates(support_role, reveal, [support_role, reveal], [.5, .52], 1.14)[0] < base_candidates[0]
assert _hierarchy_scale_candidates(focal, reveal, [focal, reveal], [.20, .52], 1.14)[0] < base_candidates[0]
dense = dict(focal, source_bbox_norm=[0, 0, .5, .6], visible_ink_fraction=1.)
assert not _hierarchy_scale_candidates(dense, reveal, [dense, reveal], [.5, .52], 1.14)
print('V31_REFERENCE_READABLE_RETENTION_AND_NORMALIZED_HIERARCHY_PASS')

# Static scale search must try another existing semantic slot before shrinking
# a focal subject beside a blocker. Names/durations do not select the result.
for prefix, duration in [('SHORT_PACKAGE', 1.6), ('DIFFERENT_SCRIPT', 2.)]:
    subject = event(prefix + '_SUBJECT', .5, .52, (0, 0, .2, .26), end=duration, primary=True)
    blocker = event(prefix + '_CONTEXT', .70, .52, (0, 0, .1, .16), end=duration)
    slot_card = card([subject, blocker], end=duration)
    slot_plan = {'events': [subject, blocker], 'visual_cards': {'cards': [slot_card]}}
    result = finalize_reference_geometry(slot_plan)
    assert result['pass'] and subject['reference_root_scale_factor'] >= 1.7, result
    assert subject['card_rest_position_norm'][0] < .4, subject
    assert not subject['position_animated'] and not subject['translation_safe_after_occlusion']
print('V31_REFERENCE_SEMANTIC_NEGATIVE_SPACE_FIT_PASS')

# Actual center authority is shared by cohort fitting and semantic continuation.
from hexa_v31.layout.position_authority import has_actual_center_travel
for name, travel in [('APPEAR_HIGH_SCALE',False), ('DISAPPEAR_DOWN_SCALE',False),
                     ('WITHIN_MIDDLE_TO_LEFT',True), ('ENTRY_LEFT_TO_MIDDLE',True)]:
    a = event('AUTHORITY_OWNER', .25,.52,(0,0,.12,.16),end=6.,hit=.5,primary=True)
    b = event('AUTHORITY_FIRST',.72,.28,(0,0,.12,.16),start=1.4,end=6.,hit=2.4)
    c = event('AUTHORITY_LATER',.72,.74,(0,0,.12,.16),start=3.8,end=6.,hit=4.8)
    p = {'events':[a,b,c], 'visual_cards':{'cards':[card([a,b,c],end=6.)]}}
    # Establish the existing two-state relationship, then exercise only the
    # continuation guard with an authored action that has already finished.
    finalize_reference_geometry(p)
    a['composition_states'] = a['composition_states'][:2]
    a['layout_scale_multiplier'] = 1.
    a['preset_actions'] = [dict(name=name,start_seconds=2.7,duration_seconds=.6)]
    assert has_actual_center_travel(a) is travel
    stats = dict(semantic_cascade_candidates_evaluated=0,semantic_cascade_committed=0,
                 semantic_cascade_event_ids=[],semantic_cascade_rejections={})
    _continue_semantic_sequences(p,30.,stats)
    assert bool(stats['semantic_cascade_committed']) is (not travel), (name,stats)
    a['position_animated'] = True
    assert has_actual_center_travel(a)
print('V31_SHARED_CENTER_AUTHORITY_SEMANTIC_CONTINUATION_PASS')

# Exhausted owner headroom is a focus-transfer opportunity, not permission to
# erase the semantic beat or manufacture an owner motion delta.
a=event('SATURATED_OWNER',.192,.52,(0,0,.2,.2),end=6.,hit=.5,primary=True)
a['composition_states']=[dict(state_id='A',start_seconds=.5,center_norm=[.192,.52],scale_multiplier=1.12),
                         dict(state_id='B',start_seconds=2.,transition_duration_seconds=.48,
                              center_norm=[.192,.52],scale_multiplier=1.12)]
b=event('NEW_SOURCE',.72,.52,(0,0,.32,.4),start=4.,end=6.,hit=4.8)
b['preset_entry']=dict(name='APPEAR_HIGH_SCALE',start_seconds=4.,duration_seconds=.8)
p={'events':[a,b],'visual_cards':{'cards':[card([a,b],end=6.)]}}
s=dict(semantic_cascade_candidates_evaluated=0,semantic_cascade_committed=0,
       semantic_cascade_event_ids=[],semantic_cascade_rejections={})
_continue_semantic_sequences(p,30.,s)
assert s['semantic_cascade_committed']==1,s
assert len(a['composition_states'])==3
assert a['composition_states'][-1]['scale_multiplier']==1.12
assert b['composition_participant_states'][-1]['owner_state_id']==a['composition_states'][-1]['state_id']
assert b['composition_participant_states'][0]['start_seconds']==4.
print('V31_SATURATED_OWNER_PARTICIPANT_FOCUS_TRANSFER_PASS')
