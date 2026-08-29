from __future__ import annotations
import os, pathlib, statistics
from typing import Any
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from .util import write_json

# This evaluator intentionally mirrors the lightweight development scorer family
# used by prior HEXA builders. It is calibrated against the two physical reference
# videos bundled in the validation authority, not against arbitrary web material.
EVAL_W=426
EVAL_H=240
LOW_MOTION_THRESHOLD=0.0013
NONWHITE_CHANNEL_THRESHOLD=248
UNDERFILLED_PERCENT=15.0
HIGH_MOTION_THRESHOLD=0.016  # doubled-luma scale, calibrated to the two physical reference videos


def _finish_run(runs:list[float], frames:int, fps:float):
    if frames>0: runs.append(frames/max(1e-6,fps))


def _detect_white_wash_events(occupancy:list[float], ink_energy:list[float], mean_luma:list[float], fps:float)->list[float]:
    """Detect both true white frames and V28-style ghost-to-white dissolves.

    The old detector only saw occupancy <=5%, so a pale silhouette could evade QA.
    V31 also detects a short high-luma contrast/ink trough that is surrounded by
    materially stronger visual content on both sides.
    """
    if not occupancy:return []
    look=max(3,int(round(float(fps)*0.24)));out=[]
    n=min(len(occupancy),len(ink_energy),len(mean_luma))
    for i in range(look,n-look):
        pre_occ=max(occupancy[i-look:i]);post_occ=max(occupancy[i+1:i+1+look])
        pure=occupancy[i]<=5.0 and pre_occ>=14.0 and post_occ>=14.0
        pre_ink=max(ink_energy[i-look:i]);post_ink=max(ink_energy[i+1:i+1+look]);baseline=min(pre_ink,post_ink)
        ghost=(baseline>=7.0 and ink_energy[i]<=min(8.0,baseline*0.48) and mean_luma[i]>=233.0 and pre_occ>=14.0 and post_occ>=10.0)
        if pure or ghost:
            t=i/max(1e-6,float(fps))
            if not out or t-out[-1]>0.45:out.append(t)
    return out


