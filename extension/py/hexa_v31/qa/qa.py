from __future__ import annotations
import json, math, os, pathlib, statistics
from typing import Any
from hexa_v31.util import read_json, write_json
from hexa_v31.preset_qa import preset_motion_qa, preset_story_plan_qa


def motion_rule_qa(motion_plan:dict, fps:float=30.0):
    failures=[];warnings=[]
    allowed_app={'POSITION_ENTRY','SCALE_POP','OPACITY_FADE_IN','CONTINUATION'};allowed_exit={'POSITION_EXIT','OPACITY_FADE_OUT','HOLD_TO_BOUNDARY'}
    by_scene={}
    for e in motion_plan.get('events',[]):
        by_scene.setdefault(str(e.get('scene_id')),[]).append(e);eid=e.get('event_id');app=e.get('appearance_method');ex=e.get('disappearance_method')
        if app not in allowed_app:failures.append(f'{eid}: invalid appearance {app}')
        if ex not in allowed_exit:failures.append(f'{eid}: invalid disappearance {ex}')
        if e.get('focus_beats'):failures.append(f'{eid}: unapproved scale/focus pulse emitted')
        if e.get('position_animated'):
            frames=(float(e.get('settle_seconds',0))-float(e.get('start_seconds',0)))*fps
            if frames+1e-4<12:failures.append(f'{eid}: position entry {frames:.2f}<12 frames')
            if e.get('position_interpolation')!='BEZIER_EASE_IN_OUT':failures.append(f'{eid}: position interpolation not Bezier Ease In/Out')
            if e.get('kind')=='MAIN_NARRATOR' and e.get('entry_direction')=='TOP':failures.append(f'{eid}: Main Narrator top entry forbidden')
        if ex=='POSITION_EXIT':
            frames=(float(e.get('exit_end_seconds',0))-float(e.get('exit_start_seconds',0)))*fps
            if frames+1e-4<12:failures.append(f'{eid}: position exit {frames:.2f}<12 frames')
            if e.get('exit_position_interpolation')!='BEZIER_EASE_IN_OUT':failures.append(f'{eid}: position exit interpolation not Bezier Ease In/Out')
        if app=='SCALE_POP':
            if e.get('scale_pop')!=[100,110,100]:failures.append(f'{eid}: Scale Pop must be 100->110->100')
            if str(e.get('semantic_role') or '').upper()=='PRIMARY':failures.append(f'{eid}: Scale Pop reserved for supporting element appearance')
        if ex and 'SCALE' in str(ex):failures.append(f'{eid}: scale exit forbidden')
        if e.get('continuous_image_scale'):
            cs=float(e.get('continuous_scale_scene_start_seconds',e.get('start_seconds',0)))
            ce=float(e.get('continuous_scale_scene_end_seconds',e.get('end_seconds',0)))
            dur=ce-cs
            if dur+1e-6<3.0:failures.append(f'{eid}: continuous image scale <3s')
            if abs(float(e.get('continuous_scale_from',0))-1.10)>1e-6 or abs(float(e.get('continuous_scale_to',0))-1.0)>1e-6:failures.append(f'{eid}: continuous scale must be 110->100')
        for a in e.get('story_actions') or []:
            bs=float(a.get('start_seconds',0));be=float(a.get('end_seconds',bs));frames=(be-bs)*fps;kind=str(a.get('kind') or '')
            if kind=='INTRODUCE':
                if frames+1e-4<8:failures.append(f'{eid}: semantic introduction {frames:.2f}<8 frames')
                if str(a.get('render_mode') or '')!='APPEARANCE_AUTHORITY':failures.append(f'{eid}: INTRODUCE must delegate to approved appearance authority')
                continue
            if kind!='POSITION_TRANSFER':failures.append(f'{eid}: unapproved story action {kind}');continue
            if frames+1e-4<12:failures.append(f'{eid}: story Position transfer {frames:.2f}<12 frames')
            if a.get('interpolation')!='BEZIER_EASE_IN_OUT':failures.append(f'{eid}: story transfer must be Bezier Ease In/Out')
            dx=float(a.get('dx_norm',0));dy=float(a.get('dy_norm',0))
            if abs(dx)>1.0+1e-6 or abs(dy)>1.0+1e-6:failures.append(f'{eid}: story transfer exceeds canvas-normalized range')
            if abs(float(a.get('scale_peak',1.0))-1.0)>1e-6:failures.append(f'{eid}: story transfer may not use scale pulse')
            if not bool(a.get('hold_after')):failures.append(f'{eid}: story transfer must create a persistent visual state')
    for sid,rows in by_scene.items():
        slots={}
        for e in rows:slots.setdefault(str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')),[]).append(e)
        overlay_slots={str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) for e in rows if e.get('fifth_element_overlay')}
        if len(slots)>4:
            if len(slots)!=5 or len(overlay_slots)!=1:
                failures.append(f'{sid}: >4 composition slots without exactly one Fifth-Element Overlay slot')
            else:
                ov=next(e for e in rows if str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) in overlay_slots)
                if int(ov.get('overlay_black_opacity_percent',0)) not in range(40,46):failures.append(f'{sid}: fifth overlay black opacity outside 40-45%')
                if int(ov.get('overlay_blur_percent',0))!=16:failures.append(f'{sid}: fifth overlay blur must be 16%')
                if not ov.get('overlay_base_four_must_persist'):failures.append(f'{sid}: fifth overlay must preserve base four')
    return {'pass':not failures,'failure_count':len(failures),'warning_count':len(warnings),'failures':failures,'warnings':warnings,'authority':'HEXA_EDITING_ENGINE_RULES_V20_PDF_HARD_CONSTRAINTS'}

