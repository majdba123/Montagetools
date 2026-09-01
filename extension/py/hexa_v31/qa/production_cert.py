from __future__ import annotations
import os, pathlib
from typing import Any
from hexa_v31.util import read_json, write_json, sha256_file
from hexa_v31.media_probe import summarize_media
from hexa_v31.reference_metrics import analyze_video, score_against_reference_floor


def _probe_media(mp4:pathlib.Path, expected_duration:float, runtime_cfg:dict)->dict[str,Any]:
    ffprobe=str(runtime_cfg.get('ffprobe_path') or os.environ.get('HEXA_FFPROBE') or '') or None
    ffmpeg=str(runtime_cfg.get('ffmpeg_path') or os.environ.get('HEXA_FFMPEG') or '') or None
    media=summarize_media(mp4,ffprobe=ffprobe,ffmpeg=ffmpeg,timeout=60)
    v=media.get('video'); audios=media.get('audio_streams') or []; dur=float(media.get('duration_seconds') or 0.0)
    tol=max(1.5,float(expected_duration or 0.0)*0.025)
    gates={
        'video_stream_present':bool(v),
        'resolution_1920x1080':bool(v and int(v.get('width') or 0)==1920 and int(v.get('height') or 0)==1080),
        'audio_stream_present':bool(audios),
        'duration_within_tolerance':bool(dur>0 and (not expected_duration or abs(dur-float(expected_duration))<=tol)),
    }
    return {'pass':all(gates.values()),'gates':gates,'probe_backend':media.get('backend'),'duration_seconds':dur,'expected_duration_seconds':float(expected_duration or 0.0),'duration_tolerance_seconds':tol,'video':v,'audio_stream_count':len(audios),'raw':media.get('raw')}


def certify_production(mp4_path:str, expected_duration:float, extension_root:str, out_dir:str, runtime_cfg:dict)->dict[str,Any]:
    mp4=pathlib.Path(mp4_path).resolve(); out=pathlib.Path(out_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    if not mp4.is_file() or mp4.stat().st_size<=100000:
        raise RuntimeError('Production MP4 missing or too small for certification: '+str(mp4))
    ref=read_json(pathlib.Path(extension_root)/'resources'/'HEXA_REFERENCE_QA_PROFILE_V20.json')
    media=_probe_media(mp4,float(expected_duration or 0.0),runtime_cfg)
    metrics=analyze_video(mp4,out/'HEXA_V31_PRODUCTION_RENDER_METRICS.json')
    score=score_against_reference_floor(metrics,ref)
    write_json(out/'HEXA_V31_PRODUCTION_RENDER_SCORE.json',score)
    # Explicit blank/off-screen guard in addition to the reference gates. A fully
    # white Premiere render (the V20.0.4 screenshot failure mode) has ~0 occupancy.
    visual_guard={
        'frame_count_gt_30':int(metrics.get('frame_count') or 0)>30,
        'median_nonwhite_occupancy_ge_3pct':float(metrics.get('median_nonwhite_occupancy_percent') or 0.0)>=3.0,
        'underfilled_frame_percent_le_20pct':float(metrics.get('underfilled_frame_percent_lt15pct',100.0))<=20.0,
    }
    # The physical Premiere render must also stay reasonably close to the offline
    # reference-QA preview. This catches silent keyframe/geometry failures even when
    # a coarse aggregate reference gate could otherwise look plausible.
    preview_path=out/'HEXA_V31_REFERENCE_PREVIEW_METRICS.json'
    preview=read_json(preview_path) if preview_path.is_file() else None
    preview_parity={'available':bool(preview),'pass':True,'gates':{}}
    if preview:
        def pg(name,actual,expected,tol):
            delta=abs(float(actual)-float(expected)); ok=delta<=float(tol)
            preview_parity['gates'][name]={'pass':ok,'actual':actual,'preview':expected,'abs_delta':delta,'tolerance':tol}
            return ok
        checks=[
            pg('motion_activity_parity',metrics.get('motion_activity',0),preview.get('motion_activity',0),0.004),
            pg('low_motion_percent_parity',metrics.get('low_motion_percent',0),preview.get('low_motion_percent',0),10.0),
            pg('occupancy_percent_parity',metrics.get('median_nonwhite_occupancy_percent',0),preview.get('median_nonwhite_occupancy_percent',0),10.0),
            pg('max_static_hold_parity',metrics.get('max_static_hold_seconds',0),preview.get('max_static_hold_seconds',0),1.0),
        ]
        preview_parity['pass']=all(checks)
    artifact_ok=bool(media['pass'] and all(visual_guard.values()) and preview_parity['pass'])
    reference_ok=bool(score.get('pass'))
    status='PASS' if artifact_ok and reference_ok else 'REVIEW_REQUIRED' if artifact_ok else 'FAIL'
    result={
        'schema':'HEXA_V31_PRODUCTION_CERTIFICATION','version':'31.0.25','status':status,
        'artifact_integrity_pass':artifact_ok,'reference_promotion_gate_pass':reference_ok,
        'mp4':str(mp4),'mp4_bytes':mp4.stat().st_size,'mp4_sha256':sha256_file(mp4),
        'media_contract':media,'visual_content_guard':visual_guard,'offline_preview_parity':preview_parity,
        'reference_proxy_pass':reference_ok,
        'reference_fidelity_proxy_score_percent':score.get('reference_fidelity_proxy_score_percent'),
        'reference_score':score,'reference_metrics':metrics,
        'failed_media_gates':[k for k,v in media.get('gates',{}).items() if not v],
        'failed_visual_guard_gates':[k for k,v in visual_guard.items() if not v],
        'failed_reference_gates':[k for k,v in (score.get('gates') or {}).items() if not v.get('pass')],
        'failed_preview_parity_gates':[k for k,v in preview_parity.get('gates',{}).items() if not v.get('pass')],
        'human_reference_comparison_pending':True,
        'promotion_allowed':bool(artifact_ok and reference_ok),
        'note':'V31 separates artifact integrity from reference promotion. A physically valid MP4 is preserved and reviewable even when the automated reference floor requests another quality iteration.'
    }
    write_json(out/'HEXA_V31_PRODUCTION_CERTIFICATION.json',result)
    return result
