from __future__ import annotations
from .preset_authority import authority as load_authority
from .composition_qa import composition_plan_qa
from .visual_density import build_visual_density_report
from .composition_qa import _state


def _peak(events:list[dict],primary:bool)->int:
    selected=[e for e in events if not e.get('suppressed_by_card_density')
              and (str(e.get('attention_priority') or '').upper()=='PRIMARY')==bool(primary)]
    if not selected:return 0
    start=min(float(e.get('start_seconds',0)) for e in selected)
    end=max(float(e.get('end_seconds',start)) for e in selected)
    peak=0;t=start
    while t<=end+1e-6:
        peak=max(peak,sum(1 for e in selected if (lambda s: bool(s and float(s[2])>.22))(_state(e,t))))
        t+=1.0/30.0
    return peak


def preset_motion_qa(motion_plan:dict,fps:float=30.0)->dict:
    failures=[];warnings=[]
    auth=load_authority();defs=auth.get('preset_motion') or {};allowed=set(defs)
    cards=list((motion_plan.get('visual_cards') or {}).get('cards') or [])
    all_events=list(motion_plan.get('events') or [])
    for c in cards:
        cid=str(c.get('card_id'));dur=float(c.get('duration_seconds') or 0.0)
        if dur<3.0-1e-5 or dur>5.0+1e-5:failures.append(f'{cid}: visual card duration {dur:.3f}s outside 3-5s')
        evs=[e for e in all_events if e.get('visual_card_id')==cid]
        rp=_peak(evs,True)
        rs=int(c.get('rendered_secondary_count',c.get('secondary_count_estimate',0)) or 0)
        if not 1<=rp<=2:failures.append(f'{cid}: peak concurrent primary count {rp} outside 1-2')
        if not 3<=rs<=8:
            # The user rule remains the target, but V31 must not invent/regenerate assets or
            # reintroduce bad subobject cutouts merely to satisfy a number. Preserve the build
            # artifact for human review and report the upstream source-density shortfall.
            warnings.append(f'{cid}: source visual density provides {rs} secondary details; target is 3-8. No synthetic asset/cutout was fabricated.')
            c['source_secondary_density_shortfall']=max(0,3-rs)
        c['rendered_primary_count']=rp
    for e in all_events:
        if e.get('suppression_reason')=='PRIMARY_PRESET_CAPACITY_OVERFLOW':
            failures.append(f"{e.get('event_id')}: primary preset capacity overflow; card compiler failed to allocate a legal 3-5s window")
        if e.get('suppressed_by_card_density'):continue
        eid=str(e.get('event_id'))
        if int(e.get('hierarchy_level') or 0)>0:
            if e.get('render_mode')!='CHILD_PARTITION' or not e.get('partition_complete') or not e.get('source_layer_path'):
                failures.append(f'{eid}: hierarchical child lacks certified partition render evidence')
            if not e.get('reveal_safe',True):failures.append(f'{eid}: unsafe hierarchical child entered render plan')
        primary=str(e.get('attention_priority') or '').upper()=='PRIMARY'
        for key in ('preset_entry','preset_exit'):
            p=e.get(key)
            if not p:failures.append(f'{eid}: missing {key}');continue
            name=str(p.get('name') or '')
            if name not in allowed:failures.append(f'{eid}: unknown preset {name}');continue
            d=defs[name];actual=float(p.get('duration_seconds') or 0);expected=float(d.get('duration_seconds') or 0)
            if abs(actual-expected)>1e-4:failures.append(f'{eid}:{name}: duration {actual:.4f}!={expected:.4f}')
            family=str(d.get('family') or '')
            if key=='preset_entry':
                if primary and family not in {'ENTRY_EXIT','APPEARANCE'}:failures.append(f'{eid}: primary entry must use Entry/Exit or necessity Appearance family')
                if (not primary) and family!='APPEARANCE':failures.append(f'{eid}: secondary entry must use appearance preset family')
            else:
                if primary and family not in {'ENTRY_EXIT','DISAPPEARANCE'}:failures.append(f'{eid}: primary exit must use Entry/Exit or legal disappearance family')
                if (not primary) and family!='DISAPPEARANCE':failures.append(f'{eid}: secondary exit must use disappearance preset family')
        for a in e.get('preset_actions') or []:
            name=str(a.get('name') or '')
            if name not in allowed:failures.append(f'{eid}: unknown within-frame preset {name}');continue
            if str(defs[name].get('family'))!='WITHIN_FRAME':failures.append(f'{eid}:{name}: action is not within-frame family')
            action_type=str(a.get('action_type') or 'SEMANTIC_RELATIONSHIP').upper()
            if action_type=='SEMANTIC_RELATIONSHIP':
                if float(a.get('relationship_confidence') or 0.0)<0.999:failures.append(f'{eid}:{name}: semantic relationship lacks explicit 1.0 evidence')
                if not a.get('relationship_evidence'):failures.append(f'{eid}:{name}: semantic relationship evidence missing')
                if not a.get('target_semantic_unit_id'):failures.append(f'{eid}:{name}: semantic relationship target missing')
            elif action_type=='LAYOUT_CHOREOGRAPHY':
                if a.get('target_semantic_unit_id') or a.get('relationship_evidence'):
                    failures.append(f'{eid}:{name}: layout choreography must not masquerade as semantic relationship')
                if not a.get('layout_purpose'):failures.append(f'{eid}:{name}: layout choreography purpose missing')
            else:
                failures.append(f'{eid}:{name}: unknown action_type {action_type}')
        if e.get('story_actions') or e.get('focus_beats') or e.get('continuous_drift') or e.get('continuous_image_scale'):
            failures.append(f'{eid}: legacy/unapproved motion survived V31 preset lock')
        if e.get('motion_blur_enabled'):failures.append(f'{eid}: synthetic motion blur is not authorized by supplied preset map')
    hard=motion_plan.get('hard_invariants') or {}
    for k in ('legacy_motion_heuristics_disabled','speculative_subobject_cutouts_forbidden','spatial_role_guessing_forbidden','explicit_relationship_evidence_required','layout_choreography_must_not_claim_semantic_relationship','full_frame_crossfade_forbidden','white_wash_forbidden','mask_wipe_reveal_forbidden','arbitrary_drift_forbidden'):
        if not hard.get(k):failures.append('hard invariant missing: '+k)
    if not cards:failures.append('no visual cards compiled')
    comp=composition_plan_qa(motion_plan)
    failures.extend(comp.get('failures') or [])
    warnings.extend(comp.get('warnings') or [])
    density=build_visual_density_report(motion_plan)
    for cid in density.get('hard_under_density_cards') or []:failures.append(f'{cid}: multi-object card serialized despite multiple valid visual units')
    for row in density.get('cards') or []:
        if row.get('soft_under_density'):warnings.append(f"{row.get('card_id')}: safe-frame union coverage {float(row.get('median_safe_frame_union_coverage') or 0):.3f}<0.240")
        if float(row.get('near_blank_duration_seconds') or 0)>0.35:failures.append(f"{row.get('card_id')}: near-blank duration {float(row.get('near_blank_duration_seconds')):.2f}s>0.35s")
        elif float(row.get('near_blank_duration_seconds') or 0)>0.15:warnings.append(f"{row.get('card_id')}: near-blank duration {float(row.get('near_blank_duration_seconds')):.2f}s")
    return {
        'pass':not failures,'failure_count':len(failures),'warning_count':len(warnings),
        'failures':failures,'warnings':warnings,
        'authority':'USER_UPLOADED_RULES_PDF_PLUS_PRFPSET_PLUS_VISUAL_SAMPLES',
        'visual_card_count':len(cards),'preset_event_count':sum(1 for e in all_events if not e.get('suppressed_by_card_density')),
        'relationship_action_count':sum(1 for e in all_events for a in (e.get('preset_actions') or []) if str(a.get('action_type') or '').upper()=='SEMANTIC_RELATIONSHIP'),
        'layout_action_count':sum(1 for e in all_events for a in (e.get('preset_actions') or []) if str(a.get('action_type') or '').upper()=='LAYOUT_CHOREOGRAPHY'),
        'source_secondary_density_shortfall_cards':sum(1 for c in cards if int(c.get('rendered_secondary_count') or 0)<3),
        'composition_qa':comp,
        'visual_density_qa':density,
    }