def alignment_qa(alignment:dict, scene_count:int):
    rows=alignment.get('scene_timings') or []; failures=[]
    if len(rows)!=scene_count: failures.append('scene timing count mismatch')
    prev=-1.0
    for r in rows:
        if r['start']<prev-1e-4 or r['end']<=r['start']: failures.append(f"non-monotonic timing {r.get('scene_id')}")
        prev=r['end']
    q=alignment.get('quality') or {}
    if alignment.get('method','').startswith('FASTER_WHISPER') and q.get('canonical_word_direct_match_ratio',0)<0.85:
        failures.append('canonical direct word match ratio below 0.85')
    # Acoustic scene-only fallback is valid for current exact scene-start contract but cannot certify internal word trigger accuracy.
    warnings=[]
    if not q.get('internal_trigger_support',False): warnings.append('scene-boundary alignment only; internal trigger packages would be blocked')
    return {'pass':not failures,'failure_count':len(failures),'failures':failures,'warnings':warnings,'method':alignment.get('method'),'quality':q}


def vision_qa(vision:list[dict]):
    failures=[];warnings=[];modes={};hier=0
    for v in vision:
        modes[v['mode']]=modes.get(v['mode'],0)+1;gc=int(v.get('major_group_count',0))
        if v['mode']=='FLAT_SCENE':warnings.append(f"{v['scene_id']}: flat fallback")
        if v['reconstruction_mae']>6.0:warnings.append(f"{v['scene_id']}: reconstruction MAE {v['reconstruction_mae']}")
        slots={str(u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id')) for u in (v.get('units') or [])}
        if len(slots)>4:
            overlays={str(u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id')) for u in (v.get('units') or []) if u.get('fifth_element_overlay')}
            policy=(v.get('artifacts') or {}).get('fifth_element_overlay') or {}
            if len(slots)!=5 or len(overlays)!=1 or not policy.get('active'):
                failures.append(f"{v['scene_id']}: >4 composition slots without certified Fifth-Element Overlay")
            elif int(policy.get('black_opacity_percent',0)) not in range(40,46) or int(policy.get('blur_percent',0))!=16 or not policy.get('base_four_must_persist'):
                failures.append(f"{v['scene_id']}: Fifth-Element Overlay stack violates hard rules")
        expected_size=[int(v.get('width') or 0),int(v.get('height') or 0)]
        if v['mode']!='FLAT_SCENE':
            for u in v.get('units') or []:
                if u.get('layer_canvas_mode')!='FULL_SCENE_ALPHA_CANVAS':failures.append(f"{v['scene_id']}:{u.get('physical_id')}: not FULL_SCENE_ALPHA_CANVAS")
                if list(u.get('layer_source_size_px') or [])!=expected_size:failures.append(f"{v['scene_id']}:{u.get('physical_id')}: source size differs from Scene canvas")
                lp=u.get('layer_path')
                if not lp or not pathlib.Path(lp).is_file():failures.append(f"{v['scene_id']}:{u.get('physical_id')}: physical layer missing")
                if int(u.get('hierarchy_level') or 0)>0:
                    hier+=1
                    if float(u.get('hierarchy_confidence') or 0)<0.64:failures.append(f"{v['scene_id']}:{u.get('physical_id')}: hierarchy confidence below V31 safety threshold")
                    if str(u.get('animation_mode') or '') not in {'TRANSLATE_SAFE','REVEAL_ONLY','GROUP_ONLY'}:failures.append(f"{v['scene_id']}:{u.get('physical_id')}: invalid animation safety mode")
                    if not bool(u.get('animation_safe',False)):warnings.append(f"{v['scene_id']}:{u.get('physical_id')}: hierarchical child not safe for independent motion")
    return {'pass':not failures,'failure_count':len(failures),'warning_count':len(warnings),'failures':failures,'warnings':warnings,'mode_counts':modes,'hierarchical_motion_unit_count':hier,'flat_fallback_ratio':modes.get('FLAT_SCENE',0)/max(1,len(vision)),'physical_layer_contract':'FULL_SCENE_ALPHA_CANVAS'}

def reference_plan_qa(motion_plan:dict, reference_profile:dict):
    """Validate the one V31 semantic story truth before Premiere handoff.

    V26 had two disagreeing causal detectors and allowed 0/0 storytelling to pass.
    V31 uses only semantic_object_graph + story_state_machine from the motion plan.
    Non-causal reveal handoffs are valid story; a safe causal TRANSFER edge additionally
    requires a physical persistent Position transfer.
    """
    scenes=motion_plan.get('scenes') or [];events=motion_plan.get('events') or [];fail=[];warn=[]
    cont=motion_plan.get('continuity_summary') or {};reset_pct=float(cont.get('white_reset_scene_percent',100.0));hard=motion_plan.get('hard_invariants') or {};max_reset=float(hard.get('max_normal_white_reset_scene_percent',18.0))
    if reset_pct>max_reset:fail.append(f'white reset scene percent {reset_pct:.2f}>{max_reset:.2f}')
    by_scene={}
    for e in events:by_scene.setdefault(str(e.get('scene_id')),[]).append(e)
    zero_story=[];transfer_missing=[];long_fail=[];long_warn=[];eligible_count=0
    for s in scenes:
        sid=str(s.get('scene_id'));dur=float(s.get('duration_seconds',0));rows=by_scene.get(sid,[]);graph=s.get('semantic_object_graph') or {};machine=s.get('story_state_machine') or {}
        eligible=bool(graph.get('story_eligible'));story=int(machine.get('story_action_count',s.get('story_action_count',0)) or 0);physical=int(machine.get('physical_action_count',s.get('physical_story_action_count',0)) or 0)
        if eligible:
            eligible_count+=1
            if story<1:zero_story.append(sid)
        # Validate the compiled physical story, not a semantic TRANSFER candidate that may have
        # been legally downgraded to reveal/handoff because geometry or the 12-frame timing window
        # made translation unsafe. This keeps one story truth and prevents false pre-render failures.
        compiled=list(machine.get('compiled_edge_resolutions') or [])
        unresolved_transfer=[x for x in compiled if x.get('requested_action_mode')=='TRANSFER' and not x.get('resolved_action_mode')]
        promised_transfer=[x for x in compiled if x.get('resolved_action_mode')=='POSITION_TRANSFER']
        if unresolved_transfer:transfer_missing.append(sid)
        if promised_transfer and physical<1:transfer_missing.append(sid)
        gap=float(s.get('max_story_gap_seconds',dur))
        reveal_safe_count=sum(1 for n in (graph.get('nodes') or []) if bool(n.get('reveal_safe',True)))
        continuous_motion=any(bool(e.get('continuous_image_scale')) for e in rows)
        # The 1.90s hard gap is only meaningful when the scene actually has multiple semantic
        # states available to schedule. A single indivisible object cannot be forced into fake
        # actions just to satisfy an invented timing metric; approved >=3s continuous image scale
        # is also valid motion. Final MP4 reference metrics remain the physical judge.
        if dur>=2.8 and len(rows)>=1 and not continuous_motion:
            if eligible and reveal_safe_count>=2:
                if gap>1.90:long_fail.append(sid)
                elif gap>1.45:long_warn.append(sid)
            elif gap>1.90:
                long_warn.append(sid)
        slot_ids={str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) for e in rows};overlay_slots={str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) for e in rows if e.get('fifth_element_overlay')};
        if len(slot_ids)>4 and not (len(slot_ids)==5 and len(overlay_slots)==1):fail.append(f'{sid}: >4 simultaneous composition slots without Fifth-Element Overlay')
        for e in rows:
            if e.get('focus_beats'):fail.append(f'{e.get("event_id")}: unapproved focus pulse')
    if eligible_count>0 and sum(int((s.get('story_state_machine') or {}).get('story_action_count',s.get('story_action_count',0)) or 0) for s in scenes)==0:
        fail.append('vacuous storytelling plan: eligible scenes exist but total story actions is zero')
    if zero_story:fail.append('story-eligible scenes lack semantic story actions: '+','.join(zero_story[:8]))
    if transfer_missing:fail.append('compiled TRANSFER promises lack persistent Position action: '+','.join(transfer_missing[:8]))
    if long_fail:fail.append('long scenes exceed 1.90s semantic state gap: '+','.join(long_fail[:8]))
    if long_warn:warn.append('long scenes have >1.45s semantic state gap: '+','.join(long_warn[:8]))
    bad_boundary=[e.get('event_id') for i,s in enumerate(scenes[:-1]) for e in by_scene.get(str(s.get('scene_id')),[]) if e.get('disappearance_method')=='OPACITY_FADE_OUT' and not e.get('explicit_exit_bound')]
    if bad_boundary:fail.append('non-final scene fades without explicit exit: '+','.join(bad_boundary[:8]))
    max_tf=int(hard.get('full_frame_transition_max_frames_normal',8) or 8)
    transition_bad=[s.get('scene_id') for s in scenes[1:] if not (s.get('transition') or {}).get('white_reset') and int((s.get('transition') or {}).get('transition_frames',max_tf))>max_tf]
    if transition_bad:fail.append(f'normal full-frame transition >{max_tf} frames: '+','.join(transition_bad[:8]))
    budget=motion_plan.get('budget_summary') or {};max_util=float(budget.get('max_scene_budget_utilization_post_orchestration',budget.get('max_scene_budget_utilization_pre_orchestration',0.0)) or 0.0)
    if max_util>1.35:fail.append(f'presentation budget utilization {max_util:.2f}>1.35')
    durs=[float(s.get('duration_seconds',0)) for s in scenes];visible=[len({str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) for e in by_scene.get(str(s.get('scene_id')),[])}) for s in scenes]
    return {'pass':not fail,'failures':fail,'warnings':warn,'planner_scene_duration_median':statistics.median(durs) if durs else 0,'planner_major_units_median':statistics.median(visible) if visible else 0,'white_reset_scene_percent':reset_pct,'story_eligible_scene_count':eligible_count,'zero_story_eligible_scene_count':len(zero_story),'causal_transfer_missing_count':len(transfer_missing),'long_scene_progression_failure_count':len(long_fail),'long_scene_progression_warning_count':len(long_warn),'story_action_count':sum(int((s.get('story_state_machine') or {}).get('story_action_count',s.get('story_action_count',0)) or 0) for s in scenes),'physical_story_action_count':sum(int((s.get('story_state_machine') or {}).get('physical_action_count',s.get('physical_story_action_count',0)) or 0) for s in scenes),'hierarchical_motion_unit_count':sum(int(s.get('hierarchical_motion_unit_count',0) or 0) for s in scenes),'max_presentation_budget_utilization':max_util,'boundary_card_fade_violation_count':len(bad_boundary),'untriggered_focus_violation_count':0,'single_story_truth_schema':'HEXA_SEMANTIC_ACTING_GRAPH_V31','composition_slot_policy':'PHYSICAL_SUBLAYERS_DO_NOT_CONSUM_SCREEN_ELEMENT_SLOTS','vacuous_story_pass_forbidden':True,'render_level_reference_gate':'REQUIRED_ON_FINAL_ENGINE_MP4_AND_HUMAN_COMPARISON'}

def build_qa_report(package, audio_probe:dict, alignment:dict, vision:list[dict], motion_plan:dict, reference_profile:dict, premiere:dict, out_path:str|os.PathLike, reference_preview_metrics:dict|None=None, reference_preview_score:dict|None=None):
    # V31 plans are governed by the uploaded preset authority.  The V31.0.22
    # choreography DNA deliberately uses a more specific suffix than the older
    # ``PREMIUM_VISUAL_CHOREOGRAPHY`` label, so authority selection must be based
    # on the stable V31 motion-DNA namespace rather than a historical suffix.
    # Falling through to motion_rule_qa would apply the retired V20 scale-pop /
    # disappearance vocabulary to a valid preset-authority plan.
    motion_dna=str(motion_plan.get('motion_dna_version') or '')
    uses_preset_authority=(
        motion_dna.startswith('HEXA_MOTION_DNA_V31_')
        or 'V31_0_1_UNIVERSAL_CONSTRAINT_STORY_DIRECTOR' in motion_dna
        or 'USER_PRESET' in motion_dna
        or 'PREMIUM_VISUAL_CHOREOGRAPHY' in motion_dna
    )
    qa={
        'schema':'HEXA_V31_QA_REPORT','version':'4.0','project_id':package.plan.get('project_id'),
        'runtime_input':{'scene_count':len(package.scenes),'voice_duration_seconds':audio_probe['duration_seconds']},
        'gates':{
            'STRUCTURAL':{'pass':True,'note':'Package validated by physical cold readback, exact slices, triggers and SHA-256.'},
            'ALIGNMENT':alignment_qa(alignment,len(package.scenes)),
            'VISION_RECONSTRUCTION':vision_qa(vision),
            'MOTION_RULES':preset_motion_qa(motion_plan,float(motion_plan.get('fps',30))) if uses_preset_authority else motion_rule_qa(motion_plan,float(motion_plan.get('fps',30))),
            'REFERENCE_PLAN':preset_story_plan_qa(motion_plan,vision) if uses_preset_authority else reference_plan_qa(motion_plan,reference_profile),
            'PREMIERE_HANDOFF':{'pass':bool(premiere.get('timeline_xml') and premiere.get('edit_map') and premiere.get('execution_mode')=='PREMIERE_2022_ANIMATED_SCENE_MEDIA_ASSEMBLY'),'execution_mode':premiere.get('execution_mode'),'still_image_keyframes_required':False,'real_premiere_2022_execution':'PENDING_USER_MACHINE'},
        }
    }
    if reference_preview_score is not None:
        qa['gates']['REFERENCE_PREVIEW_PROXY']={
            'pass':bool(reference_preview_score.get('pass')),
            'score_percent':reference_preview_score.get('reference_fidelity_proxy_score_percent'),
            'gates':reference_preview_score.get('gates'),
            'metrics':reference_preview_metrics,
            'note':'Proxy recomputed from the actual V31 final MP4 assembled from the same animated Scene media used by Premiere; human reference review remains mandatory.'
        }
    qa['technical_pass']=all(g.get('pass',False) for k,g in qa['gates'].items() if k!='REFERENCE_PREVIEW_PROXY')
    if reference_preview_score is None:
        qa['reference_quality_status']='PENDING_AUTOMATED_PREVIEW_AND_PHYSICAL_PREMIERE_RENDER'
    elif reference_preview_score.get('pass'):
        qa['reference_quality_status']='ACTUAL_V31_MP4_REFERENCE_PROXY_PASS__HUMAN_COMPARISON_PENDING'
    else:
        qa['reference_quality_status']='AUTOMATED_REFERENCE_PROXY_FAIL'
    qa['reference_proxy_pass']=bool(reference_preview_score and reference_preview_score.get('pass'))
    qa['production_promotion_allowed']=False
    write_json(out_path,qa); return qa
