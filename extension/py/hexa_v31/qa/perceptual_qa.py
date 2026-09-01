from __future__ import annotations
import os, pathlib, math
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from hexa_v31.util import write_json
from hexa_v31.reference_metrics import _detect_white_wash_events

EVAL_W=426; EVAL_H=240


def _occ(fr):
    return float(np.mean(np.min(fr,axis=2)<248)*100.0)


def _centroid(mask):
    yy,xx=np.where(mask)
    if len(xx)<8:return None
    return float(xx.mean()),float(yy.mean())


def analyze_perceptual_story(video_path:str|os.PathLike, motion_plan:dict, out_json:str|os.PathLike|None=None)->dict:
    """Streaming physical QA over the actual final MP4.

    V23-V27 exposed three failures that plan-level counters could hide: long poster plateaus,
    one-frame shocks, and white-background dissolves that visually wash the composition away.
    V31 measures those effects on the encoded output while keeping memory bounded on low-RAM
    Premiere workstations. No decoded full-video frame list is retained.
    """
    p=pathlib.Path(video_path);cap=cv2.VideoCapture(str(p))
    if not cap.isOpened():raise RuntimeError(f'Cannot open final MP4: {p}')
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.0);step=max(1,int(round(fps*0.20)))
    diffs=[];changed=[];occ=[];ink=[];luma=[];change_times=[];prev_gray=None;sample_gray=None;sample_index=0;frame_count=0
    while True:
        ok,fr=cap.read()
        if not ok:break
        fr=cv2.resize(fr,(EVAL_W,EVAL_H),interpolation=cv2.INTER_AREA);g=cv2.cvtColor(fr,cv2.COLOR_BGR2GRAY)
        occ.append(_occ(fr));ink.append(float(np.mean((255.0-g.astype(np.float32))/255.0)*100.0));luma.append(float(np.mean(g)))
        if prev_gray is not None:
            d=cv2.absdiff(prev_gray,g);diffs.append(float(np.mean(d))/255.0*2.0);changed.append(float(np.mean(d>=7)*100.0))
        if sample_gray is None:
            sample_gray=g.copy();sample_index=frame_count
        elif frame_count-sample_index>=step:
            d=cv2.absdiff(sample_gray,g);md=float(np.mean(d));cp=float(np.mean(d>=5)*100.0)
            if md>=0.85 or cp>=1.15:change_times.append(frame_count/fps)
            sample_gray=g.copy();sample_index=frame_count
        prev_gray=g;frame_count+=1
    cap.release()
    if frame_count<3:raise RuntimeError('Final MP4 too short for perceptual QA')
    arr=np.asarray(diffs,dtype=np.float32)
    severe=[]
    for i in range(1,len(arr)-1):
        if arr[i]>=0.08 and arr[i]>1.8*max(float(arr[i-1]),float(arr[i+1]),1e-9):severe.append((i+1)/fps)
    duration_seconds=frame_count/fps;duration_min=max(1e-6,duration_seconds/60.0)

    gaps=[];last=0.0
    for t in change_times:gaps.append(t-last);last=t
    gaps.append(duration_seconds-last)

    wash=_detect_white_wash_events(occ,ink,luma,fps)

    active=[j for j,x in enumerate(changed) if x>=0.10]
    local_ratio=sum(1 for j in active if 0.10<=changed[j]<=24.0)/max(1,len(active))
    full_ratio=sum(1 for j in active if changed[j]>=45.0)/max(1,len(active))

    scenes=motion_plan.get('scenes') or []
    micro=[s for s in scenes if bool((s.get('visual_sequence') or {}).get('micro_scene'))]
    exposure_bad=[s.get('scene_id') for s in micro if float((s.get('visual_sequence') or {}).get('minimum_perceived_exposure_seconds',s.get('duration_seconds',0)))<0.72]

    result={
        'schema':'HEXA_PERCEPTUAL_STORY_QA_V31','version':'1.0','video':str(p),'fps':fps,'frame_count':frame_count,'duration_seconds':duration_seconds,
        'streaming_memory_mode':True,'evaluation_resolution':[EVAL_W,EVAL_H],
        'meaningful_change_count':len(change_times),'meaningful_change_gap_mean_seconds':round(float(np.mean(gaps) if gaps else 0.0),4),'meaningful_change_gap_p90_seconds':round(float(np.percentile(gaps,90) if gaps else 0.0),4),'meaningful_change_gap_max_seconds':round(float(max(gaps) if gaps else 0.0),4),
        'white_wash_event_count':len(wash),'white_wash_times_seconds':[round(x,4) for x in wash],
        'severe_spike_count':len(severe),'severe_spikes_per_minute':round(len(severe)/duration_min,4),'severe_spike_times_seconds':[round(x,4) for x in severe],
        'active_frame_count':len(active),'localized_motion_ratio':round(local_ratio,4),'full_frame_motion_ratio':round(full_ratio,4),
        'micro_scene_count':len(micro),'micro_scene_exposure_failures':exposure_bad,
    }
    gates={
        'meaningful_state_cadence': result['meaningful_change_gap_p90_seconds']<=1.45,
        'white_wash_bounded': result['white_wash_event_count']<=max(1,int(math.ceil((result['duration_seconds']/60.0)*3.0))),
        'severe_spikes_bounded': result['severe_spikes_per_minute']<=3.0,
        'localized_motion_dominant': result['localized_motion_ratio']>=0.58,
        'full_frame_motion_bounded': result['full_frame_motion_ratio']<=0.18,
        'micro_scene_perceived_exposure': len(exposure_bad)==0,
    }
    result['gates']={k:{'pass':bool(v)} for k,v in gates.items()};result['pass']=all(gates.values())
    result['policy']='FINAL_MP4_PHYSICAL_EVIDENCE_OVERRIDES_PLAN_CLAIMS__STREAMING_LOW_MEMORY_SAFE'
    if out_json:write_json(out_json,result)
    return result


