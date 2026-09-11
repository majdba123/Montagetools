from __future__ import annotations

import cv2
import numpy as np

_EXACT_W=320
_EXACT_H=180
_EXACT_SAMPLE_HZ=4.0
_EXACT_NONWHITE_DELTA=10
_EXACT_MOTION_DELTA=13


def _authored_states(motion_plan):
    rows=[]
    for event in motion_plan.get('events') or []:
        if event.get('suppressed_by_card_density'):
            continue
        for container in ('composition_states','composition_participant_states'):
            for state in event.get(container) or []:
                if not state.get('state_id'):
                    continue
                duration=max(0.0,float(state.get('transition_duration_seconds') or 0.0))
                # Zero-duration initial anchors describe the starting composition;
                # they are not an encoded transition and therefore cannot be
                # required to produce a frame delta on their own.
                if duration<=1e-9 and not state.get('previous_state_id'):
                    continue
                rows.append((event,state,container))
    return rows


def _exact_sample_metrics(samples, motion):
    if not samples:
        return {
            'sample_count':0,'occupancy_mean':0.0,'occupancy_median':0.0,
            'frames_lt10_ratio':1.0,'frames_lt15_ratio':1.0,
            'motion_mean':0.0,'motion_median':0.0,'near_static_ratio':1.0,
        }
    occ=np.asarray(samples,dtype=np.float64)
    mov=np.asarray(motion,dtype=np.float64)
    return {
        'sample_count':int(len(occ)),
        'occupancy_mean':float(occ.mean()),
        'occupancy_median':float(np.median(occ)),
        'frames_lt10_ratio':float(np.mean(occ<.10)),
        'frames_lt15_ratio':float(np.mean(occ<.15)),
        'motion_mean':float(mov.mean()) if len(mov) else 0.0,
        'motion_median':float(np.median(mov)) if len(mov) else 0.0,
        'near_static_ratio':float(np.mean(mov<.005)) if len(mov) else 1.0,
    }