def analyze_video(video_path:str|os.PathLike, out_json:str|os.PathLike|None=None) -> dict[str,Any]:
    p=pathlib.Path(video_path)
    cap=cv2.VideoCapture(str(p))
    if not cap.isOpened(): raise RuntimeError(f'Cannot open video for reference metrics: {p}')
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count=0; prev=None; motion=[]; occupancy=[]; ink_energy=[]; mean_luma=[]; changed=[]; meaningful_change_times=[]; sample_gray=None; sample_index=0; sample_step=max(1,int(round(fps*0.20)))
    while True:
        ok,fr=cap.read()
        if not ok: break
        fr=cv2.resize(fr,(EVAL_W,EVAL_H),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(fr,cv2.COLOR_BGR2GRAY)
        mn=np.min(fr,axis=2)
        occupancy.append(float(np.mean(mn < NONWHITE_CHANNEL_THRESHOLD)*100.0)); ink_energy.append(float(np.mean((255.0-gray.astype(np.float32))/255.0)*100.0)); mean_luma.append(float(np.mean(gray)))
        if prev is not None:
            d=cv2.absdiff(gray,prev)
            # Historical HEXA proxy scorer used an approximately doubled normalized
            # luma frame-difference scale; keeping this form preserves continuity with
            # the development validation reports while recomputing from physical video.
            ma=float(np.mean(d))/255.0*2.0
            motion.append(ma)
            changed.append(float(np.mean(d>=7))*100.0)
        if sample_gray is None:
            sample_gray=gray.copy();sample_index=frame_count
        elif frame_count-sample_index>=sample_step:
            sd=cv2.absdiff(sample_gray,gray);smd=float(np.mean(sd));scp=float(np.mean(sd>=5)*100.0)
            if smd>=0.85 or scp>=1.15:meaningful_change_times.append(frame_count/fps)
            sample_gray=gray.copy();sample_index=frame_count
        prev=gray; frame_count+=1
    cap.release()
    if frame_count<2: raise RuntimeError('Video too short for reference metrics')
    arr=np.asarray(motion,dtype=np.float64)
    low=arr < LOW_MOTION_THRESHOLD
    runs=[]; n=0
    for flag in low:
        if flag: n+=1
        else:
            _finish_run(runs,n,fps); n=0
    _finish_run(runs,n,fps)
    under=np.asarray(occupancy)<UNDERFILLED_PERCENT
    uruns=[];n=0
    for flag in under:
        if flag:n+=1
        else:
            _finish_run(uruns,n,fps);n=0
    _finish_run(uruns,n,fps)
    high=arr >= HIGH_MOTION_THRESHOLD
    high_runs_frames=[];n=0
    for flag in high:
        if flag:n+=1
        else:
            if n>0: high_runs_frames.append(n)
            n=0
    if n>0: high_runs_frames.append(n)
    single_ratio=(sum(1 for x in high_runs_frames if x<=1)/len(high_runs_frames)) if high_runs_frames else 0.0
    severe_spikes=0; severe_spike_times=[]
    for i in range(1,len(arr)-1):
        if arr[i]>=0.08 and arr[i] > 1.8*max(arr[i-1],arr[i+1],1e-9):
            severe_spikes+=1; severe_spike_times.append(round((i+1)/max(1e-6,fps),6))
    duration_min=max(1e-6,(len(arr)/fps)/60.0)
    # V31 physical perceptual evidence is derived during this same decode pass so low-memory
    # workstations do not decode the 99s final MP4 twice.
    meaningful_gaps=[];last_t=0.0
    for t in meaningful_change_times:meaningful_gaps.append(t-last_t);last_t=t
    meaningful_gaps.append(frame_count/fps-last_t)
    wash=_detect_white_wash_events(occupancy,ink_energy,mean_luma,fps)
    active=[j for j,x in enumerate(changed) if x>=0.10]
    localized_motion_ratio=sum(1 for j in active if 0.10<=changed[j]<=24.0)/max(1,len(active))
    full_frame_motion_ratio=sum(1 for j in active if changed[j]>=45.0)/max(1,len(active))
    result={
        'schema':'HEXA_REFERENCE_METRICS_V31','metric_version':'V31_PHYSICAL_REFERENCE_PROXY_2.0',
        'video':str(p),'fps':fps,'frame_count':frame_count,'duration_seconds':frame_count/fps,
        'motion_activity':round(float(arr.mean()),9),
        'motion_p95':round(float(np.percentile(arr,95)),9),
        'motion_p99':round(float(np.percentile(arr,99)),9),
        'severe_isolated_motion_spikes':int(severe_spikes),
        'severe_isolated_motion_spike_times_seconds':severe_spike_times,
        'severe_isolated_motion_spikes_per_minute':round(float(severe_spikes/duration_min),6),
        'low_motion_percent':round(float(low.mean()*100.0),4),
        'changed_pixels_percent':round(float(np.mean(changed)),4) if changed else 0.0,
        'median_nonwhite_occupancy_percent':round(float(np.median(occupancy)),4),
        'underfilled_frame_ratio_lt15pct':round(float(under.mean()),6),
        'underfilled_frame_percent_lt15pct':round(float(under.mean()*100.0),4),
        'longest_underfilled_run_seconds':round(float(max(uruns) if uruns else 0.0),4),
        'average_static_hold_seconds':round(float(np.mean(runs) if runs else 0.0),4),
        'p90_static_hold_seconds':round(float(np.percentile(runs,90) if runs else 0.0),4),
        'max_static_hold_seconds':round(float(max(runs) if runs else 0.0),4),
        'static_run_count':len(runs),
        'static_run_seconds': [round(float(x),4) for x in runs],
        'high_motion_burst_count':len(high_runs_frames),
        'high_motion_burst_median_frames':round(float(np.median(high_runs_frames) if high_runs_frames else 0.0),4),
        'high_motion_burst_p75_frames':round(float(np.percentile(high_runs_frames,75) if high_runs_frames else 0.0),4),
        'single_frame_high_motion_burst_ratio':round(float(single_ratio),6),
        'single_frame_high_motion_burst_percent':round(float(single_ratio*100.0),4),
        'meaningful_change_count':len(meaningful_change_times),
        'meaningful_change_gap_mean_seconds':round(float(np.mean(meaningful_gaps) if meaningful_gaps else 0.0),4),
        'meaningful_change_gap_p90_seconds':round(float(np.percentile(meaningful_gaps,90) if meaningful_gaps else 0.0),4),
        'meaningful_change_gap_max_seconds':round(float(max(meaningful_gaps) if meaningful_gaps else 0.0),4),
        'white_wash_event_count':len(wash),'white_wash_times_seconds':[round(float(x),4) for x in wash],'white_wash_detection_version':'V31_GHOST_TROUGH_2.0','median_ink_energy_percent':round(float(np.median(ink_energy)),4),'median_mean_luma':round(float(np.median(mean_luma)),4),
        'localized_motion_ratio':round(float(localized_motion_ratio),4),'full_frame_motion_ratio':round(float(full_frame_motion_ratio),4),'active_frame_count':len(active),
        'thresholds':{'low_motion':LOW_MOTION_THRESHOLD,'high_motion':HIGH_MOTION_THRESHOLD,'nonwhite_channel':NONWHITE_CHANNEL_THRESHOLD,'underfilled_percent':UNDERFILLED_PERCENT},
    }
    if out_json: write_json(out_json,result)
    return result


def score_against_reference_floor(metrics:dict, profile:dict) -> dict:
    floor=profile.get('quality_floor') or {}
    gates={}
    def gate(name,ok,actual,target): gates[name]={'pass':bool(ok),'actual':actual,'target':target}
    mm=float(metrics['motion_activity']); mmr=floor.get('motion_mean') or {'target_min':0.020,'target_max':0.025}
    # Hard reference floor: the proxy must physically land inside the locked reference band.
    gate('motion_activity_in_reference_band', mm>=float(mmr['target_min']) and mm<=float(mmr['target_max']), mm, mmr)
    lm=float(metrics['low_motion_percent']); lmr=floor.get('low_motion_percent') or {'target_max':48.0}
    gate('low_motion_time_within_limit', lm<=float(lmr['target_max']),lm,lmr)
    oc=float(metrics['median_nonwhite_occupancy_percent']); ocr=floor.get('nonwhite_occupancy_median_percent') or {'target_min':20.0,'target_max':29.0}
    gate('occupancy_in_reference_band',oc>=float(ocr['target_min']) and oc<=float(ocr['target_max']),oc,ocr)
    av=float(metrics['average_static_hold_seconds']); avr=floor.get('static_run_mean_seconds') or {'target_max':0.65}
    gate('average_static_hold_within_limit',av<=float(avr['target_max']),av,avr)
    p90=float(metrics['p90_static_hold_seconds']); p90r=floor.get('static_run_p90_seconds') or {'target_max':1.35}
    gate('p90_static_hold_within_limit',p90<=float(p90r['target_max']),p90,p90r)
    mx=float(metrics['max_static_hold_seconds']); mxr=floor.get('static_run_max_seconds') or {'target_max':2.5}
    gate('max_static_hold_within_limit',mx<=float(mxr['target_max']),mx,mxr)
    under=float(metrics.get('underfilled_frame_percent_lt15pct',0.0))
    # Physical references are around the mid-teens under this scorer; allow <=20% as a hard floor.
    gate('underfilled_screen_time_bounded',under<=20.0,under,{'target_max':20.0})
    p95=float(metrics.get('motion_p95',0.0)); p95r=floor.get('motion_p95') or {'target_min':0.075,'target_max':0.12}
    p95_min=float(p95r.get('target_min',0.075));p95_max=float(p95r.get('target_max',0.12))
    gate('motion_peak_energy_in_reference_band',p95>=p95_min and p95<=p95_max,p95,p95r)
    severe=float(metrics.get('severe_isolated_motion_spikes_per_minute',999.0)); sr=floor.get('severe_isolated_motion_spikes_per_minute') or {'target_max':3.0}
    gate('severe_one_frame_motion_spikes_bounded',severe<=float(sr['target_max']),severe,sr)
    wash_count=int(metrics.get('white_wash_event_count',999)); wash_max=max(1,int(np.ceil((float(metrics.get('duration_seconds',0.0))/60.0)*3.0)))
    gate('white_wash_events_bounded',wash_count<=wash_max,wash_count,{'target_max':wash_max,'detector':'V31_GHOST_TROUGH_2.0'})
    passed=sum(1 for g in gates.values() if g['pass']); total=max(1,len(gates));score=100.0*passed/total
    hard=all(g['pass'] for g in gates.values())
    return {'pass':hard,'reference_fidelity_proxy_score_percent':round(score,2),'gates':gates,
            'note':'Automated motion/cadence proxy calibrated to physical references. It cannot replace physical Premiere render + human visual comparison.'}
