from __future__ import annotations
import cv2,numpy as np

def verify_encoded_composition(video_path,motion_plan,projected_density=None,fps=30.0,render_edit_map=None):
    """Prove that authored composition states changed encoded pixels."""
    cap=cv2.VideoCapture(str(video_path));actual_fps=float(cap.get(cv2.CAP_PROP_FPS) or fps);frames={}
    states=[]
    for event in motion_plan.get('events') or []:
        for state in (event.get('composition_states') or [])[1:]:
            states.append((event,state))
            t=float(state.get('start_seconds',0));dd=max(.1,float(state.get('transition_duration_seconds') or .1))
            for sample in (max(0.0,t-.12),t+dd+.12,t+float(state.get('transition_duration_seconds') or dd)*.5):frames.setdefault(int(round(sample*actual_fps)),None)
    occupancies=[];index=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY);mn=frame.min(axis=2)
        occupancies.append(float(np.mean((mn<248)|(gray<248))))
        if index in frames:frames[index]=gray
        index+=1
    cap.release();rows=[];verified=0;attributed=0
    for event,state in states:
        t=float(state.get('start_seconds',0));dd=max(.1,float(state.get('transition_duration_seconds') or .1));before=frames.get(int(round(max(0.0,t-.12)*actual_fps)));after=frames.get(int(round((t+dd+.12)*actual_fps)))
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
            # physical retirement. Keep the original full-frame gate unchanged,
            # but also inspect the authored transition midpoint, not only pixels
            # after its actors have ceased to exist.
            midpoint=int(round((t+float(state.get('transition_duration_seconds') or dd)*.5)*actual_fps))
            middle_times=(times[0],midpoint/actual_fps)
            middle=attribute_composition(event,state,before,frames.get(midpoint),middle_times,render_edit_map)
            if middle['actor_attributable_pass']:
                attribution=middle
                attribution['attribution_sample_times']=list(middle_times)
                attribution['attribution_sample_authority']='AUTHORED_TRANSITION_MIDPOINT'
        verified+=int(meaningful);attributed+=int(meaningful and attribution['actor_attributable_pass'])
        rows.append({'event_id':event.get('event_id'),'state_id':state.get('state_id'),'transition_seconds':t,'encoded_pixel_delta':round(delta,6),'full_frame_delta':round(delta,6),'encoded_changed_pixel_ratio':round(changed,6),**attribution,'pass':meaningful and attribution['actor_attributable_pass']})
    encoded_mean=float(np.mean(occupancies)) if occupancies else 0.0;encoded_median=float(np.median(occupancies)) if occupancies else 0.0
    planned=float((projected_density or {}).get('median_estimated_alpha_coverage') or 0.0);divergence=abs(planned-encoded_median)
    failures=[]
    if states and verified<len(states):failures.append({'reason':'PLANNED_RECOMPOSITION_NOT_ENCODED','planned':len(states),'verified':verified})
    if states and attributed<len(states):failures.append({'reason':'PLANNED_RECOMPOSITION_NOT_ACTOR_ATTRIBUTABLE','planned':len(states),'verified':attributed})
    if planned>0 and divergence>.10:failures.append({'reason':'PLANNED_VISIBLE_INK_DIVERGES_FROM_ENCODED_PIXELS','planned_median':planned,'encoded_median':encoded_median,'absolute_divergence':divergence})
    return {'schema':'HEXA_ENCODED_ADAPTIVE_COMPOSITION_QA_V2','pass':not failures,'planned_recomposition_count':len(states),'encoded_recomposition_verified_count':verified,'actor_attributable_verified_count':attributed,'encoded_occupancy_mean':round(encoded_mean,6),'encoded_occupancy_median':round(encoded_median,6),'planned_visible_ink_median':round(planned,6),'planned_encoded_occupancy_divergence':round(divergence,6),'rows':rows,'failures':failures,'vacuous':not bool(states)}
