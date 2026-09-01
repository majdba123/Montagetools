from __future__ import annotations
import math


def compute_reference_camera_fit(foreground_fraction:float,units:list[dict],profile:dict)->dict:
    """Uniform camera fit that preserves all relative Worker geometry.

    This is not per-object recomposition. Every full-canvas semantic layer uses the
    same scale around sequence center, preserving layout while matching the locked
    reference's negative-space grammar.
    """
    occ=max(0.01,float(foreground_fraction)*100.0)
    slots={str(u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id')) for u in units}
    char=any(str(u.get('semantic_type') or '').upper() in {'MAIN_CHARACTER','SECONDARY_CHARACTER'} for u in units)
    target=25.5
    if len(slots)>=4:target=28.5
    elif len(slots)==3:target=27.5
    elif len(slots)==2:target=26.5
    if char:target=max(target,27.5)
    q=(profile.get('quality_floor') or {}).get('nonwhite_occupancy_median_percent') or {}
    target=min(float(q.get('target_max',29.0)),max(float(q.get('preferred_min',22.0)),target))
    preferred_min=float(q.get('preferred_min',22.0))
    target_max=float(q.get('target_max',29.0))
    raw_scale=math.sqrt(target/max(occ,1e-6))
    if occ<preferred_min-0.5:
        # Sparse source states may scale up, but only within the same certified
        # safe-frame envelope already enforced by the composition solver.
        scale=max(1.0,min(1.15,raw_scale));reason='UNIFORM_REFERENCE_CAMERA_EXPAND'
    elif occ<=target_max+0.5:
        scale=1.0;reason='SOURCE_ALREADY_REFERENCE_SPACED'
    else:
        scale=max(0.76,min(0.985,raw_scale));reason='UNIFORM_REFERENCE_CAMERA_FIT'
    expected=occ*scale*scale
    return {'camera_scale':round(scale,6),'source_occupancy_percent':round(occ,4),'target_occupancy_percent':round(target,4),'expected_occupancy_percent':round(expected,4),'composition_slot_count':len(slots),'character_present':char,'geometry_policy':'UNIFORM_CENTERED_SCALE_ONLY__RELATIVE_LAYOUT_PRESERVED','reason':reason}
