from __future__ import annotations
"""Compatibility facade for V31.0.1.

Production choreography is owned by ``preset_authority`` and the user's uploaded Premiere
preset family.  This module remains import-compatible for legacy helpers but is no longer a
motion-design authority.
"""
from hexa_v31.preset_authority import authority as _authority

MOTION_DNA_ID='HEXA_MOTION_VOCABULARY_V31_0_1_USER_PRESET_AUTHORITY__LEGACY_ADAPTER_ONLY'
VOCABULARY={
    'POSITION_ENTRY':{'duration_min':1.16,'duration_max':1.44,'minimum_frames':12,'interpolation':'USER_PRFPSET_CURVE'},
    'POSITION_TRANSFER':{'duration_min':0.90,'duration_max':1.28,'minimum_frames':12,'interpolation':'USER_PRFPSET_CURVE'},
    'SCALE_POP':{'duration_min':0.80,'duration_max':0.80,'interpolation':'USER_APPEARANCE_PRESET'},
    'OPACITY_FADE_OUT':{'duration_min':0.60,'duration_max':0.60,'interpolation':'USER_DISAPPEARANCE_PRESET'},
}

def clamp_duration(name:str,requested:float,fps:float=30.0)->float:
    row=VOCABULARY.get(name) or {};lo=float(row.get('duration_min',requested));hi=float(row.get('duration_max',requested))
    if row.get('minimum_frames'):lo=max(lo,float(row['minimum_frames'])/max(1.0,fps))
    return max(lo,min(hi,float(requested)))
