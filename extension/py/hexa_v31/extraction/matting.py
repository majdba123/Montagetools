from __future__ import annotations
import math
import cv2
import numpy as np


def _smoothstep01(x:np.ndarray)->np.ndarray:
    x=np.clip(x,0.0,1.0)
    return x*x*(3.0-2.0*x)


def _signed_distance(mask:np.ndarray)->np.ndarray:
    b=(mask>0).astype(np.uint8)
    inside=cv2.distanceTransform(b,cv2.DIST_L2,5)
    outside=cv2.distanceTransform(1-b,cv2.DIST_L2,5)
    return inside-outside


def _color_distance(rgb:np.ndarray,bg_rgb:tuple[int,int,int])->np.ndarray:
    bg=np.asarray(bg_rgb,dtype=np.float32).reshape(1,1,3)
    x=rgb.astype(np.float32)
    # RGB max distance is deliberately paired with Lab chroma/luma distance. The
    # max channel distance preserves dark outlines; Lab prevents pale colored
    # antialiasing from being mistaken for the white stage.
    d_rgb=np.max(np.abs(x-bg),axis=2)
    lab=cv2.cvtColor(rgb,cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_img=np.zeros((1,1,3),dtype=np.uint8); bg_img[0,0]=np.asarray(bg_rgb,dtype=np.uint8)
    bg_lab=cv2.cvtColor(bg_img,cv2.COLOR_RGB2LAB).astype(np.float32)[0,0]
    d_lab=np.sqrt(np.sum((lab-bg_lab.reshape(1,1,3))**2,axis=2))
    return np.maximum(d_rgb,d_lab*0.62)


def _soft_group_gate(group_mask:np.ndarray, feather_px:float)->np.ndarray:
    signed=_signed_distance(group_mask)
    # 0 outside beyond feather, 1 safely inside; smooth transition across the
    # group boundary. This makes independently rendered layers anti-aliased even
    # when the semantic partition itself is binary.
    t=(signed+float(feather_px))/(2.0*float(feather_px))
    return _smoothstep01(t)




def _local_stage_leak_mask(rgb:np.ndarray, group_mask:np.ndarray, bg_rgb:tuple[int,int,int])->tuple[np.ndarray,np.ndarray]:
    """Find white-stage pixels that leaked into a top-level object group.

    The global scene mask intentionally preserves enclosed white artwork.  That is safe
    for faces/cards, but a grouped bbox can also trap a large pocket of the white stage
    behind a connector or merged silhouette.  If that pocket is left opaque, Premiere
    renders a visible rectangular/white slab when the layer moves over another object.

    V31 solves this *locally*: only near-background pixels connected to the local group
    crop border are candidates for removal.  Enclosed white object interiors are not
    border-connected and therefore survive.  Strong ink/edge neighborhoods receive a
    soft color-derived cap instead of a hard cut, preserving antialiasing.
    """
    gm=(group_mask>0)
    yy,xx=np.where(gm)
    empty=np.zeros(group_mask.shape,dtype=bool)
    if len(xx)==0:
        return empty,empty
    h,w=group_mask.shape
    pad=max(3,int(round(min(h,w)*0.003)))
    x0=max(0,int(xx.min())-pad);x1=min(w,int(xx.max())+1+pad)
    y0=max(0,int(yy.min())-pad);y1=min(h,int(yy.max())+1+pad)
    roi=rgb[y0:y1,x0:x1]
    gmr=gm[y0:y1,x0:x1]
    bg=np.asarray(bg_rgb,dtype=np.int16).reshape(1,1,3)
    diff=np.max(np.abs(roi.astype(np.int16)-bg),axis=2)
    hsv=cv2.cvtColor(roi,cv2.COLOR_RGB2HSV);sat=hsv[:,:,1]
    gray=cv2.cvtColor(roi,cv2.COLOR_RGB2GRAY)
    # Broad connectivity identifies the physical stage; core is near-canonical white.
    broad=((diff<=20)&(sat<=34)&(gray>=218)).astype(np.uint8)
    broad=cv2.morphologyEx(broad,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
    n,labels,_,_=cv2.connectedComponentsWithStats(broad,8)
    labs=set()
    if n>1:
        border=np.concatenate([labels[0,:],labels[-1,:],labels[:,0],labels[:,-1]])
        labs={int(v) for v in np.unique(border) if int(v)!=0}
    connected=np.isin(labels,list(labs)) if labs else np.zeros_like(broad,dtype=bool)
    connected &= gmr
    core=connected&(diff<=7)&(sat<=16)&(gray>=242)
    # Edge-adjacent near-white pixels can be legitimate antialiasing.  Mark them as a
    # soft zone so refine_alpha caps them by color evidence instead of erasing them.
    strong=((diff>=12)|(sat>=28)|(gray<=236)).astype(np.uint8)*255
    near_strong=cv2.dilate(strong,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)),iterations=1)>0
    hard_local=connected & (~near_strong)
    # Canonical-white stage is never valid opaque foreground even right beside ink.
    hard_local |= core & (diff<=3)
    soft_local=connected & (~hard_local)
    hard=np.zeros(group_mask.shape,dtype=bool);soft=np.zeros_like(hard)
    hard[y0:y1,x0:x1]=hard_local;soft[y0:y1,x0:x1]=soft_local
    return hard,soft

