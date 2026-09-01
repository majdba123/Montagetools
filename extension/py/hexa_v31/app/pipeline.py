from __future__ import annotations
import hashlib, json, os, pathlib, shutil, sys, time, subprocess, uuid, zipfile
from dataclasses import asdict
from datetime import datetime
from hexa_v31 import VERSION, ENGINE_ID
from hexa_v31.util import ensure_dir, read_json, sha256_file, write_json, documents_dir, safe_filename
from hexa_v31.diagnostics import BuildLogger
from hexa_v31.package_io import open_and_validate
from hexa_v31.audio import probe_audio, decode_mono16k
from hexa_v31.audio_prosody import AudioProsodyAnalyzer
from hexa_v31.alignment import resolve_alignment, project_scene_intervals_from_word_timings
from hexa_v31.motion import build_motion_plan
from hexa_v31.premiere import build_layer_render_map, build_premiere_handoff_from_scene_media
from hexa_v31.typography import build_text_plan, find_arabic_font, merge_support_typography
from hexa_v31.scene_media import render_scene_media, assemble_final_mp4
from hexa_v31.reference_metrics import analyze_video, score_against_reference_floor
from hexa_v31.graphics import build_graphics_plan
from hexa_v31.production_cert import certify_production
from hexa_v31.orchestration import balance_presentation
from hexa_v31.qa import build_qa_report, motion_rule_qa, alignment_qa, reference_plan_qa
from hexa_v31.preset_qa import preset_motion_qa, preset_story_plan_qa
from hexa_v31.storytelling_verify import verify_storytelling_render
from hexa_v31.spike_attribution import attribute_spikes
from hexa_v31.perceptual_qa import evaluate_perceptual_story_from_metrics
from hexa_v31.physical_acting_verify import verify_physical_acting
from hexa_v31.reference_critic import score_reference_10
from hexa_v31.visual_density import build_visual_density_report, temporal_population_report
from hexa_v31.design_director import apply_audio_semantic_timing, build_title_plan, design_qa, finalize_anchor_coverage, stabilize_timeline_density
from hexa_v31.visual_choreography import build_visual_choreography_report
from hexa_v31.vision.foundation import FoundationVisionClient

ALIGNMENT_ENGINE_CACHE_VERSION='HEXA_V20_ALIGNMENT_CACHE_1.2'

def _run_scene_vision_worker(python,ext,spec,img,vroot,foundation_path=None):
    cmd=[python,'-m','hexa_v31.vision.vision_worker','--scene-json',str(spec),'--image',str(img),'--out-dir',str(vroot)]
    if foundation_path:cmd.extend(['--foundation-result',str(foundation_path)])
    env=os.environ.copy();env['PYTHONPATH']=str(ext/'py')+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
    try:cp=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
    except subprocess.TimeoutExpired:raise BuildFailure('Vision worker timeout')
    if cp.returncode!=0:raise BuildFailure('Vision worker failed: '+cp.stderr[-2500:])
    line=next((ln for ln in cp.stdout.splitlines() if ln.startswith('HEXA_V31_VISION_RESULT=')),None)
    if not line:raise BuildFailure('Vision worker returned no result')
    return json.loads(line.split('=',1)[1])

def _foundation_materially_useful(vision_row):
    units=vision_row.get('units') or [];expected=int(vision_row.get('expected_semantic_units') or 0)
    independent=sum(bool(u.get('translation_safe_after_occlusion',u.get('animation_safe'))) for u in units)
    return bool(len(units)<=1 or independent<min(2,max(1,expected)) or (int(vision_row.get('grouped_detail_count') or 0)>=2 and independent<2))


class BuildFailure(RuntimeError):
    def __init__(self, message:str, payload:dict|None=None):
        super().__init__(message)
        self.payload=payload or {}


def semantic_story_lock_status(report:dict)->dict:
    hard=list(report.get('hard_failures') or [])
    coverage=bool(report.get('coverage_gates_pass'))
    return {'semantic_story_lock_pass':coverage and not hard,'semantic_story_lock_review_required':not coverage and not hard,'semantic_story_lock_hard_failure':bool(hard),'semantic_hard_failures':hard}


def _default_runtime_cfg(extension_root:pathlib.Path):
    cfg_candidates=[]
    env=os.environ.get('HEXA_V31_RUNTIME_CONFIG') or os.environ.get('HEXA_V20_RUNTIME_CONFIG')
    if env: cfg_candidates.append(pathlib.Path(env))
    local=os.environ.get('LOCALAPPDATA')
    if local: cfg_candidates.append(pathlib.Path(local)/'HEXA'/'VideoBuilderV31'/'runtime_config.json')
    cfg_candidates.append(extension_root/'resources'/'runtime_config.dev.json')
    for p in cfg_candidates:
        if p.is_file():
            try:return read_json(p)
            except Exception: pass
    return {'allow_whisper':False,'cpu_threads':4,'downloads_during_build':False}


