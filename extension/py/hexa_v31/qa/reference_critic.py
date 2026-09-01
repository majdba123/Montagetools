from __future__ import annotations
from hexa_v31.util import write_json


def _band(v,lo,hi,soft=0.35):
    v=float(v);lo=float(lo);hi=float(hi)
    if lo<=v<=hi:return 1.0
    span=max(1e-9,hi-lo)
    d=(lo-v)/span if v<lo else (v-hi)/span
    return max(0.0,1.0-d/max(1e-6,soft))


def _max(v,target,soft_ratio=0.55):
    v=float(v);target=float(target)
    if v<=target:return 1.0
    return max(0.0,1.0-(v-target)/max(1e-9,target*soft_ratio))


def _min(v,target,soft_ratio=0.55):
    v=float(v);target=float(target)
    if v>=target:return 1.0
    return max(0.0,1.0-(target-v)/max(1e-9,target*soft_ratio))


def score_reference_10(metrics:dict,profile:dict,perceptual:dict|None=None,physical_acting:dict|None=None,out_json=None)->dict:
    f=profile.get('quality_floor') or {}
    mm=f.get('motion_mean') or {'target_min':.02,'target_max':.025}; occ=f.get('nonwhite_occupancy_median_percent') or {'target_min':20,'target_max':29}
    parts={
        'motion_activity':_band(metrics.get('motion_activity',0),mm['target_min'],mm['target_max']),
        'low_motion':_max(metrics.get('low_motion_percent',100),(f.get('low_motion_percent') or {'target_max':48})['target_max']),
        'static_p90':_max(metrics.get('p90_static_hold_seconds',99),(f.get('static_run_p90_seconds') or {'target_max':1.35})['target_max']),
        'static_max':_max(metrics.get('max_static_hold_seconds',99),(f.get('static_run_max_seconds') or {'target_max':2.5})['target_max']),
        'occupancy':_band(metrics.get('median_nonwhite_occupancy_percent',0),occ['target_min'],occ['target_max']),
        'motion_peaks':_band(metrics.get('motion_p95',0),(f.get('motion_p95') or {'target_min':.075,'target_max':.12}).get('target_min',.075),(f.get('motion_p95') or {'target_min':.075,'target_max':.12}).get('target_max',.12)),
        'spikes':_max(metrics.get('severe_isolated_motion_spikes_per_minute',99),(f.get('severe_isolated_motion_spikes_per_minute') or {'target_max':3})['target_max']),
        'localized_motion':_min(metrics.get('localized_motion_ratio',0),0.58),
        'full_frame_motion':_max(metrics.get('full_frame_motion_ratio',1),0.18),
        'meaningful_cadence':_max(metrics.get('meaningful_change_gap_p90_seconds',99),1.45),
        'white_wash':_max(int(metrics.get('white_wash_event_count',99)),max(1,int((float(metrics.get('duration_seconds',0))/60.0)*3.0+0.999))),
    }
    if physical_acting is not None:
        # Never award a free perfect component when no physical relationship action was planned.
        # V31 earns this score only from actions that were actually scheduled and observed in pixels.
        planned=int(physical_acting.get('planned_physical_actions',0))
        if planned>0:
            ratio=float(physical_acting.get('verified_ratio',0.0));parts['physical_acting_survival']=ratio
    weights={'motion_activity':1.2,'low_motion':1.0,'static_p90':1.0,'static_max':.55,'occupancy':1.1,'motion_peaks':.55,'spikes':.85,'localized_motion':.75,'full_frame_motion':.6,'meaningful_cadence':1.0,'white_wash':.9,'physical_acting_survival':1.0}
    den=sum(weights.get(k,1.0) for k in parts);score=10.0*sum(parts[k]*weights.get(k,1.0) for k in parts)/max(1e-9,den)
    result={'schema':'HEXA_REFERENCE_ONLY_PERCEPTUAL_SCORE_V31','version':'1.2-V31','score_10':round(score,3),'target_10':8.0,'pass_8_plus':score>=8.0,'components':{k:round(v*10.0,3) for k,v in parts.items()},'authority':'LOCKED_PHYSICAL_REFERENCE_PROFILE_ONLY__NO_PREVIOUS_VERSION_COMPARISON'}
    if out_json:write_json(out_json,result)
    return result
