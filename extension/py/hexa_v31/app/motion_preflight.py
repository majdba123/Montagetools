from __future__ import annotations

import datetime
import hashlib
import json
import pathlib

from hexa_v31.composition_qa import card_motion_conflicts, composition_plan_qa
from hexa_v31.design_director import apply_audio_semantic_timing
from hexa_v31.interaction.director import assert_final_motion_plan_immutable
from hexa_v31.motion import build_motion_plan
from hexa_v31.package_io import open_and_validate
from hexa_v31.preset_qa import preset_motion_qa, preset_story_plan_qa
from hexa_v31.util import ensure_dir, read_json, sha256_file, write_json


def _cached_inputs(project_root: pathlib.Path, package_sha: str, scene_count: int):
    for run in sorted((project_root / 'runs').glob('*'), reverse=True):
        alignment=run / 'alignment_resolved_v31.json'
        vision=run / 'scene_vision_report_v31.json'
        audit=run / 'package_audit.json'
        if not (alignment.is_file() and vision.is_file() and audit.is_file()):
            continue
        try:
            if read_json(audit).get('package_sha256') != package_sha:
                continue
            rows=(read_json(vision).get('scenes') or [])
            if len(rows) != scene_count:
                continue
            return read_json(alignment), rows, run
        except Exception:
            continue
    raise RuntimeError('No complete hash-matched alignment/Vision cache is available for motion preflight')


def motion_preflight(scene_package_zip: str, voice_over: str, work_root: str, extension_root: str):
    ext=pathlib.Path(extension_root).resolve();work=pathlib.Path(work_root).resolve()
    package_sha=sha256_file(scene_package_zip);audio_sha=sha256_file(voice_over)
    project_root=work/f'{package_sha[:12]}_{audio_sha[:12]}'
    pkg=open_and_validate(scene_package_zip,ensure_dir(project_root/'cache'/'packages'))
    alignment,vision,source_run=_cached_inputs(project_root,package_sha,len(pkg.scenes))
    rules=ext/'resources'/'HEXA_EDITING_RULES_V20.json';reference=ext/'resources'/'HEXA_REFERENCE_QA_PROFILE_V20.json'
    motion=build_motion_plan(pkg.plan,alignment,vision,rules,reference,fps=30.0,calibration={'outside_pad':.10})
    semantic=apply_audio_semantic_timing(motion,pkg.plan,alignment,fps=30.0)
    motion_qa=preset_motion_qa(motion,30.0)
    duration=max((float(row.get('end',0.0)) for row in alignment.get('scene_timings') or []),default=0.0)
    story_qa=preset_story_plan_qa(motion,vision,duration)
    immutable=assert_final_motion_plan_immutable(motion)
    composition=composition_plan_qa(motion)
    cards=(motion.get('visual_cards') or {}).get('cards') or [];events=motion.get('events') or []
    conflicts=[]
    for card in cards:
        local=[event for event in events if str(event.get('visual_card_id'))==str(card.get('card_id')) and not event.get('suppressed_by_card_density')]
        conflicts.extend(card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),30.0))
    same=sum(1 for row in conflicts if str(next((e.get('scene_id') for e in events if e.get('event_id')==row.get('event_a')),''))==str(next((e.get('scene_id') for e in events if e.get('event_id')==row.get('event_b')),'UNKNOWN')))
    final_handoff=(motion.get('final_lifetime_commit') or {}).get('partition_handoff_repair') or {}
    failures=[]
    if semantic.get('hard_failures'):failures.append('SEMANTIC_TIMING')
    if not motion_qa.get('pass'):failures.append('PRESET_MOTION_QA')
    if not story_qa.get('pass'):failures.append('PRESET_STORY_QA')
    if not composition.get('pass'):failures.append('COMPOSITION_QA')
    if conflicts:failures.append('TRAJECTORY_COLLISIONS')
    result={'status':'MOTION_PREFLIGHT_PASS' if not failures else 'MOTION_PREFLIGHT_FAIL','package_sha256':package_sha,'voice_sha256':audio_sha,'cached_artifact_run':str(source_run),'vision_cache_reused':True,'foundation_inference_ran':False,'rendering_ran':False,'encoding_ran':False,'visual_card_count':len(cards),'event_count':len(events),'collision_count':len(conflicts),'same_scene_unresolved_conflict_count':same,'final_handoff_unresolved_conflict_count':int(final_handoff.get('unresolved_conflict_count') or 0),'failures':failures,'composition_qa':composition,'motion_qa':motion_qa,'story_qa':story_qa,'semantic_timing_hard_failures':semantic.get('hard_failures') or [],'finalization_barrier':immutable}
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');out=ensure_dir(project_root/'motion_preflight'/stamp);write_json(out/'HEXA_V31_MOTION_PREFLIGHT.json',result);write_json(out/'HEXA_MOTION_PLAN_V31.json',motion);result['result_path']=str(out/'HEXA_V31_MOTION_PREFLIGHT.json')
    return result
