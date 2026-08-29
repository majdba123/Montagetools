from __future__ import annotations
import json, math, pathlib
from functools import lru_cache

_RESOURCE = pathlib.Path(__file__).resolve().parents[2] / 'resources' / 'HEXA_USER_PRESET_AUTHORITY_V31.json'

@lru_cache(maxsize=1)
def authority() -> dict:
    return json.loads(_RESOURCE.read_text(encoding='utf-8'))

def preset(name:str) -> dict:
    p=(authority().get('preset_motion') or {}).get(str(name))
    if not p:
        raise KeyError(f'Unknown HEXA V31 preset: {name}')
    return p

def _interp_rows(rows, t:float)->float:
    if not rows:return 1.0
    q=max(0.0,min(1.0,float(t)))
    rr=[(float(a),float(b)) for a,b in rows]
    if q<=rr[0][0]:return rr[0][1]
    if q>=rr[-1][0]:return rr[-1][1]
    for (t0,v0),(t1,v1) in zip(rr,rr[1:]):
        if t0<=q<=t1:
            f=(q-t0)/max(1e-9,t1-t0)
            return v0+(v1-v0)*f
    return rr[-1][1]

def progress(name:str,t:float)->float:
    p=preset(name); curve=p.get('curve')
    if not curve:
        return max(0.0,min(1.0,float(t)))
    q=max(0.0,min(1.0,float(t))); x=q*(len(curve)-1); i=int(math.floor(x)); f=x-i
    if i>=len(curve)-1:return float(curve[-1])
    return float(curve[i])*(1.0-f)+float(curve[i+1])*f

def scale(name:str,t:float)->float:
    return _interp_rows(preset(name).get('scale_keyframes') or [[0,1],[1,1]],t)

def opacity(name:str,t:float)->float:
    return _interp_rows(preset(name).get('opacity_keyframes') or [[0,1],[1,1]],t)

def duration(name:str)->float:
    return float(preset(name).get('duration_seconds') or 0.8)

def preset_delta(name:str)->tuple[float,float]:
    p=preset(name)
    if 'position_delta_norm' in p:
        d=p['position_delta_norm'];return float(d[0]),float(d[1])
    a=p.get('start_norm'); b=p.get('end_norm')
    if a and b:return float(b[0])-float(a[0]),float(b[1])-float(a[1])
    return 0.0,0.0

def is_primary_semantic(unit:dict)->bool:
    typ=str(unit.get('semantic_type') or unit.get('type') or '').upper()
    role=str(unit.get('semantic_role') or unit.get('role') or '').upper()
    if typ in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}:return True
    return role=='PRIMARY'

def choose_entry_for_center(cx:float)->str:
    return 'ENTRY_LEFT_TO_MIDDLE' if float(cx)<=0.5 else 'ENTRY_RIGHT_TO_MIDDLE'

def choose_exit_for_center(cx:float)->str:
    # exit away from the visual center, matching the user's two legal exit presets
    return 'EXIT_MIDDLE_TO_LEFT' if float(cx)<=0.5 else 'EXIT_MIDDLE_TO_RIGHT'

def choose_within_toward(src:tuple[float,float], dst:tuple[float,float])->str:
    sx,sy=map(float,src);dx,dy=float(dst[0])-sx,float(dst[1])-sy
    if abs(dx)>=abs(dy):
        if dx>0.04:return 'WITHIN_MIDDLE_TO_RIGHT'
        if dx<-0.04:return 'WITHIN_MIDDLE_TO_LEFT'
        return 'WITHIN_LEFT_TO_MIDDLE' if sx<0.5 else 'WITHIN_RIGHT_TO_MIDDLE'
    if dy>0.04:return 'WITHIN_MIDDLE_TO_DOWN'
    if dy<-0.04:return 'WITHIN_MIDDLE_TO_UP'
    return 'WITHIN_LEFT_TO_MIDDLE' if sx<0.5 else 'WITHIN_RIGHT_TO_MIDDLE'