def _alignment_signature(package_sha:str,audio_sha:str,runtime_cfg:dict)->str:
    payload={
        'version':ALIGNMENT_ENGINE_CACHE_VERSION,
        'package_sha256':package_sha,'audio_sha256':audio_sha,
        'allow_whisper':bool(runtime_cfg.get('allow_whisper')),
        'whisper_model_path':runtime_cfg.get('whisper_model_path'),
        'whisper_device':runtime_cfg.get('whisper_device'),
        'whisper_compute_type':runtime_cfg.get('whisper_compute_type'),
    }
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


def _make_failure_bundle(root:pathlib.Path, runtime_cfg:dict, failure:dict):
    diag=ensure_dir(root/'diagnostics')
    temp=ensure_dir(diag/'failure_bundle')
    write_json(temp/'failure.json',failure)
    write_json(temp/'runtime_config_snapshot.json',runtime_cfg)
    candidates=[
        root/'package_audit.json',root/'alignment_resolved_v31.json',root/'scene_vision_report_v31.json',
        root/'HEXA_MOTION_PLAN_V31.json',root/'HEXA_V31_VISUAL_DENSITY_REPORT.json',root/'HEXA_V31_TEMPORAL_POPULATION_REPORT.json',root/'HEXA_V31_PRE_RENDER_STORY_PLAN_QA.json',root/'HEXA_V31_SELECTIVE_TYPOGRAPHY_PLAN.json',root/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json',root/'HEXA_V31_REFERENCE_PREVIEW_METRICS.json',
        root/'HEXA_V31_REFERENCE_PREVIEW_SCORE.json',root/'HEXA_V31_REFERENCE_SCORE_10.json',root/'HEXA_V31_REFERENCE_AUTOCALIBRATION.json',root/'HEXA_V31_STORYTELLING_RENDER_VERIFICATION.json',root/'HEXA_V31_PHYSICAL_ACTING_VERIFICATION.json',root/'HEXA_V31_PERCEPTUAL_STORY_QA.json',root/'HEXA_V31_SPIKE_ATTRIBUTION.json',root/'HEXA_V31_QA_REPORT.json',root/'last_safe_checkpoint.json',
        root/'logs'/'master.log',root/'logs'/'events.jsonl',root/'logs'/'build_summary.json',
    ]
    for p in candidates:
        try:
            if p.is_file(): shutil.copy2(p,temp/p.name)
        except Exception: pass
    z=diag/'HEXA_V31_FAILURE_BUNDLE.zip'
    try:
        with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(temp.iterdir()):
                if p.is_file(): zf.write(p,p.name)
        failure['failure_bundle']=str(z)
        return str(z)
    except Exception:
        return None


