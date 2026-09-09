"""Source-backed, nonperiodic semantic sequencing on the final card clock.

The sequence envelope uses existing sealed composition/participant states.
It never retimes a P2 preset, extends a carrier, or manufactures source actors.
"""
from __future__ import annotations

import copy
import math

from hexa_v31.composition_solver import composition_state_at, _in_safe
from hexa_v31.composition_qa import _state as _visible_state
from hexa_v31.layout.position_authority import has_actual_center_travel
from hexa_v31.layout.reference_geometry_finalizer import _candidate_safe, _physical_interval
from hexa_v31.layout.reference_residual_closure import _card_events, _semantic_pair_allowed

AUTHORITY = 'REFERENCE_SEMANTIC_STAGGERED_SEQUENCE_V1'


def _onset(event):
    return max(_physical_interval(event)[0], float((event.get('preset_entry') or {}).get('start_seconds', event.get('start_seconds', 0))))


def _causal(event):
    entry=event.get('preset_entry') or {}
    return bool(entry.get('interaction_id') or entry.get('semantic_action') or event.get('preset_actions'))


def _end(event):
    return min(_physical_interval(event)[1], float(event.get('motion_end_seconds', event.get('end_seconds', 0))),
               float((event.get('preset_exit') or {}).get('start_seconds', _physical_interval(event)[1])))


def _related(card, a, b):
    phases=(card.get('story_phase_plan') or {}).get('phases') or []
    memberships=[{i for i,p in enumerate(phases) if e['event_id'] in (p.get('event_ids') or [])} for e in (a,b)]
    if all(memberships) and not memberships[0].intersection(memberships[1]):
        return False
    return _semantic_pair_allowed(card,a,b)


def _sequence_safe(plan, cohort, fps):
    if not _candidate_safe(plan,cohort,fps):return False
    for e in cohort:
        start,end=_physical_interval(e)
        for frame in range(math.ceil(start*fps),math.ceil(end*fps)):
            state=_visible_state(e,frame/fps)
            if state and state[2]>.22 and not _in_safe(state[3]):return False
    return True


def _safe_envelope_cap(event, fps):
    from hexa_v31.composition_solver import SAFE_X, SAFE_Y
    cap=1.
    start,end=_physical_interval(event)
    for frame in range(math.ceil(start*fps),math.ceil(end*fps)):
        state=_visible_state(event,frame/fps)
        if not state or state[2]<=.22:continue
        (cx,cy),_,_,(_,_,w,h)=state
        cap=min(cap,2*(cx-SAFE_X[0])/max(w,1e-9),2*(SAFE_X[1]-cx)/max(w,1e-9),
                2*(cy-SAFE_Y[0])/max(h,1e-9),2*(SAFE_Y[1]-cy)/max(h,1e-9))
    return max(0.,cap-1e-6)


def _state(event, owner, phase, start, duration, scale, visibility, previous=None):
    return dict(state_id=f"{owner['event_id']}::SEQUENCE::{event['event_id']}::{phase}",
                authority=AUTHORITY, sequence_envelope=True, semantic_beat=phase,
                start_seconds=round(start, 6), transition_duration_seconds=round(duration, 6),
                scale_multiplier=scale, visibility=visibility,
                center_norm=list(event.get('card_rest_position_norm') or [.5,.5]),
                previous_state_id=previous, card_id=event['visual_card_id'])


def _append(event, state, owner, owner_state_id, ids):
    state.update(owner_event_id=owner['event_id'], owner_state_id=owner_state_id,
                 participating_event_ids=ids)
    focal_destination=state['semantic_beat'] in {'FOCUS_TRANSFER','COMPOSITION_REBUILD'}
    initial_anchor=state['semantic_beat'] in {'AWAIT_REVEAL','PRESERVE_CAUSAL_REVEAL'} and not event.get('composition_states')
    field='composition_states' if event is owner and (focal_destination or initial_anchor) else 'composition_participant_states'
    event.setdefault(field, []).append(state)