def refine_alpha(
    rgb:np.ndarray,
    hard_mask:np.ndarray,
    bg_rgb:tuple[int,int,int],
    *,
    native_alpha:np.ndarray|None=None,
    group_mask:np.ndarray|None=None,
    feather_px:float|None=None,
)->tuple[np.ndarray,np.ndarray,dict]:
    """Return edge-refined alpha, decontaminated RGB, and measurable matte QA.

    The scene family is deliberately white/near-white and illustration-heavy.
    V31 therefore uses a deterministic trimap/matting solver rather than a
    project-specific ML model: native alpha wins when present; otherwise a hard
    semantic silhouette supplies certain foreground and a color-aware signed
    distance band reconstructs anti-aliased edges. White-fringe decontamination
    solves the observed source color against the estimated white stage.
    """
    h,w=hard_mask.shape
    feather=float(feather_px or max(1.0,min(2.6,min(h,w)*0.0018)))
    hard=(hard_mask>0).astype(np.uint8)*255
    if native_alpha is not None:
        base=np.asarray(native_alpha,dtype=np.float32)/255.0
        source='NATIVE_ALPHA_REFINED'
    else:
        signed=_signed_distance(hard)
        geom=_smoothstep01((signed+feather)/(2.0*feather))
        cd=_color_distance(rgb,bg_rgb)
        # Soft color evidence is only authoritative in the edge band. Enclosed
        # white interiors remain opaque because the hard silhouette is semantic truth.
        color=_smoothstep01((cd-1.5)/18.0)
        interior=cv2.distanceTransform((hard>0).astype(np.uint8),cv2.DIST_L2,5)
        # V31 keeps every physically recovered source pixel opaque except the narrow
        # antialias boundary.  This prevents the pale/thin icon edges visible in P2.
        certain=(interior>=max(0.75,feather*0.62))
        base=np.where(certain,1.0,np.maximum(geom,color*0.96))
        allowed=cv2.dilate(hard,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)),iterations=1)>0
        base=np.where(allowed,base,0.0)
        source='TRIMAP_EDGE_MATTE'
    stage_hard=np.zeros((h,w),dtype=bool); stage_soft=np.zeros((h,w),dtype=bool)
    if group_mask is not None:
        # Gate only against a slightly expanded top-level semantic group.  V31 does not
        # erode an icon to fit a speculative child mask.
        expanded=cv2.dilate((group_mask>0).astype(np.uint8)*255,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)),iterations=1)
        gate=_soft_group_gate(expanded,max(1.0,feather))
        base=np.minimum(base,gate)
        if native_alpha is None:
            stage_hard,stage_soft=_local_stage_leak_mask(rgb,group_mask,bg_rgb)
            # Remove border-connected white-stage pockets before alpha smoothing.
            # In the narrow antialias neighborhood cap opacity by real color evidence.
            base[stage_hard]=0.0
            if np.any(stage_soft):
                cd=_color_distance(rgb,bg_rgb)
                edge_cap=_smoothstep01((cd-1.0)/18.0)*0.96
                base[stage_soft]=np.minimum(base[stage_soft],edge_cap[stage_soft])
    # Tiny bilateral smoothing keeps alpha coherent along shaded cartoon edges
    # without moving the boundary or filling gaps between independent objects.
    a8=np.clip(base*255.0,0,255).astype(np.uint8)
    a8=cv2.bilateralFilter(a8,5,16,3)
    if np.any(stage_soft):
        # Bilateral smoothing may borrow opacity from adjacent foreground and lift a
        # border-connected stage pixel back above the hard leak cutoff. Reapply the
        # same color-derived soft cap after smoothing; enclosed white object content
        # is not stage_soft and remains untouched.
        cd=_color_distance(rgb,bg_rgb)
        edge_cap=_smoothstep01((cd-1.0)/18.0)*0.96
        a8[stage_soft]=np.minimum(a8[stage_soft],np.floor(edge_cap[stage_soft]*255.0).astype(np.uint8))
    # Restore certified opaque interiors after edge smoothing. The bilateral pass must
    # never turn solid source ink into a translucent 254-valued ghost.
    a8[(base>=0.995)&(hard>0)]=255
    a8[(base<=0.004)]=0
    alpha=np.asarray(a8,dtype=np.float32)/255.0

    # White/near-white edge decontamination. For a composited source C=aF+(1-a)B,
    # estimate F only in the soft band. Interior pixels are untouched.
    bg=np.asarray(bg_rgb,dtype=np.float32).reshape(1,1,3)
    src=rgb.astype(np.float32)
    denom=np.maximum(alpha[...,None],0.08)
    solved=(src-(1.0-alpha[...,None])*bg)/denom
    solved=np.clip(solved,0,255)
    edge=(alpha>0.035)&(alpha<0.985)
    weight=np.zeros_like(alpha,dtype=np.float32)
    weight[edge]=np.clip((1.0-alpha[edge])*0.88,0.18,0.78)
    clean=src*(1.0-weight[...,None])+solved*weight[...,None]
    clean=np.clip(clean,0,255).astype(np.uint8)

    soft=(a8>5)&(a8<250)
    hard_fg=a8>=250
    edge_count=int(np.count_nonzero(soft)); fg_count=max(1,int(np.count_nonzero(a8>5)))
    cd=_color_distance(rgb,bg_rgb)
    halo_risk=float(np.mean((cd[soft]<7.0).astype(np.float32))) if edge_count else 0.0
    stage_candidate=(stage_hard|stage_soft)
    stage_count=int(np.count_nonzero(stage_candidate))
    stage_opaque=int(np.count_nonzero(stage_candidate & (a8>=245)))
    metrics={
        'matting_source':source,
        'feather_px':round(feather,3),
        'soft_edge_pixel_fraction':round(edge_count/float(fg_count),6),
        'opaque_foreground_fraction':round(float(np.count_nonzero(hard_fg))/float(max(1,h*w)),6),
        'edge_halo_risk':round(halo_risk,6),
        'stage_leak_candidate_pixels':stage_count,
        'opaque_stage_leak_pixels':stage_opaque,
        'opaque_stage_leak_fraction':round(stage_opaque/float(max(1,fg_count)),6),
        'stage_leak_repair_applied':bool(stage_count),
        'alpha_min':int(a8.min()),
        'alpha_max':int(a8.max()),
        'alpha_unique_approx':int(len(np.unique((a8//8)*8))),
    }
    return a8,clean,metrics
