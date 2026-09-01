from __future__ import annotations
import math
import cv2
import numpy as np


def _bbox_overlap(a,b)->float:
    ax,ay,aw,ah=map(float,a); bx,by,bw,bh=map(float,b)
    ix=max(0.0,min(ax+aw,bx+bw)-max(ax,bx)); iy=max(0.0,min(ay+ah,by+bh)-max(ay,by))
    inter=ix*iy
    return inter/max(1e-9,min(aw*ah,bw*bh))


def _mask_contact(a:np.ndarray,b:np.ndarray)->tuple[float,float]:
    aa=(a>8).astype(np.uint8); bb=(b>8).astype(np.uint8)
    if not np.any(aa) or not np.any(bb):return 0.0,0.0
    k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    da=cv2.dilate(aa,k,iterations=1); db=cv2.dilate(bb,k,iterations=1)
    touch=int(np.count_nonzero((da>0)&(db>0)))
    overlap=int(np.count_nonzero((aa>0)&(bb>0)))
    denom=max(1,min(int(np.count_nonzero(aa)),int(np.count_nonzero(bb))))
    return touch/float(denom),overlap/float(denom)


def build_occlusion_graph(units:list[dict], alpha_by_id:dict[str,np.ndarray])->dict:
    """Build conservative physical relationship graph for animation safety.

    A flat scene cannot reveal truly hidden pixels. V31 therefore treats any
    same-object embedding, physical touch, or uncertain overlap as an occlusion
    constraint. Translation is permitted only for detached, matte-clean layers
    with no risky neighbor; reveal/scale/opacity acting remains legal otherwise.
    """
    nodes=[];edges=[];risk_by={str(u.get('physical_id')):0.0 for u in units}
    for u in units:
        pid=str(u.get('physical_id'))
        nodes.append({'physical_id':pid,'composition_slot_id':u.get('composition_slot_id'),'hierarchy_level':int(u.get('hierarchy_level') or 0),'animation_mode':u.get('animation_mode'),'semantic_type':u.get('semantic_type'),'semantic_role':u.get('semantic_role')})
    for i,a in enumerate(units):
        for b in units[i+1:]:
            aid=str(a.get('physical_id'));bid=str(b.get('physical_id'))
            same_slot=str(a.get('composition_slot_id'))==str(b.get('composition_slot_id'))
            bo=_bbox_overlap(a.get('bbox_norm') or [0,0,0,0],b.get('bbox_norm') or [0,0,0,0])
            touch,overlap=_mask_contact(alpha_by_id.get(aid,np.zeros((1,1),np.uint8)),alpha_by_id.get(bid,np.zeros((1,1),np.uint8)))
            if same_slot and (bo>0.02 or touch>0.002):kind='INTERNAL_OCCLUSION_OR_EMBEDDED';risk=0.95
            elif overlap>0.002:kind='PIXEL_OVERLAP';risk=0.92
            elif touch>0.018:kind='PHYSICAL_TOUCH';risk=0.78
            elif bo>0.22:kind='PROJECTED_BBOX_OVERLAP';risk=0.62
            else:kind='SEPARATE';risk=0.08
            risk_by[aid]=max(risk_by[aid],risk);risk_by[bid]=max(risk_by[bid],risk)
            edges.append({'a':aid,'b':bid,'relationship':kind,'same_composition_slot':same_slot,'bbox_overlap_ratio':round(bo,6),'mask_touch_ratio':round(touch,6),'mask_overlap_ratio':round(overlap,6),'reveal_risk':round(risk,4),'z_order':'UNKNOWN_FLAT_SOURCE' if risk>=0.6 else 'NOT_REQUIRED'})
    safe=[];blocked=[]
    for u in units:
        pid=str(u.get('physical_id'));r=float(risk_by.get(pid,0.0));base_safe=bool(u.get('animation_safe')) and str(u.get('animation_mode') or '')=='TRANSLATE_SAFE'
        matte=float((u.get('matting') or {}).get('edge_halo_risk',0.0))
        allowed=bool(base_safe and r<0.55 and matte<0.32)
        u['occlusion_reveal_risk']=round(r,4)
        u['translation_safe_after_occlusion']=allowed
        if not allowed and str(u.get('animation_mode') or '')=='TRANSLATE_SAFE':u['animation_mode']='IN_PLACE_ACTING_ONLY'
        (safe if allowed else blocked).append(pid)
    return {'schema':'HEXA_OCCLUSION_SAFETY_GRAPH_V31','version':'1.0','nodes':nodes,'edges':edges,'translation_safe_nodes':safe,'translation_blocked_nodes':blocked,'unknown_z_order_edges':sum(1 for e in edges if e['z_order']=='UNKNOWN_FLAT_SOURCE'),'policy':'NO_TRANSLATION_THAT_CAN_REVEAL_UNSEEN_PIXELS'}