def _pixel_evidence(events, before_events, start, end, focus, rebuild, neighbors=()):
    """Bounded actual-source probe, using runtime rendering and frozen 4 Hz QA."""
    import numpy as np
    import cv2
    from hexa_v31.render.scene_media import prepare_composition_actor, _event_state, _apply
    from hexa_v31.layout.composition_attribution import attribute_composition
    width,height=320,180
    def materialize(event):
        from PIL import Image
        row=copy.deepcopy(event)
        if not row.get('source_path'):
            row['source_path']=row['source_layer_path']
            with Image.open(row['source_path']) as source:
                w,h=source.size
            row['base_fit_scale_percent']=min(1920/w,1080/h)*100*float(row.get('reference_camera_scale') or 1.)
        return row
    events=[materialize(e) for e in events]
    before_events=[materialize(e) for e in before_events]
    neighbors=[materialize(e) for e in neighbors]
    def prepare(rows):
        return [prepare_composition_actor(e,width,height) for e in rows]
    current=prepare([*events,*neighbors]);baseline=prepare([*before_events,*neighbors])
    def frame(prepared,t):
        canvas=np.full((height,width,3),255,np.uint8);population=0
        for e,img in prepared:
            value=_event_state(e,t)
            if value:
                pos,scale,opacity=value
                if opacity>.22:population+=1
                _apply(canvas,img,pos,opacity,scale,width,height)
        return canvas,population
    times=np.arange(start,end,0.25)
    def metrics(prepared):
        frames=[];pop=[]
        for t in times:
            image,count=frame(prepared,float(t));frames.append(image);pop.append(count)
        a=np.asarray(frames,dtype=np.int16)
        changed=(np.abs(np.diff(a,axis=0)).max(axis=3)>13).mean(axis=(1,2))
        return dict(near_static_ratio=float((changed<.005).mean()),motion_mean=float(changed.mean()),
                    mean_population=float(np.mean(pop)),max_population=max(pop),
                    concurrent_seconds=float(sum(v>=2 for v in pop)*.25))
    before=metrics(baseline);after=metrics(current)
    attribution=[]
    for state in (focus,rebuild):
        t=float(state['start_seconds']);dt=float(state['transition_duration_seconds'])
        a,_=frame(current,t);b,_=frame(current,t+dt)
        result=attribute_composition(events[0],state,cv2.cvtColor(a,cv2.COLOR_RGB2GRAY),
                                     cv2.cvtColor(b,cv2.COLOR_RGB2GRAY),(t,t+dt),{'events':[*events,*neighbors]})
        attribution.append(result)
    passed=(all(r['actor_attributable_pass'] for r in attribution)
            and after['near_static_ratio'] < before['near_static_ratio']
            and after['concurrent_seconds']>=.5)
    return dict(pass_=passed,before=before,after=after,attribution=attribution,
                authority='ACTUAL_SOURCE_RUNTIME_4HZ_320X180')


