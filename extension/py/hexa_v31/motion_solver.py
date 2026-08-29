from __future__ import annotations
import math


def clamp01(x:float)->float:return max(0.0,min(1.0,float(x)))


def s_curve7(t:float)->float:
    """Seventh-order S-curve with zero velocity, acceleration and jerk at endpoints."""
    t=clamp01(t)
    return 35*t**4-84*t**5+70*t**6-20*t**7


def min_jerk5(t:float)->float:
    t=clamp01(t)
    return 10*t**3-15*t**4+6*t**5


def bell_c2(t:float)->float:
    # C2-ish symmetric emphasis envelope. Zero value and slope at both ends.
    t=clamp01(t)
    s=min_jerk5(t*2.0) if t<=0.5 else min_jerk5((1.0-t)*2.0)
    return s


def schedule_around_hit(hit:float,duration:float,scene_start:float,scene_end:float,fps:float=30.0,hit_fraction:float=0.68)->tuple[float,float,float]:
    """Schedule movement so most travel happens before the spoken perceptual hit.

    V28 started at the trigger. V31 starts before it and softly settles after it,
    which matches professional motion practice and materially improves AV sync.
    """
    minimum=12.0/max(1.0,fps);duration=max(minimum,float(duration))
    # The semantic hit is intentionally late in the approved preset: the
    # visual has completed nearly all travel when the voice names it.
    hit_fraction=max(0.62,min(0.92,float(hit_fraction)))
    start=float(hit)-duration*hit_fraction;end=start+duration
    if start<scene_start:
        end+=scene_start-start;start=scene_start
    if end>scene_end:
        start-=end-scene_end;end=scene_end
    start=max(scene_start,start);end=min(scene_end,end)
    if end-start<minimum:
        end=min(scene_end,start+minimum)
        if end-start<minimum:start=max(scene_start,end-minimum)
    actual_hit=max(start,min(end,float(hit)))
    return start,actual_hit,end


def position_progress(t:float,start:float,end:float,profile:str='JERK_LIMITED_S7')->float:
    if end<=start:return 1.0
    q=(float(t)-float(start))/(float(end)-float(start))
    return s_curve7(q) if str(profile).upper().startswith('JERK') else min_jerk5(q)


def camera_motion_gain(camera_scale:float)->float:
    """Compensate motion amplitude after uniform reference camera fit.

    V31 P1 correctly reduced composition occupancy but then multiplied relative travel by
    the same camera scale, making choreography timid.  A full-canvas layer may move
    independently of its uniform visual scale, so restore roughly source-scale screen
    travel (plus a small 6% reference-energy margin) while bounding the gain.
    """
    cs=max(0.70,min(1.0,float(camera_scale)))
    return max(1.0,min(1.40,1.06/cs))