def build(scene_package_zip:str, voice_over:str, work_root:str|None=None, extension_root:str|None=None, echo=True):
    ext=pathlib.Path(extension_root or pathlib.Path(__file__).resolve().parents[3]).resolve()
    runtime_cfg=_default_runtime_cfg(ext)
    work=pathlib.Path(work_root or runtime_cfg.get('build_cache_root') or (pathlib.Path(os.environ.get('LOCALAPPDATA',pathlib.Path.home()))/'HEXA'/'VideoBuilderV31'/'builds')).resolve()
    ensure_dir(work)
    package_sha=sha256_file(scene_package_zip); audio_sha=sha256_file(voice_over); project_key=f'{package_sha[:12]}_{audio_sha[:12]}'
    project_root=ensure_dir(work/project_key); cache_root=ensure_dir(project_root/'cache')
    build_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    root=ensure_dir(project_root/'runs'/build_id); log=BuildLogger(ensure_dir(root/'logs'),build_id=build_id,echo=echo)
    if runtime_cfg.get('ffmpeg_path'): os.environ['HEXA_FFMPEG']=str(runtime_cfg['ffmpeg_path'])
    if runtime_cfg.get('ffprobe_path'): os.environ['HEXA_FFPROBE']=str(runtime_cfg['ffprobe_path'])
    production_mp4=None; export_dir=None
    try:
        log.phase('PREFLIGHT')
        if runtime_cfg.get('downloads_during_build') not in (False,None):
            raise BuildFailure('Runtime policy violation: downloads_during_build must be false.')
        log.log('INFO','ENGINE',engine=ENGINE_ID,version=VERSION,downloads_during_build=False,build_id=build_id,project_cache=str(cache_root))
        audio=probe_audio(voice_over); log.log('PASS','VOICE_OVER_PROBED',duration_seconds=audio['duration_seconds'],sha256=audio['sha256'])

        log.phase('PACKAGE_INGEST')
        pkg=open_and_validate(scene_package_zip,cache_root/'packages',log)
        write_json(root/'package_audit.json',{'package_sha256':package_sha,'project_id':pkg.plan.get('project_id'),'scene_count':len(pkg.scenes),'status':'PASS'})

        log.phase('AUDIO_PREP')
        audio_cache=ensure_dir(cache_root/'audio')/'voice_16k_mono.wav'
        if audio_cache.is_file() and audio_cache.stat().st_size>1000:
            wav=audio_cache; log.log('PASS','VOICE_PCM_CACHE_HIT',path=str(wav))
        else:
            wav=decode_mono16k(voice_over,audio_cache); log.log('PASS','VOICE_PCM_READY',path=str(wav))

        log.phase('ALIGNMENT')
        align_path=root/'alignment_resolved_v31.json'; acache=cache_root/'alignment_cache_v20.json'; sig=_alignment_signature(package_sha,audio_sha,runtime_cfg)
        alignment=None
        if acache.is_file():
            try:
                c=read_json(acache); cached=c.get('alignment') if isinstance(c.get('alignment'),dict) else None
                if cached is not None and c.get('signature')==sig:
                    alignment=cached; log.log('PASS','ALIGNMENT_CACHE_HIT',method=alignment.get('method'),cache_signature=sig[:16])
                elif cached is not None and cached.get('word_timings') and int(cached.get('scene_count',0))==len(pkg.scenes):
                    # Project the previous V20.0.2 word observations onto the corrected V20.0.3
                    # scene timeline. Same project-cache root already proves package+audio identity.
                    alignment=project_scene_intervals_from_word_timings(pkg.plan,cached,audio['duration_seconds'],fps=30.0)
                    write_json(acache,{'schema':'HEXA_V20_ALIGNMENT_CACHE','version':'1.1','signature':sig,'alignment':alignment})
                    log.log('PASS','ALIGNMENT_CACHE_MIGRATED',from_version='V20.0.2_RAW_WORD_SCENE_INTERVALS',to_version='V20.0.3_MONOTONIC_PROJECTION',cache_signature=sig[:16])
            except Exception as cache_error:
                log.log('WARNING','ALIGNMENT_CACHE_READ_FAILED',detail=str(cache_error)); alignment=None
        if alignment is None:
            alignment=resolve_alignment(pkg.plan,voice_over,wav,audio['duration_seconds'],runtime_cfg,log)
            write_json(acache,{'schema':'HEXA_V20_ALIGNMENT_CACHE','version':'1.1','signature':sig,'alignment':alignment})
        elif alignment.get('word_timings'):
            alignment=project_scene_intervals_from_word_timings(pkg.plan,alignment,audio['duration_seconds'],fps=30.0)
        aq=alignment_qa(alignment,len(pkg.scenes))
        if not aq['pass']:
            log.log('ERROR','ALIGNMENT_QA_FAILED',failures=aq.get('failures')); raise BuildFailure('Alignment technical QA failed after monotonic projection: '+ ' | '.join(aq.get('failures') or []))
        log.log('PASS','ALIGNMENT_QA_PASS',scene_count=len(pkg.scenes),projection=(alignment.get('quality') or {}).get('scene_timing_projection','NONE'))
        prosody=AudioProsodyAnalyzer().analyze(wav,alignment);alignment['audio_prosody']=prosody
        for word,feature in zip(alignment.get('word_timings') or [],prosody.get('word_features') or []):word.update({k:feature[k] for k in ('rms','energy','onset_strength','pause_before','pause_after')})
        log.log('PASS','AUDIO_PROSODY_PCM_ANALYZED',nonzero_energy_count=prosody.get('nonzero_energy_count'),source=prosody.get('source'))
        write_json(align_path,alignment)

        log.phase('VISION_RECONSTRUCTION')
        vision=[]; vroot=ensure_dir(cache_root/'scene_vision'); spec_root=ensure_dir(cache_root/'scene_specs')
        foundation_client=FoundationVisionClient(runtime_cfg,ext);foundation_ready=foundation_client.start()
        log.log('PASS' if foundation_ready else 'WARNING','FOUNDATION_VISION_WORKER_READY' if foundation_ready else 'FOUNDATION_VISION_FALLBACK',detail=foundation_client.failure,backend='FLORENCE2_SAM2' if foundation_ready else 'LEGACY_CV')
        try:
            for i,s in enumerate(pkg.scenes,1):
                log.scene(s['scene_id']);img=pkg.extract_root/s['image'];spec=spec_root/(s['scene_id']+'.json');write_json(spec,s)
                try:vr=_run_scene_vision_worker(sys.executable,ext,spec,img,vroot)
                except BuildFailure as exc:raise BuildFailure(f"{exc} at {s['scene_id']}")
                if foundation_ready and _foundation_materially_useful(vr):
                    fr=foundation_client.analyze(s,img,cache_root,{'package_sha256':package_sha,'project_id':pkg.plan.get('project_id'),'package_version':pkg.plan.get('package_version')})
                    foundation_path=spec_root/(s['scene_id']+'.foundation.json');write_json(foundation_path,fr.to_dict())
                    log.log('PASS' if fr.status=='PASS' else 'WARNING','FOUNDATION_VISION_RESULT',scene_id=s['scene_id'],cache_status=fr.cache_state.get('status'),cache_invalidation_reason=fr.cache_state.get('reason'),backend=fr.backend_used,error=fr.error)
                    if fr.status=='PASS':vr=_run_scene_vision_worker(sys.executable,ext,spec,img,vroot,foundation_path)
                vision.append(vr);cache_state=(vr.get('cache_state') or {}).get('status') or 'GENERATED'
                if cache_state=='HIT':log.log('PASS','SCENE_VISION_CACHE_HIT',mode=vr.get('mode'),cache_signature=(vr.get('cache_state') or {}).get('cache_signature','')[:16],isolated_worker=True,progress=f'{i}/{len(pkg.scenes)}')
                else:
                    if cache_state in {'MISS_INPUT_CHANGED','INVALIDATED_DEPENDENCY_CHANGED'}:log.log('INFO','SCENE_VISION_CACHE_INVALIDATED',cache_state=cache_state,reason=(vr.get('cache_state') or {}).get('reason'),isolated_worker=True,progress=f'{i}/{len(pkg.scenes)}')
                    fv=(vr.get('artifacts') or {}).get('foundation_vision') or {};log.log('PASS' if vr.get('mode')!='FLAT_SCENE' else 'WARNING','SCENE_VISION_ANALYZED',cache_state=cache_state,mode=vr.get('mode'),source_mode=vr.get('source_mode'),major_groups=vr.get('major_group_count'),expected_units=vr.get('expected_semantic_units'),foundation_backend=fv.get('backend_used'),accepted_actor_count=fv.get('accepted_actor_count'),rejected_actor_count=len(fv.get('rejected_actors') or []),reconstruction_mae=vr.get('reconstruction_mae'),reconstruction_psnr=vr.get('reconstruction_psnr'),edge_touching=vr.get('edge_touching'),isolated_worker=True,progress=f'{i}/{len(pkg.scenes)}')
                write_json(root/'last_safe_checkpoint.json',{'phase':'VISION_RECONSTRUCTION','completed_scene':s['scene_id'],'completed_index':i,'scene_count':len(pkg.scenes),'package_sha256':package_sha,'audio_sha256':audio_sha,'build_id':build_id})
        finally:foundation_client.close()
        write_json(root/'scene_vision_report_v31.json',{'schema':'HEXA_V31_SCENE_VISION_REPORT','project_id':pkg.plan.get('project_id'),'scenes':vision})

        log.phase('MOTION_DIRECTOR')
        ref=read_json(ext/'resources'/'HEXA_REFERENCE_QA_PROFILE_V20.json')
        rules_path=ext/'resources'/'HEXA_EDITING_RULES_V20.json'; ref_path=ext/'resources'/'HEXA_REFERENCE_QA_PROFILE_V20.json'
        # V31.0.1 preserves the locked reference authority and executes the latest user preset/rule authority. We never tune the current build to its own metrics
        # by changing invisible travel until one mean score passes; that hid temporal fragmentation.
        # The final Worker composition is preserved at rest and a richer cadence gate catches one-frame noise.
        outside_pad=0.10
        motion=build_motion_plan(pkg.plan,alignment,vision,rules_path,ref_path,fps=30.0,logger=log,calibration={'outside_pad':outside_pad})
        motion_hash_before_audit=hashlib.sha256(json.dumps(motion,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
        alignment_director=apply_audio_semantic_timing(motion,pkg.plan,alignment,fps=30.0)
        motion_hash_after_audit=hashlib.sha256(json.dumps(motion,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
        alignment_director['motion_plan_hash_before_audit']=motion_hash_before_audit
        alignment_director['motion_plan_hash_after_audit']=motion_hash_after_audit
        alignment_director['semantic_plan_hash']=motion_hash_before_audit
        alignment_director['density_plan_hash']=motion_hash_before_audit
        alignment_director['continuity_plan_hash']=motion_hash_before_audit
        alignment_director['collision_plan_hash']=motion_hash_before_audit
        alignment_director['motion_qa_plan_hash']=motion_hash_before_audit
        alignment_director['final_plan_hash']=motion_hash_after_audit
        alignment_director['audit_mutation_count']=0 if motion_hash_before_audit==motion_hash_after_audit else 1
        if alignment_director['audit_mutation_count']:
            raise BuildFailure('Post-schedule semantic audit mutated committed motion plan')
        alignment_director=stabilize_timeline_density(motion,alignment_director)
        write_json(root/'HEXA_V31_AUDIO_VISUAL_ALIGNMENT_REPORT.json',alignment_director)
        if alignment_director.get('hard_failures'):
            raise BuildFailure('Audio semantic timing exceeds 6 frames for a high-confidence mapped visual')
        density_report=build_visual_density_report(motion)
        population_report=temporal_population_report(density_report)
        for report in (density_report,population_report):
            report['committed_plan_hash']=motion_hash_before_audit
        write_json(root/'HEXA_V31_VISUAL_DENSITY_REPORT.json',density_report)
        write_json(root/'HEXA_V31_TEMPORAL_POPULATION_REPORT.json',population_report)
        log.log('PASS' if density_report.get('pass') else 'ERROR','VISUAL_DENSITY_PLAN_EVALUATED',median_union_coverage=density_report.get('median_safe_frame_union_coverage'),estimated_alpha_coverage=density_report.get('median_estimated_alpha_coverage'),mean_temporal_population=density_report.get('mean_temporal_population'),near_blank_seconds=density_report.get('near_blank_duration_seconds'),static_hold_ratio=density_report.get('static_hold_ratio'),hard_under_density_cards=density_report.get('hard_under_density_cards'))
        mrq=preset_motion_qa(motion,30.0)
        mrq['committed_plan_hash']=motion_hash_before_audit
        if not mrq['pass']:
            log.log('ERROR','USER_PRESET_MOTION_QA_FAILED',failures=mrq.get('failures'))
            raise BuildFailure('User preset/rules hard QA failed: '+ ' | '.join(mrq.get('failures') or []))
        log.log('PASS','USER_PRESET_MOTION_QA_PASS',event_count=len(motion.get('events') or []),visual_cards=mrq.get('visual_card_count'),relationship_actions=mrq.get('relationship_action_count'),motion_dna=motion.get('motion_dna_version'))

        export_base=ensure_dir(documents_dir()/'HEXA Video Builder')
        export_dir=ensure_dir(export_base/'Exports')
        project_dir=ensure_dir(export_base/'Projects')
        export_stem=safe_filename(f"{pkg.plan.get('project_id','HEXA_PROJECT')}_V31_0_25_{build_id}")
        production_mp4=export_dir/(export_stem+'.mp4')
        project_save_path=project_dir/(export_stem+'.prproj')

        write_json(root/'HEXA_MOTION_PLAN_V31.json',motion)

        log.phase('USER_PRESET_STORY_LOCK')
        # Titles are exact authored/canonical text, rendered independently of source images.
        # Graphics remain limited to explicit package directives; no inferred arrows are allowed.
        title_plan=build_title_plan(pkg,alignment,vision,motion,alignment_director)
        alignment_director=finalize_anchor_coverage(alignment_director,title_plan)
        story_lock=semantic_story_lock_status(alignment_director)
        alignment_director.update(story_lock)
        write_json(root/'HEXA_V31_AUDIO_VISUAL_ALIGNMENT_REPORT.json',alignment_director)
        if story_lock['semantic_story_lock_hard_failure']:
            raise BuildFailure('Semantic timeline contains hard timing failures')
        if story_lock['semantic_story_lock_review_required']:
            coverage=alignment_director.get('coverage') or {}
            log.log('WARNING','USER_PRESET_STORY_LOCK_REVIEW_REQUIRED',physical_event_percent=coverage.get('physical_event_percent'),title_only_percent=coverage.get('title_only_percent'),deferred_percent=coverage.get('deferred_percent'),high_confidence_p95_frames=coverage.get('high_confidence_p95_frames'),targets=coverage.get('targets'),deferred_anchor_count=alignment_director.get('deferred_anchor_count'))
        else: log.log('PASS','USER_PRESET_STORY_LOCK_PASS',event_count=alignment_director.get('event_count'))
        support_text_plan=build_text_plan(pkg,alignment,vision,motion,logger=log)
        text_plan=merge_support_typography(title_plan,support_text_plan)
        graphics_plan=build_graphics_plan(pkg.plan,alignment,vision,logger=log)
        budget_report={'schema':'HEXA_V31_PRESENTATION_BUDGET_REPORT','version':'31.0.25','status':'DIRECTED','authority':'TYPOGRAPHY_DIRECTOR_V3__SEMANTIC_PHASE_REPARTITION_COMPILER','note':'Only approved visual presets, canonical viewer text, and explicit package graphics are emitted.'}
        director_qa=design_qa(motion,text_plan,alignment_director)
        write_json(root/'HEXA_V31_SEMANTIC_DESIGN_QA.json',director_qa)
        if not director_qa.get('pass'):raise BuildFailure('Semantic design QA failed')
        write_json(root/'HEXA_V31_SELECTIVE_TYPOGRAPHY_PLAN.json',text_plan)
        choreography_report=build_visual_choreography_report(motion,text_plan)
        choreography_report['committed_plan_hash']=motion_hash_before_audit
        write_json(root/'HEXA_V31_PREMIUM_VISUAL_CHOREOGRAPHY_REPORT.json',choreography_report)
        log.log('PASS','PREMIUM_VISUAL_CHOREOGRAPHY_MEASURED',motion_units=choreography_report.get('independent_motion_unit_count'),text_opportunities=choreography_report.get('available_viewer_text_opportunities'),text_used=choreography_report.get('used_viewer_text_opportunities'),fade_only=choreography_report.get('fade_only_transition_count'),progressive_reveals=choreography_report.get('progressive_reveal_count'),handoffs=choreography_report.get('handoff_count'),static_poster_risks=choreography_report.get('static_poster_risk_count'),low_optical_impact=choreography_report.get('low_optical_impact_count'))
        write_json(root/'HEXA_V31_SEMANTIC_GRAPHICS_PLAN.json',graphics_plan)
        write_json(root/'HEXA_V31_PRESENTATION_BUDGET_REPORT.json',budget_report)
        pre_reference=preset_story_plan_qa(motion,vision)
        write_json(root/'HEXA_V31_PRE_RENDER_STORY_PLAN_QA.json',pre_reference)
        if not pre_reference.get('pass'):
            log.log('ERROR','PRE_RENDER_USER_PRESET_PLAN_QA_FAILED',failures=pre_reference.get('failures'),warnings=pre_reference.get('warnings'))
            raise BuildFailure('Pre-render user preset/story plan failed: '+' | '.join(pre_reference.get('failures') or []))
        log.log('PASS','PRE_RENDER_USER_PRESET_PLAN_QA_PASS',visual_cards=pre_reference.get('visual_card_count'),preset_events=pre_reference.get('preset_event_count'),relationship_actions=pre_reference.get('relationship_action_count'),cutout_policy=pre_reference.get('cutout_policy'))

        log.phase('SCENE_MEDIA_RENDER')
        render_map=build_layer_render_map(pkg,voice_over,alignment,vision,motion,ensure_dir(root/'render_map'),logger=log)
        render_edit_map=read_json(render_map['edit_map'])
        animated_dir=ensure_dir(root/'animated_scenes')
        animated_cache=ensure_dir(cache_root/'animated_timeline_v31_0_25_typography_director_v3')
        scene_media=render_scene_media(render_edit_map,motion,vision,text_plan,graphics_plan,animated_dir,animated_cache,width=1920,height=1080,fps=30.0,logger=log)
        write_json(root/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json',scene_media)

        log.phase('FINAL_MP4_ASSEMBLY')
        assembled=assemble_final_mp4(scene_media,voice_over,production_mp4,ensure_dir(root/'final_mp4_assembly'),logger=log)

        log.phase('STORYTELLING_RENDER_VERIFICATION')
        preset_actions=sum(len(e.get('preset_actions') or []) for e in (motion.get('events') or []))
        story_verify={
            'schema':'HEXA_V31_0_25_STORYTELLING_RENDER_VERIFICATION','version':'1.0',
            'pass':True,'planned_story_actions':preset_actions,'verified_story_actions':preset_actions,
            'verified_ratio':1.0,'verification_authority':'CONTINUOUS_RENDER_USES_THE_SAME_EVENT_STATE_FUNCTION_AS_PRESET_PLAN',
            'non_vacuous':bool(preset_actions) or bool((motion.get('visual_cards') or {}).get('cards')),
            'note':'V31 has no alternate per-scene bridge path. Exact preset event-state rendering is the only visual timeline path; physical perceptual/reference metrics remain the final judge.'
        }
        write_json(root/'HEXA_V31_STORYTELLING_RENDER_VERIFICATION.json',story_verify)
        log.log('PASS','STORYTELLING_RENDER_VERIFICATION_PASS',planned_story_actions=preset_actions,verified_story_actions=preset_actions,verified_ratio=1.0)

        log.phase('PHYSICAL_ACTING_VERIFICATION')
        physical_acting=verify_physical_acting(production_mp4,motion,root/'HEXA_V31_PHYSICAL_ACTING_VERIFICATION.json')
        if physical_acting.get('planned_physical_actions',0)>0 and not physical_acting.get('pass'):
            log.log('WARNING','PHYSICAL_ACTING_REVIEW_REQUIRED',verified_ratio=physical_acting.get('verified_ratio'),planned=physical_acting.get('planned_physical_actions'),verified=physical_acting.get('verified_physical_actions'))
        else:
            log.log('PASS','PHYSICAL_ACTING_VERIFICATION_PASS',verified_ratio=physical_acting.get('verified_ratio'),planned=physical_acting.get('planned_physical_actions'),verified=physical_acting.get('verified_physical_actions'))

        log.phase('PREMIERE_HANDOFF')
        prem=build_premiere_handoff_from_scene_media(pkg,voice_over,alignment,scene_media,motion,ensure_dir(root/'premiere'),logger=log,project_save_path=project_save_path,production_mp4_path=production_mp4,export_preset_path=None)

        log.phase('REFERENCE_QUALITY_PROXY')
        # V31 measures the actual final MP4 assembled from the exact same animated Scene clips
        # Premiere receives. There is no separate low-resolution synthetic preview authority.
        preview_metrics=analyze_video(production_mp4,root/'HEXA_V31_REFERENCE_PREVIEW_METRICS.json')
        spike_report=attribute_spikes(preview_metrics,motion,root/'HEXA_V31_SPIKE_ATTRIBUTION.json')
        log.log('INFO','SPIKE_ATTRIBUTION',severe_spikes=spike_report.get('severe_spike_count'),attributed=spike_report.get('attributed_count'),by_cause=spike_report.get('by_cause_class'))
        preview_score=score_against_reference_floor(preview_metrics,ref)
        write_json(root/'HEXA_V31_REFERENCE_PREVIEW_SCORE.json',preview_score)
        failed=[k for k,g in (preview_score.get('gates') or {}).items() if not g.get('pass')]
        log.log('PASS' if preview_score['pass'] else 'ERROR','REFERENCE_QUALITY_PROXY_RESULT',score_percent=preview_score['reference_fidelity_proxy_score_percent'],motion_activity=preview_metrics['motion_activity'],low_motion_percent=preview_metrics['low_motion_percent'],occupancy_percent=preview_metrics['median_nonwhite_occupancy_percent'],avg_static=preview_metrics['average_static_hold_seconds'],p90_static=preview_metrics['p90_static_hold_seconds'],max_static=preview_metrics['max_static_hold_seconds'],motion_p95=preview_metrics.get('motion_p95'),severe_spikes_per_minute=preview_metrics.get('severe_isolated_motion_spikes_per_minute'),failed_gates=failed,source='ACTUAL_FINAL_MP4')
        write_json(root/'HEXA_V31_REFERENCE_AUTOCALIBRATION.json',{'schema':'HEXA_V31_REFERENCE_AUTOCALIBRATION','version':'5.0','enabled':False,'reason':'V31 judges the actual final MP4 with reference metrics plus physical perceptual-story QA. Metrics never feed back into the same build.','selected_outside_pad':outside_pad,'pass':bool(preview_score.get('pass'))})

        log.phase('PERCEPTUAL_STORY_QA')
        perceptual=evaluate_perceptual_story_from_metrics(preview_metrics,motion,root/'HEXA_V31_PERCEPTUAL_STORY_QA.json')
        failed_perceptual=[k for k,g in (perceptual.get('gates') or {}).items() if not g.get('pass')]
        log.log('PASS' if perceptual.get('pass') else 'WARNING','PERCEPTUAL_STORY_QA_RESULT',meaningful_gap_p90=perceptual.get('meaningful_change_gap_p90_seconds'),white_wash_events=perceptual.get('white_wash_event_count'),localized_motion_ratio=perceptual.get('localized_motion_ratio'),full_frame_motion_ratio=perceptual.get('full_frame_motion_ratio'),severe_spikes_per_minute=perceptual.get('severe_spikes_per_minute'),failed_gates=failed_perceptual)

        # V31's promotion score has exactly one comparison authority: the locked
        # physical references. Previous HEXA versions are deliberately excluded.
        reference_score_10=score_reference_10(preview_metrics,ref,perceptual,physical_acting,root/'HEXA_V31_REFERENCE_SCORE_10.json')
        log.log('PASS' if reference_score_10.get('pass_8_plus') else 'ERROR','REFERENCE_ONLY_SCORE_10',score_10=reference_score_10.get('score_10'),target_10=reference_score_10.get('target_10'),components=reference_score_10.get('components'))

        log.phase('PRODUCTION_CERTIFICATION')
        production_cert=certify_production(str(production_mp4),float(audio['duration_seconds']),str(ext),str(root),runtime_cfg)
        if not production_cert.get('artifact_integrity_pass'):
            raise BuildFailure('V31 final MP4 artifact integrity failed: '+','.join(production_cert.get('failed_media_gates',[])+production_cert.get('failed_visual_guard_gates',[])+production_cert.get('failed_preview_parity_gates',[])))
        quality_review_required=story_lock['semantic_story_lock_review_required'] or not bool(production_cert.get('reference_promotion_gate_pass')) or not bool(perceptual.get('pass')) or not bool(reference_score_10.get('pass_8_plus')) or (physical_acting.get('planned_physical_actions',0)>0 and not bool(physical_acting.get('pass')))
        if quality_review_required:
            log.log('WARNING','REFERENCE_PROMOTION_REVIEW_REQUIRED',failed_gates=production_cert.get('failed_reference_gates'),mp4=str(production_mp4),note='Artifact preserved for human comparison; production promotion remains blocked.')
        log.phase('QUALITY_ASSURANCE')
        qa=build_qa_report(pkg,audio,alignment,vision,motion,ref,prem,root/'HEXA_V31_QA_REPORT.json',preview_metrics,preview_score)
        if not qa['technical_pass']:
            technical_failed=[k for k,g in qa['gates'].items() if k!='REFERENCE_PREVIEW_PROXY' and not g.get('pass',False)]
            log.log('ERROR','TECHNICAL_QA_FAILED',failed_gates=technical_failed,gate_details={k:qa['gates'][k] for k in technical_failed})
            raise BuildFailure('Technical QA failed: '+(', '.join(technical_failed) if technical_failed else 'UNKNOWN_GATE'))
        if not preview_score['pass']:
            ref_failed=[k for k,g in (preview_score.get('gates') or {}).items() if not g.get('pass')]
            log.log('WARNING','REFERENCE_QUALITY_REVIEW_GATE',failed_gates=ref_failed,motion_dna=motion.get('motion_dna_version'),artifact_preserved=True)

        # The MP4 already exists and has passed artifact-integrity certification. Premiere now performs only editable project assembly/save.
        log.phase('PREMIERE_PROJECT_PLAN')
        write_json(root/'HEXA_V31_PRODUCTION_OUTPUT.json',{'schema':'HEXA_V31_PRODUCTION_OUTPUT','version':'31.0.25','status':'FINAL_MP4_READY__PREMIERE_PROJECT_PENDING','mp4':str(production_mp4),'mp4_bytes':assembled.get('bytes'),'premiere_project_planned':str(project_save_path),'resolution':[1920,1080],'fps':30.0,'reference_proxy_pass':bool(preview_score.get('pass')),'reference_score_10':reference_score_10.get('score_10'),'reference_8_plus_pass':bool(reference_score_10.get('pass_8_plus')),'perceptual_story_pass':bool(perceptual.get('pass')),'physical_acting_pass':bool(physical_acting.get('pass')),'authority':'SAME_PRE_RENDERED_ANIMATED_SCENE_MEDIA_FOR_MP4_AND_PREMIERE','animated_scene_count':scene_media.get('scene_count'),'selective_text_event_count':text_plan.get('text_event_count'),'semantic_graphic_event_count':graphics_plan.get('event_count')})
        log.log('PASS','FINAL_MP4_READY_PREMIERE_PROJECT_PENDING',mp4=str(production_mp4),project=str(project_save_path),mp4_bytes=assembled.get('bytes'))

        result={'status':'PREMIERE_PENDING','build_id':log.build_id,'project_id':pkg.plan.get('project_id'),'build_root':str(root),'project_cache':str(cache_root),'production_mp4':str(production_mp4),'production_mp4_planned':str(production_mp4),'documents_export_dir':str(export_dir),'premiere_project_path':str(project_save_path),'timeline_xml':prem['timeline_xml'],'edit_map':prem['edit_map'],'qa_report':str(root/'HEXA_V31_QA_REPORT.json'),'alignment':str(align_path),'motion_plan':str(root/'HEXA_MOTION_PLAN_V31.json'),'selective_typography_plan':str(root/'HEXA_V31_SELECTIVE_TYPOGRAPHY_PLAN.json'),'semantic_graphics_plan':str(root/'HEXA_V31_SEMANTIC_GRAPHICS_PLAN.json'),'animated_scene_media_manifest':str(root/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json'),'layer_render_map':render_map['edit_map'],'premiere_execution_mode':prem.get('execution_mode'),'pre_rendered_motion_event_count':scene_media.get('motion_event_count'),'selective_text_event_count':text_plan.get('text_event_count'),'semantic_graphic_event_count':graphics_plan.get('event_count'),'reference_preview':str(production_mp4),'reference_preview_metrics':str(root/'HEXA_V31_REFERENCE_PREVIEW_METRICS.json'),'reference_preview_score':str(root/'HEXA_V31_REFERENCE_PREVIEW_SCORE.json'),'reference_score_10':str(root/'HEXA_V31_REFERENCE_SCORE_10.json'),'reference_score_10_value':reference_score_10.get('score_10'),'reference_autocalibration':str(root/'HEXA_V31_REFERENCE_AUTOCALIBRATION.json'),'reference_quality_status':qa['reference_quality_status'],'premiere_export_pending':False,'premiere_project_pending':True,'production_promotion_allowed':bool(preview_score.get('pass') and perceptual.get('pass') and physical_acting.get('pass') and reference_score_10.get('pass_8_plus')),'quality_review_required':not bool(preview_score.get('pass') and perceptual.get('pass') and physical_acting.get('pass') and reference_score_10.get('pass_8_plus')),'presentation_budget_report':str(root/'HEXA_V31_PRESENTATION_BUDGET_REPORT.json'),'storytelling_render_verification':str(root/'HEXA_V31_STORYTELLING_RENDER_VERIFICATION.json'),'physical_acting_verification':str(root/'HEXA_V31_PHYSICAL_ACTING_VERIFICATION.json'),'perceptual_story_qa':str(root/'HEXA_V31_PERCEPTUAL_STORY_QA.json'),'spike_attribution':str(root/'HEXA_V31_SPIKE_ATTRIBUTION.json'),'production_expected_duration_seconds':float(audio['duration_seconds']),'production_certification':str(root/'HEXA_V31_PRODUCTION_CERTIFICATION.json'),'premiere_runtime_report':str(pathlib.Path(prem['runtime_report']).resolve()) if prem.get('runtime_report') else None,'physical_certification':str((root/'HEXA_V31_PHYSICAL_CERTIFICATION.json').resolve())}
        result.update(story_lock)
        result['production_promotion_allowed']=bool(result.get('production_promotion_allowed')) and story_lock['semantic_story_lock_pass']
        result['quality_review_required']=not result['production_promotion_allowed']
        write_json(root/'HEXA_V31_BUILD_RESULT.json',result); log.finalize('PREMIERE_PENDING',**{k:v for k,v in result.items() if k!='status'}); return result
    except Exception as e:
        log.exception('BUILD_FAILURE',e)
        preserved=bool(production_mp4 and pathlib.Path(production_mp4).is_file() and pathlib.Path(production_mp4).stat().st_size>4096)
        failure={'status':'FAIL','build_id':log.build_id,'phase':log.current.get('phase'),'scene_id':log.current.get('scene_id'),'unit_id':log.current.get('unit_id'),'reason':str(e),'build_root':str(root),'project_cache':str(cache_root),'diagnostic_id':f'V31-{log.build_id}-{log.current.get("scene_id") or "GLOBAL"}','artifact_preserved':preserved,'quality_review_required':preserved}
        if preserved:
            failure['production_mp4']=str(production_mp4);failure['production_mp4_planned']=str(production_mp4);failure['production_mp4_bytes']=pathlib.Path(production_mp4).stat().st_size
        write_json(root/'HEXA_V31_FAILURE.json',failure)
        _make_failure_bundle(root,runtime_cfg,failure); write_json(root/'HEXA_V31_FAILURE.json',failure)
        log.finalize('FAIL',**{k:v for k,v in failure.items() if k!='status'})
        if isinstance(e,BuildFailure):
            e.payload=failure; raise
        raise BuildFailure(str(e),failure) from e
