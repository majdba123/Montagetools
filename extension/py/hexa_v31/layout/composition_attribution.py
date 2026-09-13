"""Conservative, source-backed attribution of encoded composition changes."""
from __future__ import annotations
import cv2
import numpy as np
from hexa_v31.render.scene_media import prepare_composition_actor, _event_state, _apply
from hexa_v31.render.scene_media import _draw_graphic,_text_state,_alpha_blend_top_left,render_text_rgba


def _gray_actor(event, image, t, width, height):
    canvas=np.full((height,width,3),255,dtype=np.uint8)
    state=_event_state(event,t)
    if state:
        position,scale,opacity=state
        _apply(canvas,image,position,opacity,scale,width,height)
    return cv2.cvtColor(canvas,cv2.COLOR_RGB2GRAY)


def attribute_composition(event,state,before,after,times,render_edit_map):
    """Require encoded change attributable to the authored state itself.

    Uses the exact framed render map, shared source preparation and evaluator.
    Unrelated actor support is excluded conservatively, even where it overlaps
    intended actors. A counterfactual without this destination distinguishes
    composition from concurrent preset entry/exit motion. No QA thresholds are
    reduced or normalized to a conveniently small ROI.
    """
    owner=str(event.get('event_id'));sid=str(state.get('state_id'))
    intended={owner,*map(str,state.get('participating_event_ids') or [])}
    result={'owner_delta':0.0,'participant_delta':0.0,'unrelated_delta':0.0,
            'attributed_changed_pixel_ratio':0.0,'actor_attributable_pass':False,
            'attribution_authority':'EXACT_RENDER_SOURCE_COUNTERFACTUAL_V2','actors':[]}
    if before is None or after is None or render_edit_map is None:
        return dict(result,attribution_failure='MISSING_ENCODED_OR_RENDER_SOURCE_EVIDENCE')
    height,width=before.shape
    unrelated=np.zeros_like(before,dtype=bool)
    unrelated_before=np.full_like(before,255);unrelated_after=unrelated_before.copy()
    # Typography and relationship graphics are unrelated render contributions
    # too. Exclude their actual support instead of crediting their animation.
    for index,t in enumerate(times):
        canvas=np.full((height,width,3),255,dtype=np.uint8)
        for graphic in render_edit_map.get('composition_graphic_events') or []:
            _draw_graphic(canvas,graphic,t)
        for text in render_edit_map.get('composition_text_events') or []:
            ts=_text_state(text,t)
            if ts:
                op,sc,dx,dy=ts
                layer=np.array(render_text_rgba(text,width,height).convert('RGBA'))
                x=int(round((float(text.get('x_norm',.1))+dx)*width))
                y=int(round((float(text.get('y_norm',.08))+dy)*height))
                _alpha_blend_top_left(canvas,layer,x,y,op,sc)
        gray=cv2.cvtColor(canvas,cv2.COLOR_RGB2GRAY)
        unrelated|=gray<248
        np.minimum(unrelated_before if index==0 else unrelated_after,gray,
                   out=unrelated_before if index==0 else unrelated_after)
    actor_rows=[];seen=set()
    for source in render_edit_map.get('events') or []:
        if source.get('suppressed_by_card_density'):continue
        eid=str(source.get('event_id'))
        start=float(source.get('physical_start_seconds',source.get('start_seconds',0)))
        end=float(source.get('physical_end_seconds',source.get('end_seconds',0)))
        if eid not in intended and not any(start<=t<end for t in times):continue
        try:
            runtime,image=prepare_composition_actor(source,width,height)
        except (OSError,ValueError,KeyError,cv2.error) as error:
            return dict(result,attribution_failure='UNREADABLE_RENDER_SOURCE',event_id=eid,detail=str(error))
        a=_gray_actor(runtime,image,times[0],width,height)
        b=_gray_actor(runtime,image,times[1],width,height)
        if eid not in intended:
            support=image.copy();support[:,:,:3]=0
            unrelated|=(_gray_actor(runtime,support,times[0],width,height)<248)|(_gray_actor(runtime,support,times[1],width,height)<248)
            np.minimum(unrelated_before,a,out=unrelated_before)
            np.minimum(unrelated_after,b,out=unrelated_after)
            continue
        seen.add(eid)
        if eid==owner and (
            (runtime.get('composition_states') or [])!=(event.get('composition_states') or [])
            or (runtime.get('composition_participant_states') or [])!=(event.get('composition_participant_states') or [])
        ):
            return dict(result,attribution_failure='PLANNER_RENDER_COMPOSITION_STATE_MISMATCH',event_id=eid)
        counter=dict(runtime)
        counter['composition_states']=[s for s in runtime.get('composition_states') or [] if str(s.get('state_id'))!=sid]
        # Exact participant destinations are first-class authored states too.
        # Remove the exact state under test; for an owner destination also omit
        # its linked B participant states while preserving their preceding A state.
        counter['composition_participant_states']=[
            s for s in runtime.get('composition_participant_states') or []
            if str(s.get('state_id'))!=sid
            and not (str(s.get('owner_state_id'))==sid and s.get('previous_state_id'))
        ]
        c=_gray_actor(counter,image,times[1],width,height)
        actor_rows.append((eid,a,b,c))
    if seen!=intended:
        return dict(result,attribution_failure='MISSING_INTENDED_ACTOR',missing_actor_ids=sorted(intended-seen))
    encoded=after.astype(np.int16)-before.astype(np.int16)
    result['unrelated_delta']=round(float(np.mean(cv2.absdiff(unrelated_before,unrelated_after))/255),6)
    owner_evidence=np.zeros_like(before);participant_evidence=np.zeros_like(before)
    for eid,a,b,c in actor_rows:
        temporal=b.astype(np.int16)-a.astype(np.int16)
        authored=cv2.absdiff(b,c)
        concordant=(np.sign(encoded)==np.sign(temporal))&(~unrelated)
        evidence=np.minimum(np.minimum(np.abs(encoded),np.abs(temporal)),authored)
        evidence=np.where(concordant,evidence,0).astype(np.uint8)
        target=owner_evidence if eid==owner else participant_evidence
        np.maximum(target,evidence,out=target)
        result['actors'].append({'event_id':eid,'role':'OWNER' if eid==owner else 'PARTICIPANT',
            'source_temporal_delta':round(float(np.mean(np.abs(temporal))/255),6),
            'authored_state_delta':round(float(np.mean(authored)/255),6),
            'encoded_attributable_delta':round(float(np.mean(evidence)/255),6)})
    combined=np.maximum(owner_evidence,participant_evidence)
    delta=float(np.mean(combined)/255);changed=float(np.mean(combined>=10))
    result.update(owner_delta=round(float(np.mean(owner_evidence)/255),6),
        participant_delta=round(float(np.mean(participant_evidence)/255),6),
        attributed_changed_pixel_ratio=round(changed,6),actor_attributable_pass=delta>=.003 and changed>=.012)
    if not result['actor_attributable_pass']:result['attribution_failure']='INTENDED_COMPOSITION_NOT_MATERIALLY_ENCODED'
    return result