def evaluate_perceptual_story_from_metrics(metrics:dict, motion_plan:dict, out_json:str|os.PathLike|None=None)->dict:
    """Evaluate V31 perceptual gates from the already-decoded reference-metrics pass."""
    duration=float(metrics.get('duration_seconds',0.0));scenes=motion_plan.get('scenes') or []
    micro=[s for s in scenes if bool((s.get('visual_sequence') or {}).get('micro_scene'))]
    exposure_bad=[s.get('scene_id') for s in micro if float((s.get('visual_sequence') or {}).get('minimum_perceived_exposure_seconds',s.get('duration_seconds',0)))<0.72]
    result={
        'schema':'HEXA_PERCEPTUAL_STORY_QA_V31','version':'1.0','video':metrics.get('video'),'fps':metrics.get('fps'),'frame_count':metrics.get('frame_count'),'duration_seconds':duration,
        'shared_decode_with_reference_metrics':True,'streaming_memory_mode':True,
        'meaningful_change_count':int(metrics.get('meaningful_change_count',0)),
        'meaningful_change_gap_mean_seconds':float(metrics.get('meaningful_change_gap_mean_seconds',0.0)),
        'meaningful_change_gap_p90_seconds':float(metrics.get('meaningful_change_gap_p90_seconds',999.0)),
        'meaningful_change_gap_max_seconds':float(metrics.get('meaningful_change_gap_max_seconds',999.0)),
        'white_wash_event_count':int(metrics.get('white_wash_event_count',0)),'white_wash_times_seconds':list(metrics.get('white_wash_times_seconds') or []),
        'severe_spike_count':int(metrics.get('severe_isolated_motion_spikes',0)),'severe_spikes_per_minute':float(metrics.get('severe_isolated_motion_spikes_per_minute',999.0)),'severe_spike_times_seconds':list(metrics.get('severe_isolated_motion_spike_times_seconds') or []),
        'active_frame_count':int(metrics.get('active_frame_count',0)),'localized_motion_ratio':float(metrics.get('localized_motion_ratio',0.0)),'full_frame_motion_ratio':float(metrics.get('full_frame_motion_ratio',1.0)),
        'micro_scene_count':len(micro),'micro_scene_exposure_failures':exposure_bad,
    }
    gates={
        'meaningful_state_cadence':result['meaningful_change_gap_p90_seconds']<=1.45,
        'white_wash_bounded':result['white_wash_event_count']<=max(1,int(math.ceil((duration/60.0)*3.0))),
        'severe_spikes_bounded':result['severe_spikes_per_minute']<=3.0,
        'localized_motion_dominant':result['localized_motion_ratio']>=0.58,
        'full_frame_motion_bounded':result['full_frame_motion_ratio']<=0.18,
        'micro_scene_perceived_exposure':len(exposure_bad)==0,
    }
    result['gates']={k:{'pass':bool(v)} for k,v in gates.items()};result['pass']=all(gates.values());result['policy']='FINAL_MP4_PHYSICAL_EVIDENCE_OVERRIDES_PLAN_CLAIMS__SHARED_SINGLE_DECODE'
    if out_json:write_json(out_json,result)
    return result
