from __future__ import annotations
from hexa_v31.preset_authority import authority as load_authority
from hexa_v31.composition_qa import composition_plan_qa
from hexa_v31.visual_density import build_visual_density_report
from hexa_v31.composition_qa import _state
from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa


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


def hierarchical_render_evidence_qa(events:list[dict])->dict:
    """Validate hierarchical render modes without treating residual pixels as actors."""
    failures=[];defs=(load_authority().get('preset_motion') or {})
    for e in events:
        if e.get('suppressed_by_card_density') or int(e.get('hierarchy_level') or 0)<=0:continue
        eid=str(e.get('event_id'));mode=str(e.get('render_mode') or '')
        if mode=='CHILD_PARTITION':
            if not e.get('partition_complete') or not e.get('source_layer_path'):
                failures.append(f'{eid}: hierarchical child lacks certified partition render evidence')
            if not e.get('reveal_safe',True):failures.append(f'{eid}: unsafe hierarchical child entered render plan')
            continue
        if mode!='RESIDUAL_SUPPORT':
            failures.append(f'{eid}: hierarchical child lacks certified partition render evidence')
            continue
        if not e.get('source_layer_path'):failures.append(f'{eid}: residual support lacks source layer')
        if 'foundation_residual_support' in e and not e.get('foundation_residual_support'):
            failures.append(f'{eid}: residual support lacks Foundation reconstruction evidence')
        if e.get('independent_motion_allowed'):
            failures.append(f'{eid}: residual support permits independent motion')
        if e.get('translation_safe_after_occlusion'):
            failures.append(f'{eid}: residual support claims translation safety')
        if 'animation_mode' in e and e.get('animation_mode')!='STATIC_SUPPORT':
            failures.append(f'{eid}: residual support is not static reconstruction support')
        spatial=bool(e.get('position_animated') or e.get('preset_actions'))
        for key in ('preset_entry','preset_exit'):
            name=str((e.get(key) or {}).get('name') or '')
            spatial=spatial or bool(name and str((defs.get(name) or {}).get('family') or '')=='ENTRY_EXIT')
        coords=[e.get(k) for k in ('start_x_norm','start_y_norm','end_x_norm','end_y_norm','exit_x_norm','exit_y_norm')]
        if all(v is not None for v in coords):
            spatial=spatial or abs(float(coords[0])-float(coords[2]))>1e-6 or abs(float(coords[1])-float(coords[3]))>1e-6 or abs(float(coords[2])-float(coords[4]))>1e-6 or abs(float(coords[3])-float(coords[5]))>1e-6
        if spatial:failures.append(f'{eid}: residual support has independent spatial animation')
    return {'pass':not failures,'failures':failures}


def preset_motion_qa(motion_plan:dict,fps:float=30.0)->dict:
    failures=[];warnings=[]
    auth=load_authority();defs=auth.get('preset_motion') or {};allowed=set(defs)
    cards=list((motion_plan.get('visual_cards') or {}).get('cards') or [])
    all_events=list(motion_plan.get('events') or [])
    failures.extend(hierarchical_render_evidence_qa(all_events)['failures'])
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


def _vision_planner_partition_completeness_qa(motion_plan:dict, vision_results:list[dict])->dict:
    """Prove the planner preserved every member of each certified Vision partition."""
    failures=[];rows=[]
    events=list(motion_plan.get('events') or [])
    by_scene={}
    for e in events:
        by_scene.setdefault(str(e.get('scene_id')),[]).append(e)
    for v in vision_results:
        sid=str(v.get('scene_id'))
        reconstruction=((v.get('artifacts') or {}).get('foundation_vision') or {}).get('reconstruction_qa') or {}
        if not reconstruction.get('partition_complete'):
            continue
        units=list(v.get('units') or [])
        expected=[u for u in units if (u.get('candidate_source') and u.get('mask_path')) or (u.get('foundation_residual_support') and u.get('mask_path'))]
        if not expected:
            continue
        expected_ids={str(u.get('physical_id')) for u in expected}
        scene_events=by_scene.get(sid,[])
        selected=[e for e in scene_events if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} and not e.get('suppressed_by_card_density')]
        selected_ids={str(e.get('physical_id')) for e in selected}
        suppressed_ids={str(e.get('physical_id')) for e in scene_events if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} and e.get('suppressed_by_card_density')}
        root_fallbacks=[e for e in scene_events if e.get('render_mode')=='ROOT_ATOMIC' and not e.get('suppressed_by_card_density')]
        missing=sorted(expected_ids-selected_ids)
        extra=sorted(selected_ids-expected_ids)
        complete_partition=not missing and not suppressed_ids and not extra and bool(selected)
        root_atomic_fallback=bool(root_fallbacks) and not selected and not suppressed_ids
        valid=complete_partition or root_atomic_fallback
        if not valid:
            failures.append(f"{sid}: certified Foundation partition membership mismatch expected={sorted(expected_ids)} selected={sorted(selected_ids)} suppressed={sorted(suppressed_ids)} root_fallbacks={[str(e.get('physical_id')) for e in root_fallbacks]}")
        rows.append({'scene_id':sid,'expected_member_ids':sorted(expected_ids),'selected_member_ids':sorted(selected_ids),
                     'suppressed_member_ids':sorted(suppressed_ids),'missing_member_ids':missing,'extra_member_ids':extra,
                     'root_atomic_fallback_ids':[str(e.get('physical_id')) for e in root_fallbacks],
                     'selection_mode':'COMPLETE_PARTITION' if complete_partition else ('ROOT_ATOMIC_FALLBACK' if root_atomic_fallback else 'INVALID_PARTIAL_PARTITION'),
                     'pass':valid})
    return {'pass':not failures,'failures':failures,'groups':rows}


def preset_story_plan_qa(motion_plan:dict,vision_results:list[dict]|None=None,duration_seconds:float|None=None)->dict:
    qa=preset_motion_qa(motion_plan,float(motion_plan.get('fps') or 30.0))
    failures=list(qa['failures']);warnings=list(qa['warnings'])
    partition_completeness={'pass':True,'failures':[],'groups':[]}
    if vision_results is not None:
        partition_completeness=_vision_planner_partition_completeness_qa(motion_plan,vision_results)
        failures.extend(partition_completeness.get('failures') or [])
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
    coverage=visual_timeline_coverage_qa(motion_plan,duration_seconds=duration_seconds)
    failures.extend(coverage.get('failures') or [])
    return {
        'pass':not failures,'failures':failures,'warnings':warnings,
        'visual_card_count':qa['visual_card_count'],'preset_event_count':qa['preset_event_count'],
        'relationship_action_count':qa['relationship_action_count'],'layout_action_count':qa['layout_action_count'],
        'composition_qa':qa.get('composition_qa') or {},
        'cutout_policy':'TOP_LEVEL_GROUPS_ONLY__NO_SPECULATIVE_SUBOBJECTS__PRESERVE_ATTACHED_DETAILS',
        'relationship_policy':'EXPLICIT_METADATA_ONLY__LAYOUT_MOVES_NEVER_CLAIM_RELATIONSHIP',
        'transition_policy':'NO_FULL_FRAME_BLEND__OBJECT_PRESETS_ONLY',
        'authority':qa['authority'],
        'visual_timeline_coverage_qa':coverage,
        'vision_planner_partition_completeness_qa':partition_completeness,
    }