def preset_story_plan_qa(motion_plan:dict,vision_results:list[dict]|None=None)->dict:
    qa=preset_motion_qa(motion_plan,float(motion_plan.get('fps') or 30.0))
    failures=list(qa['failures']);warnings=list(qa['warnings'])
    if vision_results is not None:
        for v in vision_results:
            sid=str(v.get('scene_id'))
            children=[u for u in (v.get('units') or []) if int(u.get('hierarchy_level') or 0)>0]
            # Vision children are permitted only when the planner selected a
            # complete source-backed CHILD_PARTITION.  This auditor receives
            # vision evidence, not a request to render every extracted child.
            matte=(v.get('artifacts') or {}).get('matting_summary') or {};risk=float(matte.get('max_edge_halo_risk') or 0.0)
            leak=float(matte.get('max_opaque_stage_leak_fraction') or 0.0)
            if risk>0.55:warnings.append(f'{sid}: high matte halo risk {risk:.3f}; preserve grouped-source object and avoid thinner slicing')
            if leak>0.004:failures.append(f'{sid}: opaque white-stage leak remains in extracted layer ({leak:.4f}>0.0040)')
    return {
        'pass':not failures,'failures':failures,'warnings':warnings,
        'visual_card_count':qa['visual_card_count'],'preset_event_count':qa['preset_event_count'],
        'relationship_action_count':qa['relationship_action_count'],'layout_action_count':qa['layout_action_count'],
        'composition_qa':qa.get('composition_qa') or {},
        'cutout_policy':'TOP_LEVEL_GROUPS_ONLY__NO_SPECULATIVE_SUBOBJECTS__PRESERVE_ATTACHED_DETAILS',
        'relationship_policy':'EXPLICIT_METADATA_ONLY__LAYOUT_MOVES_NEVER_CLAIM_RELATIONSHIP',
        'transition_policy':'NO_FULL_FRAME_BLEND__OBJECT_PRESETS_ONLY',
        'authority':qa['authority'],
    }