def verify_encoded_composition(video_path,motion_plan,projected_density=None,fps=30.0,render_edit_map=None):
    """Prove authored P3/P4 composition states survived into encoded pixels.

    State attribution is performed against the exact render sources. In the
    same decode pass we compute the frozen 4 Hz / 320x180 closure metrics. When
    ``projected_density`` is supplied (the production pipeline path), P3/P4
    quality thresholds are hard gates. Unit-level attribution probes may omit
    it and remain focused on attribution rather than whole-program density.
    """
    cap=cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {'schema':'HEXA_ENCODED_ADAPTIVE_COMPOSITION_QA_V3','pass':False,
                'failures':[{'reason':'ENCODED_VIDEO_OPEN_FAILED','path':str(video_path)}]}
    actual_fps=float(cap.get(cv2.CAP_PROP_FPS) or fps)
    frames={}
    states=_authored_states(motion_plan)
    for event,state,container in states:
        t=float(state.get('start_seconds',0));transition=float(state.get('transition_duration_seconds') or 0.0)
        dd=max(.1,transition or .1)
        for sample in (max(0.0,t-.12),t+dd+.12,t+transition*.5):
            frames.setdefault(int(round(sample*actual_fps)),None)

    occupancies=[];index=0
    exact_occupancy=[];exact_motion=[];previous_exact=None
    sample_number=0;next_sample_index=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY);mn=frame.min(axis=2)
        occupancies.append(float(np.mean((mn<248)|(gray<248))))
        if index in frames:frames[index]=gray
        if index>=next_sample_index:
            small=cv2.resize(frame,(_EXACT_W,_EXACT_H),interpolation=cv2.INTER_AREA)
            occupancy=float(np.mean((255-small.min(axis=2).astype(np.int16))>_EXACT_NONWHITE_DELTA))
            exact_occupancy.append(occupancy)
            if previous_exact is not None:
                diff=cv2.absdiff(small,previous_exact)
                exact_motion.append(float(np.mean(diff.max(axis=2)>_EXACT_MOTION_DELTA)))
            previous_exact=small
            sample_number+=1
            next_sample_index=max(index+1,int(round(sample_number*actual_fps/_EXACT_SAMPLE_HZ)))
        index+=1
    cap.release()

    rows=[];verified=0;attributed=0
    for event,state,container in states:
        t=float(state.get('start_seconds',0));transition=float(state.get('transition_duration_seconds') or 0.0);dd=max(.1,transition or .1)
        before=frames.get(int(round(max(0.0,t-.12)*actual_fps)))
        after=frames.get(int(round((t+dd+.12)*actual_fps)))
        diff=None if before is None or after is None else cv2.absdiff(before,after)
        delta=0.0 if diff is None else float(np.mean(diff)/255.0)
        changed=0.0 if diff is None else float(np.mean(diff>=10))
        meaningful=delta>=.003 and changed>=.012
        from hexa_v31.layout.composition_attribution import attribute_composition
        times=(round(max(0.0,t-.12)*actual_fps)/actual_fps,round((t+dd+.12)*actual_fps)/actual_fps)
        attribution=attribute_composition(event,state,before,after,times,render_edit_map)
        attribution['attribution_sample_times']=list(times)
        if not attribution['actor_attributable_pass']:
            # A committed short handoff can finish immediately before a legal
            # physical retirement. Inspect the authored midpoint while its
            # source actors still exist; do not lower any pixel threshold.
            midpoint=int(round((t+transition*.5)*actual_fps)) if transition>0 else None
            if midpoint is not None:
                middle_times=(times[0],midpoint/actual_fps)
                middle=attribute_composition(event,state,before,frames.get(midpoint),middle_times,render_edit_map)
                if middle['actor_attributable_pass']:
                    attribution=middle
                    attribution['attribution_sample_times']=list(middle_times)
                    attribution['attribution_sample_authority']='AUTHORED_TRANSITION_MIDPOINT'
                    middle_frame=frames.get(midpoint)
                    if before is not None and middle_frame is not None:
                        diff=cv2.absdiff(before,middle_frame)
                        delta=float(np.mean(diff)/255.0)
                        changed=float(np.mean(diff>=10))
                        meaningful=delta>=.003 and changed>=.012
        passed=bool(meaningful and attribution['actor_attributable_pass'])
        verified+=int(meaningful);attributed+=int(passed)
        rows.append({
            'event_id':event.get('event_id'),'card_id':state.get('card_id',event.get('visual_card_id')),
            'state_id':state.get('state_id'),'state_container':container,
            'sequence_envelope':bool(state.get('sequence_envelope')),
            'envelope_track':state.get('envelope_track'),'semantic_beat':state.get('semantic_beat'),
            'transition_seconds':t,'transition_duration_seconds':transition,
            'encoded_pixel_delta':round(delta,6),'full_frame_delta':round(delta,6),
            'encoded_changed_pixel_ratio':round(changed,6),**attribution,'pass':passed,
        })

    encoded_mean=float(np.mean(occupancies)) if occupancies else 0.0
    encoded_median=float(np.median(occupancies)) if occupancies else 0.0
    exact=_exact_sample_metrics(exact_occupancy,exact_motion)
    planned_safe=float((projected_density or {}).get('median_estimated_alpha_coverage') or 0.0)
    safe_area=.84*.80
    planned_full_equivalent=planned_safe*safe_area
    divergence=abs(planned_full_equivalent-exact['occupancy_median']) if planned_safe>0 else 0.0

    failures=[]
    if states and verified<len(states):
        failures.append({'reason':'PLANNED_RECOMPOSITION_NOT_ENCODED','planned':len(states),'verified':verified})
    if states and attributed<len(states):
        failures.append({'reason':'PLANNED_RECOMPOSITION_NOT_ACTOR_ATTRIBUTABLE','planned':len(states),'verified':attributed})

    p3_gates={
        'encoded_mean_occupancy_ge_24pct':{'pass':exact['occupancy_mean']>=.24,'actual':round(exact['occupancy_mean'],6),'target_min':.24},
        'encoded_median_occupancy_ge_20pct':{'pass':exact['occupancy_median']>=.20,'actual':round(exact['occupancy_median'],6),'target_min':.20},
        'encoded_frames_lt10_le_8pct':{'pass':exact['frames_lt10_ratio']<=.08,'actual':round(exact['frames_lt10_ratio'],6),'target_max':.08},
        'encoded_frames_lt15_le_25pct':{'pass':exact['frames_lt15_ratio']<=.25,'actual':round(exact['frames_lt15_ratio'],6),'target_max':.25},
    }
    p3_pass=all(g['pass'] for g in p3_gates.values())

    sequence_rows=[r for r in rows if r.get('envelope_track')=='SEMANTIC_SEQUENCE']
    participant_sequence_rows=[r for r in sequence_rows if r.get('state_container')=='composition_participant_states']
    sequence_stats=motion_plan.get('reference_staggered_sequence_finalizer') or {}
    planned_sequence_count=len(sequence_stats.get('sequences') or [])
    sequence_required=planned_sequence_count>0
    sequence_materiality_pass=(not sequence_required) or (bool(sequence_rows) and all(r.get('pass') for r in sequence_rows))
    p4_gates={
        'semantic_sequence_destinations_encoded':{
            'pass':sequence_materiality_pass,'planned_sequence_count':planned_sequence_count,
            'encoded_sequence_state_count':len(sequence_rows),'verified_sequence_state_count':sum(bool(r.get('pass')) for r in sequence_rows),
        },
        'exact_motion_mean_in_reference_direction':{
            'pass':.13<=exact['motion_mean']<=.20,'actual':round(exact['motion_mean'],6),'target_min':.13,'target_max':.20,
        },
        'exact_near_static_ratio_materially_below_baseline':{
            'pass':exact['near_static_ratio']<=.28,'actual':round(exact['near_static_ratio'],6),'target_max':.28,
        },
    }
    p4_pass=all(g['pass'] for g in p4_gates.values())

    closure_enforced=projected_density is not None
    if closure_enforced and not p3_pass:
        failures.append({'reason':'P3_ENCODED_DENSITY_TARGET_NOT_MET',
                         'failed_gates':[name for name,gate in p3_gates.items() if not gate['pass']]})
    if closure_enforced and not p4_pass:
        failures.append({'reason':'P4_ENCODED_CHOREOGRAPHY_TARGET_NOT_MET',
                         'failed_gates':[name for name,gate in p4_gates.items() if not gate['pass']]})

    return {
        'schema':'HEXA_ENCODED_ADAPTIVE_COMPOSITION_QA_V3','pass':not failures,
        'p34_closure_enforced':closure_enforced,
        'planned_recomposition_count':len(states),'encoded_recomposition_verified_count':verified,
        'actor_attributable_verified_count':attributed,
        'composition_state_count':sum(1 for _,_,c in states if c=='composition_states'),
        'participant_state_count':sum(1 for _,_,c in states if c=='composition_participant_states'),
        'semantic_sequence_planned_count':planned_sequence_count,
        'semantic_sequence_state_count':len(sequence_rows),
        'semantic_sequence_verified_count':sum(bool(r.get('pass')) for r in sequence_rows),
        'semantic_sequence_participant_state_count':len(participant_sequence_rows),
        'semantic_sequence_participant_verified_count':sum(bool(r.get('pass')) for r in participant_sequence_rows),
        'p4_semantic_sequence_encoded_pass':sequence_materiality_pass,
        'encoded_occupancy_mean':round(encoded_mean,6),'encoded_occupancy_median':round(encoded_median,6),
        'exact_normalized_4hz_320x180':{k:round(v,6) if isinstance(v,float) else v for k,v in exact.items()},
        'p3_encoded_density_gates':p3_gates,'p3_encoded_density_pass':p3_pass,
        'p4_encoded_choreography_gates':p4_gates,'p4_encoded_choreography_pass':p4_pass,
        'planned_visible_ink_safe_frame_median':round(planned_safe,6),
        'planned_visible_ink_full_frame_equivalent':round(planned_full_equivalent,6),
        'planned_encoded_occupancy_divergence_diagnostic':round(divergence,6),
        'rows':rows,'failures':failures,'vacuous':not bool(states),
        'metric_authority':'FROZEN_4HZ_320X180_AREA__NONWHITE_DELTA_GT10__MOTION_MAX_CHANNEL_GT13',
    }