def finalize_reference_staggered_sequence(plan, fps=30.0):
    stats=dict(authority=AUTHORITY,changed=False,sequences=[],rejections=[],source_limited_card_ids=[])
    def reject(card, reason, ids=()):
        stats['rejections'].append(dict(card_id=card['card_id'],reason=reason,event_ids=list(ids)))
    for card in (plan.get('visual_cards') or {}).get('cards') or []:
        rows=_card_events(plan,card)
        roots=[]
        for e in rows:
            eid=e['event_id']
            if str(e.get('render_mode') or 'ROOT_ATOMIC')!='ROOT_ATOMIC':
                reject(card,'PARTITION_CONSTRAINT',[eid]);continue
            if has_actual_center_travel(e):
                reject(card,'ACTUAL_CENTER_TRAVEL',[eid]);continue
            if not (e.get('source_path') or e.get('source_layer_path')) or e.get('visible_ink_fraction') is None:
                reject(card,'MISSING_SOURCE_EVIDENCE',[eid]);continue
            if any(s.get('sequence_envelope') for key in ('composition_states','composition_participant_states') for s in e.get(key) or []):
                continue
            roots.append(e)
        if len(rows)==1 and len(roots)==1:
            stats['source_limited_card_ids'].append(card['card_id']);reject(card,'SOURCE_LIMITED_SINGLE_ACTOR',[roots[0]['event_id']])
        if len(roots)<2:continue
        roots.sort(key=lambda e:(_onset(e),0 if e.get('attention_priority')=='PRIMARY' else 1,str(e['event_id'])))
        # Skip expired introductions when choosing the sentence owner. Temporal
        # adjacency alone never grants relationship authority.
        opportunities=[(a,b) for i,a in enumerate(roots) for b in roots[i+1:]
                       if _related(card,a,b)
                       and min(_end(a),_end(b))-max(_onset(a),_onset(b))>=1.2]
        if not opportunities:
            relationship=any(_related(card,a,b) for i,a in enumerate(roots) for b in roots[i+1:])
            reject(card,'INSUFFICIENT_LIFETIME' if relationship else 'UNRELATED_SEMANTICS',[e['event_id'] for e in roots]);continue
        owner,first_support=opportunities[0]
        related=[e for e in roots if e is not owner and _onset(e)>=_onset(owner) and _related(card,owner,e)]
        for e in roots:
            if e is owner:continue
            if e not in related:reject(card,'UNRELATED_SEMANTICS',[owner['event_id'],e['event_id']])
        if not related:continue
        # One focal/support/context sentence. Further actors retain their own
        # authored semantics and participate in the full-plan safety check.
        cohort=[owner,first_support]
        for e in related:
            if e is first_support:continue
            common_end=min(_end(e),*map(_end,cohort))
            if common_end-max(_onset(e),*map(_onset,cohort))>=3.5:
                cohort.append(e);break
        start=max(float(card.get('start_seconds',0)),_onset(owner))
        end=min(float(card['end_seconds']),*map(_end,cohort))
        span=end-start
        entry=min(.65,max(.25,span*.13))
        stagger=min(.65,max(.25,span*.12))
        onsets=[start]
        for e in cohort[1:]:
            causal=_causal(e)
            natural=max(start,_onset(e))
            onsets.append(natural if causal else max(natural,onsets[-1]+stagger))
        settled=max(max(t+entry,float((e.get('preset_entry') or {}).get('start_seconds',t))+float((e.get('preset_entry') or {}).get('duration_seconds') or 0)) for e,t in zip(cohort,onsets))
        readable=max(.45,math.ceil(min(.65,max(0.,end-settled)*.25)*fps)/fps)
        focus_start=settled+readable
        transition=min(.65,(end-focus_start-readable*.5)/2)
        rebuild_start=focus_start+transition+readable*.25
        if transition<.20 or rebuild_start+transition+readable*.25>end+1e-6 or onsets[1]<=onsets[0]+1/fps:
            reject(card,'INSUFFICIENT_LIFETIME',[e['event_id'] for e in cohort]);continue
        snapshots=[copy.deepcopy(e) for e in cohort]
        safe_caps=[_safe_envelope_cap(e,fps) for e in cohort]
        ids=[e['event_id'] for e in cohort]
        accepted=False
        for promotion in (1.12,1.06,1.0):
            for e,snapshot in zip(cohort,snapshots):e.clear();e.update(copy.deepcopy(snapshot))
            for i,(e,onset) in enumerate(zip(cohort,onsets)):
                # Causal preset reveals retain exact P2 timing. Their subsequent
                # focus may still take part in the linked composition sentence.
                if _causal(e):
                    anchor=_state(e,owner,'PRESERVE_CAUSAL_REVEAL',_physical_interval(e)[0],0,safe_caps[i],1)
                    _append(e,anchor,owner,anchor['state_id'],ids)
                    continue
                hidden=_state(e,owner,'AWAIT_REVEAL',_physical_interval(e)[0],0,(.78 if i else .90)*safe_caps[i],0)
                reveal=_state(e,owner,'ESTABLISH' if i==0 else 'OVERLAPPING_REVEAL',onset,entry,safe_caps[i],1,hidden['state_id'])
                _append(e,hidden,owner,hidden['state_id'],ids)
                _append(e,reveal,owner,reveal['state_id'],ids)
            focus_id=f"{owner['event_id']}::SEQUENCE::{owner['event_id']}::FOCUS_TRANSFER"
            rebuild_id=f"{owner['event_id']}::SEQUENCE::{owner['event_id']}::COMPOSITION_REBUILD"
            focus_state=rebuild_state=None
            for i,e in enumerate(cohort):
                # Promote the incoming support, retaining the established focal.
                # Rebuild then redistributes hierarchy toward context/handoff.
                focus_scale=.84 if i==0 else (promotion if i==1 else .92)
                final_scale=min(1.04,promotion) if i==0 else (.92 if i==1 else promotion)
                a=_state(e,owner,'FOCUS_TRANSFER',focus_start,transition,focus_scale*safe_caps[i],1)
                b=_state(e,owner,'COMPOSITION_REBUILD',rebuild_start,transition,final_scale*safe_caps[i],1,a['state_id'])
                # Attribution removes only each destination, retaining its
                # preceding reveal/relationship state for the counterfactual.
                earlier=[s for key in ('composition_states','composition_participant_states') for s in e.get(key) or [] if s.get('sequence_envelope')]
                a['previous_state_id']=max(earlier,key=lambda s:float(s['start_seconds']))['state_id']
                _append(e,a,owner,focus_id,ids);_append(e,b,owner,rebuild_id,ids)
                if i==0:focus_state,rebuild_state=a,b
            if not _sequence_safe(plan,cohort,fps):
                reject(card,'COLLISION_OR_SAFE_FRAME',ids);continue
            try:
                neighbors=[e for e in plan.get('events') or [] if e not in cohort
                           and not e.get('suppressed_by_card_density')
                           and _physical_interval(e)[0]<end and _physical_interval(e)[1]>start]
                evidence=_pixel_evidence(cohort,snapshots,start,end,focus_state,rebuild_state,neighbors)
            except (OSError,KeyError,ValueError) as exc:
                reject(card,'SOURCE_PROBE_FAILED',ids)
                stats['rejections'][-1]['detail']=str(exc)
                continue
            if not evidence['pass_']:
                reject(card,'NO_MATERIAL_ENCODED_EFFECT',ids);continue
            accepted=True
            owner['meaningful_recomposition']=True
            stats['sequences'].append(dict(card_id=card['card_id'],owner_event_id=owner['event_id'],
                participant_event_ids=ids,semantic_roles=[e.get('semantic_role') or e.get('composition_role') for e in cohort],
                relationship_source='SAME_SCENE_OR_SHARED_STORY_PHASE',sequence_type='ESTABLISH_OVERLAP_FOCUS_REBUILD_RETAIN',
                reveal_onsets=onsets,establish_interval=[start,onsets[1]],overlap_interval=[settled,end],
                focus_transfer_interval=[focus_start,focus_start+transition],recomposition_interval=[rebuild_start,rebuild_start+transition],
                handoff_interval=[rebuild_start+transition,end],reaction_authority='EXISTING_P2_ACTIONS_ONLY',
                before_static_hold_estimate=evidence['before']['near_static_ratio'],after_static_hold_estimate=evidence['after']['near_static_ratio'],
                before_simultaneous_actor_population=evidence['before'],after_simultaneous_actor_population=evidence['after'],
                before_hierarchy_state=[composition_state_at(e,focus_start)[1] for e in snapshots],
                after_hierarchy_state=[composition_state_at(e,focus_start+transition)[1] for e in cohort],
                encoded_attribution_expectation=evidence))
            stats['changed']=True
            break
        if not accepted:
            for e,snapshot in zip(cohort,snapshots):e.clear();e.update(snapshot)
    stats['pass']=True
    return stats
