from __future__ import annotations
import math, os, pathlib, json, hashlib, shutil, uuid
from dataclasses import dataclass, asdict
from typing import Any
import cv2
cv2.setNumThreads(1)
try: cv2.ocl.setUseOpenCL(False)
except Exception: pass
import numpy as np
from PIL import Image
from hexa_v31.util import ensure_dir, sha256_file, write_json, read_json
from hexa_v31.hierarchy import decompose_semantic_group
from hexa_v31.matting import refine_alpha
from hexa_v31.occlusion import build_occlusion_graph
from hexa_v31.extraction.actor_extraction import extract_foundation_actors
from hexa_v31.extraction.reconstruction import build_lossless_foundation_partition,FOUNDATION_RECONSTRUCTION_VERSION
from hexa_v31.qa.actor_qa import actor_qa

VISION_CACHE_SCHEMA_VERSION='HEXA_V31_SCENE_VISION_CACHE_2.0'
VISION_CACHE_DEPENDENCIES={
    'vision':'VISION_10.0_SAFE_HIERARCHICAL_ASSET_DECOMPOSER',
    'extraction_matting':'EXTRACTION_MATTING_2.1_POST_SMOOTH_STAGE_CAP',
    'hierarchy_decomposition':'HIERARCHY_10.0_TOPOLOGICAL_DECOMPOSITION',
    'occlusion':'OCCLUSION_1.0_CONSERVATIVE_GRAPH',
    'foundation_reconstruction':FOUNDATION_RECONSTRUCTION_VERSION,
}

class VisionError(RuntimeError): pass

@dataclass
class PhysicalUnit:
    physical_id: str
    bbox: tuple[int,int,int,int]
    area_px: int
    center_norm: tuple[float,float]
    bbox_norm: tuple[float,float,float,float]
    mask_confidence: float
    edge_touch: bool
    semantic_unit_id: str|None = None
    semantic_type: str|None = None
    semantic_role: str|None = None

@dataclass
class SceneVisionResult:
    scene_id: str
    width: int
    height: int
    source_mode: str
    background_rgb: tuple[int,int,int]
    foreground_fraction: float
    raw_component_count: int
    grouped_detail_count: int
    major_group_count: int
    expected_semantic_units: int
    reconstruction_mae: float
    reconstruction_psnr: float
    reconstruction_pass: bool
    split_confidence: float
    mode: str
    edge_touching: bool
    units: list[dict]
    artifacts: dict
    cache_state: dict|None = None


def _cache_artifacts_complete(data:dict)->bool:
    art=data.get('artifacts') or {}
    required=[art.get('mask'),art.get('reconstruction'),art.get('background')]
    layers=art.get('layers') or []
    required.extend(x.get('path') for x in layers if isinstance(x,dict))
    return (
        bool(layers)
        and isinstance(art.get('matting_summary'),dict)
        and isinstance(art.get('hierarchy_decisions'),list)
        and isinstance(art.get('occlusion_graph'),dict)
        and all(x and pathlib.Path(x).is_file() for x in required)
    )


def _replace_scene_cache_directory(stage:pathlib.Path, target:pathlib.Path)->None:
    backup=target.parent/f'.{target.name}.backup-{uuid.uuid4().hex}'
    had_target=target.exists()
    try:
        if had_target:os.replace(target,backup)
        os.replace(stage,target)
    except Exception:
        if backup.exists() and not target.exists():os.replace(backup,target)
        raise
    finally:
        if stage.exists():shutil.rmtree(stage)
    if backup.exists():shutil.rmtree(backup)


def _bg_estimate(rgb: np.ndarray) -> tuple[int,int,int]:
    h,w=rgb.shape[:2]; band=max(3,min(h,w)//80)
    samples=np.concatenate([
        rgb[:band].reshape(-1,3), rgb[-band:].reshape(-1,3),
        rgb[:, :band].reshape(-1,3), rgb[:, -band:].reshape(-1,3)
    ],axis=0)
    # Select bright/low-saturation edge pixels first; robust against edge-touching objects.
    mx=samples.max(1); mn=samples.min(1); sat=mx-mn
    good=samples[(mx>=235)&(sat<=25)]
    use=good if len(good)>=100 else samples
    med=np.median(use,axis=0)
    return tuple(int(round(x)) for x in med)


def _foreground_mask(rgb: np.ndarray, alpha: np.ndarray|None, bg: tuple[int,int,int]) -> tuple[np.ndarray,str,float]:
    """Recover a white-stage foreground without cutting enclosed white icon interiors.

    P2 started from color seeds and contour fill.  That still produced brittle mattes on
    soft shadows, open outlines and complex icons.  V31 instead identifies *background
    connected to the canvas border*.  White pixels enclosed by artwork are therefore kept
    as foreground automatically, while only physically connected white-stage pixels are
    removed.  This is conservative by design: when uncertain, keep the original artwork
    grouped rather than slicing it into a bad cutout.
    """
    h,w=rgb.shape[:2]
    if alpha is not None and np.quantile(alpha,0.05)<250:
        mask=(alpha>4).astype(np.uint8)*255
        return mask,'NATIVE_ALPHA_AUTHORITY',0.995
    bgv=np.asarray(bg,dtype=np.int16).reshape(1,1,3)
    diff=np.max(np.abs(rgb.astype(np.int16)-bgv),axis=2)
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV); sat=hsv[:,:,1]
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    # Candidate white-stage pixels.  A generous tolerance is safe because only regions
    # physically connected to the outer border are allowed to become background.
    bg_candidate=((diff<=20)&(sat<=34)&(gray>=218)).astype(np.uint8)
    # Close microscopic JPEG/antialias gaps in the stage, but never close object gaps.
    bg_candidate=cv2.morphologyEx(bg_candidate,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
    n,labels,stats,_=cv2.connectedComponentsWithStats(bg_candidate,8)
    bg_labels=set()
    if n>1:
        border=np.concatenate([labels[0,:],labels[-1,:],labels[:,0],labels[:,-1]])
        for lab in np.unique(border):
            if int(lab)!=0:bg_labels.add(int(lab))
    connected_bg=np.isin(labels,list(bg_labels)) if bg_labels else np.zeros((h,w),dtype=bool)
    fg=(~connected_bg).astype(np.uint8)*255
    # Require real visual evidence near each retained component.  This removes isolated
    # white islands caused by compression while preserving enclosed white faces/cards.
    strong=((diff>=7)|(sat>=12)|(gray<=245)).astype(np.uint8)*255
    strong=cv2.dilate(strong,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)),iterations=1)
    n2,l2,st2,_=cv2.connectedComponentsWithStats((fg>0).astype(np.uint8),8)
    out=np.zeros_like(fg);min_area=max(12,int(h*w*0.000006));kept=0
    for i in range(1,n2):
        area=int(st2[i,cv2.CC_STAT_AREA])
        if area<min_area:continue
        cm=(l2==i)
        if np.count_nonzero(strong[cm])<max(3,int(area*0.002)):continue
        out[cm]=255;kept+=1
    # Preserve low-contrast source shadows only when they hug an accepted object.
    near=cv2.dilate((out>0).astype(np.uint8)*255,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(9,9)),iterations=1)>0
    shadow=(near&(diff>=2)&(diff<12)&(gray<252))
    out[shadow]=255
    return out,'BORDER_CONNECTED_WHITE_STAGE_MATTE',0.97 if kept else 0.55



def _grouped_detail_count(rgb: np.ndarray, mask: np.ndarray) -> int:
    """Estimate visually distinct supporting details without creating cutout layers.

    This number is used only for the user's 3-8 visible-secondary composition rule.
    It never authorizes animation of an internal fragment.  Large color/shape regions are
    counted conservatively; shading specks and antialias noise are ignored.
    """
    fg=(mask>0)
    total=int(np.count_nonzero(fg))
    if total<80:return 0
    h,w=mask.shape
    # Detached physical islands with a stricter, non-dilated component pass.
    n,labels,stats,_=cv2.connectedComponentsWithStats(fg.astype(np.uint8),8)
    min_area=max(50,int(total*0.018),int(h*w*0.000035))
    islands=sum(1 for i in range(1,n) if int(stats[i,cv2.CC_STAT_AREA])>=min_area)

    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    H=hsv[:,:,0].astype(np.int16);S=hsv[:,:,1].astype(np.int16);V=hsv[:,:,2].astype(np.int16)
    # Quantized visual regions. Low-saturation whites/grays are separated by value;
    # saturated artwork is separated by hue sectors. Each region must own >=3% of ink.
    q=np.full((h,w),-1,np.int16)
    sat=(S>=48)&fg
    q[sat]=(H[sat]//18).astype(np.int16)
    low=(~sat)&fg
    q[low]=10+np.clip((V[low]//52),0,4).astype(np.int16)
    regions=0
    for bid in np.unique(q[fg]):
        bm=(q==int(bid)).astype(np.uint8)
        bm=cv2.morphologyEx(bm,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
        nn,ll,ss,_=cv2.connectedComponentsWithStats(bm,8)
        for i in range(1,nn):
            a=int(ss[i,cv2.CC_STAT_AREA])
            if a>=max(70,int(total*0.030)):
                regions+=1
    # A single illustration can contain several legitimate visible supporting details
    # while remaining one safe alpha group. Do not inflate beyond the user's upper bound.
    detail=max(islands,regions)
    return int(max(1,min(8,detail)))

def _components(mask: np.ndarray):
    # Build components on a proximity-connected copy, not on every tiny stroke.
    # This prevents text/outline fragments from exploding into hundreds of O(n^3) merge candidates.
    h,w=mask.shape
    k=max(5,int(round(min(h,w)*0.005)))
    if k%2==0: k+=1
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k))
    grouping=cv2.dilate((mask>0).astype(np.uint8)*255,kernel,iterations=1)
    grouping=cv2.morphologyEx(grouping,cv2.MORPH_CLOSE,kernel,iterations=1)
    n,labels,stats,cent=cv2.connectedComponentsWithStats((grouping>0).astype(np.uint8),8)
    min_area=max(30,int(h*w*0.00012))
    comps=[]
    for i in range(1,n):
        x,y,bw,bh,area=[int(v) for v in stats[i]]
        if area<min_area: continue
        # Physical area is measured from the original mask inside the component bbox.
        orig_area=int(np.count_nonzero(mask[y:y+bh,x:x+bw]))
        if orig_area<20: continue
        comps.append({'label':i,'x':x,'y':y,'w':bw,'h':bh,'area':orig_area,'cx':float(cent[i][0]),'cy':float(cent[i][1])})
    if len(comps)>80:
        comps=sorted(comps,key=lambda c:c['area'],reverse=True)[:80]
    return comps,grouping

def _group_mask(original_mask: np.ndarray, group:dict) -> np.ndarray:
    h,w=original_mask.shape
    x=max(0,int(group['x'])); y=max(0,int(group['y'])); x2=min(w,int(group['x']+group['w'])); y2=min(h,int(group['y']+group['h']))
    out=np.zeros_like(original_mask)
    out[y:y2,x:x2]=original_mask[y:y2,x:x2]
    return out

def _bbox_gap(a,b):
    ax1,ay1,aw,ah=a['x'],a['y'],a['w'],a['h']; ax2,ay2,bw,bh=b['x'],b['y'],b['w'],b['h']
    dx=max(0,max(ax1,ax2)-min(ax1+aw,ax2+bw)); dy=max(0,max(ay1,ay2)-min(ay1+ah,ay2+bh))
    return math.hypot(dx,dy)


def _merge_components(comps:list[dict], target:int, W:int,H:int):
    if not comps: return []
    groups=[{'members':[c],**c} for c in comps]
    # Merge tiny fragments into nearest large group first, then reduce toward semantic target without forcing below 1.
    target=max(1,min(target if target>0 else 3,5))
    def recalc(g):
        xs=[m['x'] for m in g['members']]; ys=[m['y'] for m in g['members']]
        x2=[m['x']+m['w'] for m in g['members']]; y2=[m['y']+m['h'] for m in g['members']]
        x,y=min(xs),min(ys); xx,yy=max(x2),max(y2); area=sum(m['area'] for m in g['members'])
        g.update(x=x,y=y,w=xx-x,h=yy-y,area=area,cx=(x+xx)/2,cy=(y+yy)/2); return g
    groups=[recalc(g) for g in groups]
    # Maximum merging gap is relative to canvas; connected visual clusters often include arrows/labels separated by small whitespace.
    max_gap=0.085*math.hypot(W,H)
    while len(groups)>target:
        best=None
        for i in range(len(groups)):
            for j in range(i+1,len(groups)):
                gap=_bbox_gap(groups[i],groups[j])
                area_ratio=min(groups[i]['area'],groups[j]['area'])/max(groups[i]['area'],groups[j]['area'])
                # Tiny supports can attach across slightly larger gaps.
                score=gap*(0.65 if area_ratio<0.18 else 1.0)
                if best is None or score<best[0]: best=(score,gap,i,j)
        if best is None: break
        _,gap,i,j=best
        # If groups are extremely far apart and both large, keep them separate even if metadata undercounts.
        if gap>max_gap and min(groups[i]['area'],groups[j]['area'])>W*H*0.015: break
        ng={'members':groups[i]['members']+groups[j]['members']}
        for idx in sorted((i,j),reverse=True): groups.pop(idx)
        groups.append(recalc(ng))
    groups.sort(key=lambda g:(g['x'],g['y']))
    return groups




def _group_from_mask(gm: np.ndarray) -> dict | None:
    yy,xx=np.where(gm>0)
    if len(xx)<24:return None
    x0=int(xx.min());x1=int(xx.max())+1;y0=int(yy.min());y1=int(yy.max())+1
    area=int(len(xx))
    return {'members':[],'x':x0,'y':y0,'w':x1-x0,'h':y1-y0,'area':area,'cx':(x0+x1)/2.0,'cy':(y0+y1)/2.0,'_mask':gm}

def _best_projection_cut(gm: np.ndarray, axis:int, W:int, H:int):
    """Find a conservative valley between two substantial visual lobes.

    This is used only when semantic metadata expects more independent units than
    proximity grouping recovered. Thin arrows/connector lines often physically
    join otherwise independent objects; a low-density valley lets V31 separate
    those objects without inventing pixels or regenerating art.
    """
    yy,xx=np.where(gm>0)
    if len(xx)<80:return None
    x0,x1=int(xx.min()),int(xx.max())+1;y0,y1=int(yy.min()),int(yy.max())+1
    sub=gm[y0:y1,x0:x1]>0
    proj=sub.sum(axis=0 if axis==0 else 1).astype(np.float64)
    n=len(proj)
    if n<24:return None
    # Smooth only enough to ignore single outline pixels; preserve genuine gaps.
    k=max(3,int(round(n*0.025))); k+=1-k%2
    kernel=np.ones(k,dtype=np.float64)/k
    sm=np.convolve(proj,kernel,mode='same')
    lo=max(4,int(n*0.20));hi=min(n-4,int(n*0.80))
    if hi<=lo:return None
    peak=max(1.0,float(np.percentile(sm,90)))
    cand=sorted(range(lo,hi),key=lambda i:sm[i])[:max(5,int(n*0.10))]
    total=float(np.count_nonzero(sub))
    best=None
    for i in cand:
        if sm[i] > peak*0.32:continue
        if axis==0:
            left=float(np.count_nonzero(sub[:,:i]));right=float(np.count_nonzero(sub[:,i:]))
        else:
            left=float(np.count_nonzero(sub[:i,:]));right=float(np.count_nonzero(sub[i:,:]))
        if min(left,right)<max(60.0,total*0.14):continue
        balance=min(left,right)/max(left,right)
        score=(1.0-sm[i]/peak)*0.68+balance*0.32
        if best is None or score>best[0]:best=(score,i,x0,y0,x1,y1)
    return best

def _split_group_mask(gm: np.ndarray, W:int, H:int):
    h,w=gm.shape
    yy,xx=np.where(gm>0)
    if len(xx)<80:return None
    bbox_w=int(xx.max())-int(xx.min())+1;bbox_h=int(yy.max())-int(yy.min())+1
    axes=[]
    if bbox_w>=bbox_h*1.10 and bbox_w>=W*0.24:axes.append(0)
    if bbox_h>=bbox_w*1.10 and bbox_h>=H*0.24:axes.append(1)
    if not axes:axes=[0,1]
    choices=[]
    for ax in axes:
        c=_best_projection_cut(gm,ax,W,H)
        if c:choices.append((c[0],ax,c))
    if not choices:return None
    _,axis,c=max(choices,key=lambda z:z[0]);_,i,x0,y0,x1,y1=c
    a=np.zeros_like(gm);b=np.zeros_like(gm)
    if axis==0:
        cut=x0+i;a[:,:cut]=gm[:,:cut];b[:,cut:]=gm[:,cut:]
    else:
        cut=y0+i;a[:cut,:]=gm[:cut,:];b[cut:,:]=gm[cut:,:]
    ga=_group_from_mask(a);gb=_group_from_mask(b)
    if not ga or not gb:return None
    return [ga,gb]

def _split_groups_to_target(groups:list[dict], original_mask:np.ndarray, target:int, W:int,H:int):
    """Recover independently animatable lobes before declaring GROUPED_LAYERED.

    No semantic names, topic keywords, or scene IDs participate. Splits are
    accepted only when the physical mask itself contains a strong projection
    valley and both sides remain substantial.
    """
    out=[]
    for g in groups:
        gg=dict(g);gg['_mask']=g.get('_mask') if g.get('_mask') is not None else _group_mask(original_mask,g);out.append(gg)
    target=max(1,min(int(target or 1),5))
    while len(out)<target:
        candidates=[]
        for idx,g in enumerate(out):
            split=_split_group_mask(g['_mask'],W,H)
            if split:
                area=float(g.get('area') or np.count_nonzero(g['_mask']))
                candidates.append((area,idx,split))
        if not candidates:break
        _,idx,split=max(candidates,key=lambda x:x[0])
        out.pop(idx);out.extend(split);out.sort(key=lambda g:(g['x'],g['y']))
    return out

def _raw_components(mask: np.ndarray):
    h,w=mask.shape
    n,labels,stats,cent=cv2.connectedComponentsWithStats((mask>0).astype(np.uint8),8)
    min_area=max(20,int(h*w*0.000025))
    comps=[]
    for i in range(1,n):
        x,y,bw,bh,area=[int(v) for v in stats[i]]
        if area<min_area: continue
        comps.append({'label':i,'x':x,'y':y,'w':bw,'h':bh,'area':area,'cx':float(cent[i][0]),'cy':float(cent[i][1])})
    return comps,labels


def _bbox_union(members):
    xs=[m['x'] for m in members];ys=[m['y'] for m in members];x2=[m['x']+m['w'] for m in members];y2=[m['y']+m['h'] for m in members]
    x,y=min(xs),min(ys);xx,yy=max(x2),max(y2)
    return {'members':members,'x':x,'y':y,'w':xx-x,'h':yy-y,'area':sum(m['area'] for m in members),'cx':(x+xx)/2,'cy':(y+yy)/2}


def _partition_for_semantics(mask: np.ndarray, semantic:list[dict], W:int, H:int):
    """Conservative physical partition.

    Character isolation starts from the original (non-dilated) foreground components so
    neighboring props cannot be accidentally merged into the character. Small detached
    gesture/pose fragments may be attached only when they are close to the body. If a
    plausible clean character body cannot be isolated, the scene falls back to a composite
    group instead of moving a contaminated character layer.
    """
    char_sem=[u for u in semantic if u.get('type') in ('MAIN_CHARACTER','SECONDARY_CHARACTER')]
    other_sem=[u for u in semantic if u not in char_sem]
    raw,labels=_raw_components(mask)
    available=list(raw); remaining_mask=mask.copy(); groups=[]; assignments=[]
    diag=math.hypot(W,H)
    for sem in char_sem:
        if not available: break
        def score(c):
            wf=c['w']/W;hf=c['h']/H;ar=c['h']/max(1,c['w']);side=abs(c['cx']/W-0.5)
            return 2.4*min(hf/0.72,1.25)+1.8*min(ar/2.0,1.25)+0.20*side-2.0*max(0,wf-0.32)
        body=max(available,key=score)
        wf=body['w']/W;hf=body['h']/H;ar=body['h']/max(1,body['w'])
        if not (hf>=0.26 and ar>=0.90 and wf<=0.39):
            # Physical contact/contamination is too likely. Keep composite scene grouping.
            break
        members=[body]
        # Attach only small, nearby detached pose pieces (hands, gesture marks, hair fragments).
        for c in list(available):
            if c is body: continue
            gap=_bbox_gap(body,c)
            small=c['area'] <= max(600,body['area']*0.20)
            not_object_sized=(c['w']/W<0.16 and c['h']/H<0.22)
            # expanded body neighborhood; generous horizontally for an extended arm/hand.
            ex0=body['x']-0.18*W; ex1=body['x']+body['w']+0.18*W
            ey0=body['y']-0.10*H; ey1=body['y']+body['h']+0.10*H
            near=(ex0<=c['cx']<=ex1 and ey0<=c['cy']<=ey1 and gap<=0.09*diag)
            if small and not_object_sized and near:
                members.append(c)
        g=_bbox_union(members)
        ids=[m['label'] for m in members]
        cm=np.isin(labels,ids).astype(np.uint8)*255
        # Small dilation only for antialias protection, not semantic grouping.
        cm=cv2.morphologyEx(cm,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
        g['_mask']=cm;g['_reserved_character']=True;g['_semantic_mapping_confidence']=0.96
        groups.append(g);assignments.append(sem)
        remaining_mask[cm>0]=0
        used=set(ids);available=[c for c in available if c['label'] not in used]
    # All remaining foreground is object/context space. Group it independently.
    obj_comps,_=_components(remaining_mask)
    target=max(1,len(other_sem)) if np.any(remaining_mask>0) else 0
    obj_groups=_merge_components(obj_comps,target,W,H) if obj_comps else []
    for g in obj_groups:
        g['_mask']=_group_mask(remaining_mask,g)
    # V31 independent-object recovery: if proximity grouping was bridged by a
    # thin connector/arrow but the semantic plan expects multiple units, split
    # only at strong physical projection valleys. This directly increases the
    # amount of real object-level choreography available to the renderer.
    # V31: never split a connected object merely to satisfy semantic unit count.
    # If the source art physically joins elements, keep them grouped; bad cutouts are a hard failure.
    base=len(groups);groups.extend(obj_groups);assignments.extend([None]*len(obj_groups))
    rem_indices=list(range(base,len(groups)))
    # Mapping a semantic name onto a flat-image component is not the same problem as
    # physically isolating that component.  P2 conflated the two and then animated wrong
    # source/target objects.  V31 records confidence explicitly and permits relationship
    # choreography only when both endpoints are physically/semantically unambiguous.
    ordered_sem=sorted(other_sem,key=lambda x:0 if str(x.get('role') or '').upper()=='PRIMARY' else 1)
    if len(rem_indices)==1 and len(ordered_sem)==1:
        gi=rem_indices.pop();assignments[gi]=ordered_sem[0];groups[gi]['_semantic_mapping_confidence']=0.99
    else:
        for u in ordered_sem:
            if not rem_indices:break
            gi=max(rem_indices,key=lambda k:groups[k]['area']);rem_indices.remove(gi);assignments[gi]=u
            role=str(u.get('role') or '').upper()
            # A unique dominant standalone primary can be mapped with useful confidence;
            # multiple similarly-sized unlabeled icons remain deliberately uncertain.
            ranked=sorted([float(groups[k]['area']) for k in range(base,len(groups))],reverse=True)
            dominance=(ranked[0]/max(1.0,ranked[1])) if len(ranked)>1 and gi==max(range(base,len(groups)),key=lambda k:groups[k]['area']) else 1.0
            conf=0.90 if role=='PRIMARY' and sum(1 for x in ordered_sem if str(x.get('role') or '').upper()=='PRIMARY')==1 and dominance>=1.55 else 0.58
            groups[gi]['_semantic_mapping_confidence']=conf
    for gi in range(base,len(groups)):
        groups[gi].setdefault('_semantic_mapping_confidence',0.0)
    return groups,assignments



def _expand_hierarchical_groups(groups:list[dict], assignments:list[dict|None], W:int, H:int, rgb:np.ndarray|None=None):
    """Expose only evidence-backed optional children beside an atomic root.

    The root is always preserved as the authoritative semantic composite.  Children are
    never fabricated, never replace the root, and are rejected for characters or whenever
    deterministic physical separation/reconstruction evidence is insufficient.
    """
    out_g=[];out_a=[];decisions=[]
    for i,g in enumerate(groups):
        sem=assignments[i] if i<len(assignments) else None
        gg=dict(g)
        slot=str((sem or {}).get('unit_id') or f'PHYSICAL_SLOT_{i+1:02d}')
        gg['_hierarchy_level']=0;gg['_parent_semantic_unit_id']=None;gg['_composition_slot_id']=slot
        gg['_subobject_role']='CONTEXT';gg['_hierarchy_confidence']=1.0
        gg['_root_atomic']=True;gg['_decomposition_root_id']=f'ROOT_{i+1:02d}'
        # Top-level groups are allowed to translate only when their physical mask is detached
        # from other top-level groups; the occlusion graph performs the final downgrade.
        gg['_animation_safe']=True;gg['_reveal_safe']=True;gg['_animation_mode']='TRANSLATE_SAFE';gg['_occlusion_class']='TOP_LEVEL_SEMANTIC_GROUP'
        out_g.append(gg);out_a.append(sem)
        typ=str((sem or {}).get('type') or '').upper()
        if typ in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}:
            decisions.append({'root_id':gg['_decomposition_root_id'],'semantic_unit_id':(sem or {}).get('unit_id'),'composition_slot_id':slot,'accepted':False,'reason':'UNSAFE_CHARACTER_FRAGMENTATION','decomposition_mode':'ROOT_ATOMIC_ONLY','child_count':0})
            continue
        result=decompose_semantic_group(gg.get('_mask') if gg.get('_mask') is not None else _group_mask(np.zeros((H,W),np.uint8),gg),W=W,H=H,semantic_type=typ,semantic_role=str((sem or {}).get('role') or ''),rgb=rgb)
        decision={'root_id':gg['_decomposition_root_id'],'semantic_unit_id':(sem or {}).get('unit_id'),'composition_slot_id':slot,'accepted':bool(result.get('accepted')),'reason':result.get('reason'),'decomposition_mode':result.get('decomposition_mode'),'child_count':len(result.get('children') or []),'confidence':result.get('confidence',0.0),'evidence':result.get('evidence') or []}
        decisions.append(decision)
        if not result.get('accepted'):
            continue
        # Child masks form an exact source partition and retain their root slot.  They are
        # opt-in reveal/translation candidates; semantic movement still requires downstream
        # mapping confidence and the existing occlusion graph.
        for child in result.get('children') or []:
            x,y,bw,bh=child.bbox
            cg={'members':[],'x':x,'y':y,'w':bw,'h':bh,'area':child.area_px,'cx':child.center_norm[0]*W,'cy':child.center_norm[1]*H,'_mask':child.mask,
                '_hierarchy_level':1,'_parent_semantic_unit_id':(sem or {}).get('unit_id'),'_composition_slot_id':slot,'_subobject_role':child.role_candidate,
                '_hierarchy_confidence':float(child.confidence),'_animation_safe':bool(child.animation_safe),'_reveal_safe':bool(child.reveal_safe),'_animation_mode':child.animation_mode,
                '_occlusion_class':child.occlusion_class,'_root_atomic':False,'_decomposition_root_id':gg['_decomposition_root_id'],
                '_semantic_mapping_confidence':min(float(gg.get('_semantic_mapping_confidence',0.0)),float(child.confidence))}
            out_g.append(cg);out_a.append(sem)
    return out_g,out_a,decisions

def analyze_scene(scene:dict, image_path:str|os.PathLike, out_dir:str|os.PathLike, logger=None,foundation_result:dict|None=None) -> SceneVisionResult:
    sid=scene['scene_id']; cache_root=ensure_dir(pathlib.Path(out_dir)); final_out=cache_root/sid
    input_payload={'image_sha256':sha256_file(image_path),'semantic_units':scene.get('units') or []}
    dependency_payload=dict(VISION_CACHE_DEPENDENCIES)
    foundation_signature=((foundation_result or {}).get('cache_state') or {}).get('signature')
    dependency_payload['foundation_vision']=foundation_signature or 'LEGACY_CV_FALLBACK'
    sig_payload={'cache_schema':VISION_CACHE_SCHEMA_VERSION,'input':input_payload,'dependencies':dependency_payload}
    cache_sig=hashlib.sha256(json.dumps(sig_payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    meta_path=final_out/'cache_meta.json'; vision_path=final_out/'vision.json'; cache_status='GENERATED'; invalidation_reason=None
    if meta_path.is_file() and vision_path.is_file():
        try:
            meta=read_json(meta_path); data=read_json(vision_path)
            if meta.get('cache_signature')==cache_sig and _cache_artifacts_complete(data):
                if logger: logger.log('PASS','SCENE_VISION_CACHE_HIT',mode=data.get('mode'),cache_signature=cache_sig[:16])
                data['cache_state']={'status':'HIT','reason':None,'cache_signature':cache_sig}
                return SceneVisionResult(**data)
            old_payload=meta.get('input') if isinstance(meta.get('input'),dict) else {}
            if 'input' in old_payload:
                old_input=old_payload.get('input'); old_dependencies=old_payload.get('dependencies')
            else:
                # V1 cache metadata stored the image/semantic identity beside one
                # coarse algorithm label. Preserve the input identity while treating
                # that legacy algorithm as an obsolete dependency fingerprint.
                old_input={'image_sha256':old_payload.get('image_sha256'),'semantic_units':old_payload.get('semantic_units') or []}
                old_dependencies={'legacy_algorithm':old_payload.get('algorithm')}
            if old_input==input_payload and old_dependencies!=dependency_payload:
                cache_status='INVALIDATED_DEPENDENCY_CHANGED'; invalidation_reason='DEPENDENCY_CHANGED'
            else:
                cache_status='MISS_INPUT_CHANGED'; invalidation_reason='INPUT_CHANGED_OR_INCOMPLETE_ARTIFACT_SET'
        except Exception:
            cache_status='MISS_INPUT_CHANGED'; invalidation_reason='CACHE_READ_FAILED'
    if logger and invalidation_reason:
        logger.log('INFO','SCENE_VISION_CACHE_INVALIDATED',cache_state=cache_status,reason=invalidation_reason,cache_signature=cache_sig[:16])
    out=cache_root/f'.{sid}.stage-{uuid.uuid4().hex}'
    ensure_dir(out)
    im=Image.open(image_path)
    rgba=np.array(im.convert('RGBA'))
    raw_rgb=rgba[:,:,:3]; alpha=rgba[:,:,3] if im.mode in ('RGBA','LA') or 'transparency' in im.info else None
    native_alpha=bool(alpha is not None and np.quantile(alpha,0.05)<250)
    H,W=raw_rgb.shape[:2]
    bg=(255,255,255) if native_alpha else _bg_estimate(raw_rgb)
    if native_alpha:
        aa=(alpha.astype(np.float32)/255.0)[...,None]
        rgb=(raw_rgb.astype(np.float32)*aa+np.array(bg,dtype=np.float32).reshape(1,1,3)*(1-aa)).astype(np.uint8)
    else:
        rgb=raw_rgb
    mask,source_mode,base_conf=_foreground_mask(raw_rgb if native_alpha else rgb,alpha,bg)
    comps,_grouping=_components(mask)
    grouped_detail_count=_grouped_detail_count(rgb,mask)
    semantic=scene.get('units') or []
    groups,assignments=_partition_for_semantics(mask,semantic,W,H)
    groups,assignments,hierarchy_decisions=_expand_hierarchical_groups(groups,assignments,W,H,rgb=rgb)
    unit_rows=[]; layer_paths=[]
    union=np.zeros((H,W),np.uint8)
    union_alpha=np.zeros((H,W),np.uint8)
    alpha_by_id={}
    clean_rgb_by_id={}
    matting_rows=[]
    for idx,g in enumerate(groups,1):
        gm=g.get('_mask') if g.get('_mask') is not None else _group_mask(mask,g)
        # V31 keeps the semantic partition physically conservative and reconstructs
        # antialiasing through a soft matte instead of binary dilation. A 1px close
        # repairs tiny contour gaps without inflating the object silhouette.
        gm=cv2.morphologyEx((gm>0).astype(np.uint8)*255,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)),iterations=1)
        union=cv2.bitwise_or(union,gm)
        x,y,bw,bh=g['x'],g['y'],g['w'],g['h']
        edge=(x<=2 or y<=2 or x+bw>=W-2 or y+bh>=H-2)
        sem=assignments[idx-1] if idx-1<len(assignments) else None
        pid=f'PHYS_{idx:02d}'
        layer_alpha,clean_rgb,matte=refine_alpha(raw_rgb if native_alpha else rgb,gm,bg,native_alpha=alpha if native_alpha else None,group_mask=gm)
        alpha_by_id[pid]=layer_alpha; clean_rgb_by_id[pid]=clean_rgb; matting_rows.append(matte)
        union_alpha=np.maximum(union_alpha,layer_alpha)
        # V21 PHYSICAL CANVAS LOCK (preserved from V20.0.4):
        # Every extracted semantic unit is stored on the ORIGINAL full-scene transparent canvas.
        # This removes Premiere's cropped-still coordinate ambiguity entirely: at rest every layer
        # shares one origin/scale with the Worker Scene, while the rendered-scene motion stage only applies relative travel.
        # It costs some disk space but PNG transparency compresses well and physical fidelity wins.
        pad=max(2,int(min(W,H)*0.004))
        yy,xx=np.where(gm>0)
        if len(xx):
            cx0=max(0,int(xx.min())-pad); cy0=max(0,int(yy.min())-pad); cx1=min(W,int(xx.max())+1+pad); cy1=min(H,int(yy.max())+1+pad)
        else:
            cx0,cy0,cx1,cy1=x,y,x+bw,y+bh
        layer_rgba=np.dstack([clean_rgb,layer_alpha])
        lp=out/f'{pid}.png'; final_lp=final_out/f'{pid}.png'; Image.fromarray(layer_rgba,'RGBA').save(lp)
        layer_paths.append({'path':str(final_lp),'origin_px':[0,0],'size_px':[W,H],'content_origin_px':[cx0,cy0],'content_size_px':[cx1-cx0,cy1-cy0],'canvas_mode':'FULL_SCENE_ALPHA_CANVAS'})
        # The semantic object's physical center still drives travel direction/delta, but never static layout.
        # Static layout is now encoded directly in the full-canvas alpha pixels.
        place_cx=(cx0+cx1)/2.0; place_cy=(cy0+cy1)/2.0
        pu=PhysicalUnit(
            physical_id=pid,bbox=(x,y,bw,bh),area_px=int(g['area']),
            center_norm=(round(place_cx/W,6),round(place_cy/H,6)),
            bbox_norm=(round(x/W,6),round(y/H,6),round(bw/W,6),round(bh/H,6)),
            mask_confidence=round(base_conf*(0.95 if len(g['members'])>=1 else 0.7),4),edge_touch=edge,
            semantic_unit_id=sem.get('unit_id') if sem else None,semantic_type=sem.get('type') if sem else None,semantic_role=sem.get('role') if sem else None,
        )
        row=asdict(pu); row['hierarchy_level']=int(g.get('_hierarchy_level',0)); row['parent_semantic_unit_id']=g.get('_parent_semantic_unit_id'); row['composition_slot_id']=str(g.get('_composition_slot_id') or row.get('semantic_unit_id') or row.get('physical_id')); row['subobject_role']=g.get('_subobject_role'); row['hierarchy_confidence']=float(g.get('_hierarchy_confidence',0.0)); row['animation_safe']=bool(g.get('_animation_safe',True)); row['reveal_safe']=bool(g.get('_reveal_safe',True)); row['animation_mode']=str(g.get('_animation_mode') or ('TRANSLATE_SAFE' if row['animation_safe'] else 'GROUP_ONLY')); row['occlusion_class']=str(g.get('_occlusion_class') or ('CLEAN_SEPARABLE' if row['animation_safe'] else 'GROUP_ONLY')); row['matting']=matte; row['semantic_mapping_confidence']=round(float(g.get('_semantic_mapping_confidence',0.0)),4); row['layer_path']=str(final_lp); row['mask_path']=str(final_lp); row['layer_canvas_mode']='FULL_SCENE_ALPHA_CANVAS'; row['layer_source_size_px']=[W,H]; row['crop_origin_px']=[cx0,cy0]; row['crop_size_px']=[cx1-cx0,cy1-cy0]; row['root_id']=g.get('_decomposition_root_id'); row['parent_id']=g.get('_decomposition_root_id') if row['hierarchy_level']>0 else None; row['child_id']=f"{g.get('_decomposition_root_id')}::CHILD_{row['hierarchy_level']}_{idx}" if row['hierarchy_level']>0 else None; row['visible_area']=round(float(np.count_nonzero(layer_alpha>4))/(W*H),6); row['optical_center']=row['center_norm']; row['independence_confidence']=row['hierarchy_confidence']; row['reconstruction_error']=0.0; unit_rows.append(row)
    foundation_rejected=[]
    foundation_reconstruction={'partition_complete':False,'residual_support_present':False,'root_fallback_available':True,'reason':'FOUNDATION_NOT_USED'}
    if foundation_result and foundation_result.get('status')=='PASS':
        actors,foundation_rejected,foundation_alpha,foundation_layers=extract_foundation_actors(foundation_result,rgb,bg,mask,out,final_out,len(unit_rows)+1)
        residual,residual_layer,foundation_reconstruction=build_lossless_foundation_partition(rgb,bg,mask,actors,foundation_alpha,out,final_out)
        if actors:
            for legacy in unit_rows:
                legacy['foundation_fallback_root']=True;legacy['fallback_only_when_foundation_unavailable']=True;legacy['render_mode']='ROOT_ATOMIC'
            for actor in actors:actor['render_mode']='CHILD_PARTITION';actor['partition_complete']=bool(foundation_reconstruction['partition_complete']);actor['partition_root_id']='ROOT_COMPOSITE'
            if residual:
                residual['partition_complete']=bool(foundation_reconstruction['partition_complete']);actors.append(residual);foundation_layers.append(residual_layer)
        unit_rows.extend(actors);alpha_by_id.update(foundation_alpha);layer_paths.extend(foundation_layers);matting_rows.extend([x.get('matting') or {} for x in actors])
    # Hard-rule fifth-element special case is evaluated by *composition slots*, not physical
    # animation layers. Splitting one machine into body/coin/display must not falsely create a
    # five-element layout.
    fifth_overlay=None
    slot_ids=[]
    for row in unit_rows:
        slot=str(row.get('composition_slot_id') or row.get('semantic_unit_id') or row.get('physical_id'))
        if slot not in slot_ids:slot_ids.append(slot)
    if len(slot_ids)==5:
        sem_by_id={str(u.get('unit_id')):u for u in semantic if u.get('unit_id')}
        candidates=[]
        for slot in slot_ids:
            slot_rows=[r for r in unit_rows if str(r.get('composition_slot_id'))==slot]
            rep=max(slot_rows,key=lambda r:float(r.get('area_px') or 0))
            typ=str(rep.get('semantic_type') or '').upper()
            if typ in {'MAIN_CHARACTER','SECONDARY_CHARACTER'}:continue
            sem=sem_by_id.get(str(rep.get('semantic_unit_id') or ''),{})
            trig=sem.get('appear_trigger') or sem.get('focus_trigger') or {};pos=trig.get('global_char_start')
            try:pos=float(pos)
            except Exception:pos=-1.0
            supporting=1 if str(rep.get('semantic_role') or '').upper()!='PRIMARY' else 0
            area=sum(float(r.get('area_px') or 0) for r in slot_rows)
            candidates.append((pos,supporting,-area,slot))
        if candidates:
            _,_,_,chosen_slot=max(candidates,key=lambda z:(z[0],z[1],z[2]))
            for row in unit_rows:row['fifth_element_overlay']=str(row.get('composition_slot_id'))==chosen_slot
            fifth_overlay={'active':True,'composition_slot_id':chosen_slot,'black_opacity_percent':42,'blur_percent':16,'base_four_must_persist':True}
    for row in unit_rows:row.setdefault('fifth_element_overlay',False)

    # Build the V31 conservative occlusion graph after all physical layers exist.
    # The graph may downgrade a previously detached TRANSLATE_SAFE layer when its
    # flat-source geometry or matte indicates that travel could expose unseen pixels.
    occlusion_graph=build_occlusion_graph(unit_rows,alpha_by_id)

    # Reconstruction First uses the physically estimated source background so the
    # decomposition can be compared against the Worker image without hiding errors.
    source_bgimg=np.zeros_like(rgb); source_bgimg[:]=np.array(bg,dtype=np.uint8)
    a=(union_alpha.astype(np.float32)/255.0)[...,None]
    # Reconstruct against the physical source colors with the refined alpha. The
    # soft edge is what the renderer actually uses, so QA cannot pass a binary mask
    # while shipping a visibly different matte.
    recon=(rgb*a+source_bgimg*(1-a)).astype(np.uint8)
    # Runtime stage is normalized to canonical white. The references define white/near-white
    # as the permanent stage; generator tint/noise in otherwise empty background is not
    # semantic scene content and must not inflate density or drift between scenes.
    stage_bg=np.zeros_like(rgb); stage_bg[:]=np.array((255,255,255),dtype=np.uint8)
    Image.fromarray(stage_bg).save(out/'background.png')
    mae=float(np.mean(np.abs(recon.astype(np.int16)-rgb.astype(np.int16))))
    mse=float(np.mean((recon.astype(np.float32)-rgb.astype(np.float32))**2))
    psnr=99.0 if mse<1e-9 else 20*math.log10(255.0/math.sqrt(mse))
    foreground=float(np.count_nonzero(mask)/(H*W))
    expected=max(1,len(semantic)); gc=len(groups); slot_count=len(slot_ids)
    split_conf=max(0.0,1.0-abs(slot_count-expected)/max(expected,slot_count,1))
    reconstruction_pass=(mae<=3.25 and psnr>=31.0)
    assigned_slots={str(u.get('composition_slot_id')) for u in unit_rows if u.get('semantic_unit_id')}
    clean_semantic=(slot_count==expected and len(assigned_slots)==expected)
    if reconstruction_pass and slot_count==5 and fifth_overlay: mode='FIFTH_ELEMENT_OVERLAY'
    elif reconstruction_pass and clean_semantic: mode='CLEAN_LAYERED'
    elif reconstruction_pass and slot_count<=max(1,expected): mode='GROUPED_LAYERED'
    elif reconstruction_pass and slot_count<=5: mode='HYBRID'
    else: mode='FLAT_SCENE'
    # Store diagnostic mask/reconstruction, not user-facing generated art.
    Image.fromarray(mask).save(out/'foreground_mask.png')
    Image.fromarray(recon).save(out/'reconstruction.png')
    matte_summary={
        'layer_count':len(matting_rows),
        'mean_soft_edge_pixel_fraction':round(float(np.mean([m.get('soft_edge_pixel_fraction',0.0) for m in matting_rows]) if matting_rows else 0.0),6),
        'max_edge_halo_risk':round(float(max([m.get('edge_halo_risk',0.0) for m in matting_rows] or [0.0])),6),
        'max_opaque_stage_leak_fraction':round(float(max([m.get('opaque_stage_leak_fraction',0.0) for m in matting_rows] or [0.0])),6),
        'stage_leak_repair_layers':sum(1 for m in matting_rows if bool(m.get('stage_leak_repair_applied'))),
        'stage_leak_hard_gate':True,
        'soft_alpha_required':True,
        'binary_alpha_layers':sum(1 for m in matting_rows if int(m.get('alpha_unique_approx',0))<=2),
    }
    foundation_actors=[x for x in unit_rows if x.get('candidate_source')]
    staged_foundation_actors=[dict(x,layer_path=str(out/pathlib.Path(x['layer_path']).name)) for x in foundation_actors]
    foundation_qa=actor_qa(staged_foundation_actors,foundation_rejected)
    foundation_diagnostics=dict((foundation_result or {}).get('diagnostics') or {})
    foundation_diagnostics.update({'legacy_candidate_count':len(unit_rows)-len(foundation_actors),'merged_candidate_count':len(unit_rows),'accepted_actor_count':len(foundation_actors),'translation_safe_actor_count':sum(bool(x.get('translation_safe_after_occlusion')) for x in foundation_actors),'reveal_only_actor_count':sum(bool(x.get('reveal_safe')) and not bool(x.get('translation_safe_after_occlusion')) for x in foundation_actors),'atomic_actor_count':sum(x.get('safety_class')=='ATOMIC_PARENT_DEPENDENT' for x in foundation_actors),'rejected_actor_count':int(foundation_diagnostics.get('rejected_actor_count',0))+len(foundation_rejected)})
    result=SceneVisionResult(sid,W,H,source_mode,bg,round(foreground,6),len(comps),grouped_detail_count,gc,len(semantic),round(mae,4),round(psnr,3),reconstruction_pass,round(split_conf,4),mode,any(u['edge_touch'] for u in unit_rows),unit_rows,{
        'mask':str(final_out/'foreground_mask.png'),'reconstruction':str(final_out/'reconstruction.png'),'background':str(final_out/'background.png'),'grouped_detail_count':grouped_detail_count,'layers':layer_paths,'hierarchy_decisions':hierarchy_decisions,'fifth_element_overlay':fifth_overlay,'matting_summary':matte_summary,'occlusion_graph':occlusion_graph,'foundation_vision':{'status':(foundation_result or {}).get('status','FALLBACK'),'backend_used':(foundation_result or {}).get('backend_used','LEGACY_CV'),'diagnostics':foundation_diagnostics,'accepted_actor_count':len(foundation_actors),'rejected_actors':foundation_rejected,'actor_qa':foundation_qa,'reconstruction_qa':foundation_reconstruction,'root_fallback_available':True,'legacy_fallback_used':not bool(foundation_reconstruction.get('partition_complete')),'error':(foundation_result or {}).get('error')}
    },{'status':cache_status,'reason':invalidation_reason,'cache_signature':cache_sig})
    write_json(out/'vision.json',asdict(result)); write_json(out/'cache_meta.json',{'schema':VISION_CACHE_SCHEMA_VERSION,'cache_signature':cache_sig,'input':sig_payload})
    staged_data=read_json(out/'vision.json')
    staged_data['artifacts']['mask']=str(out/'foreground_mask.png'); staged_data['artifacts']['reconstruction']=str(out/'reconstruction.png'); staged_data['artifacts']['background']=str(out/'background.png')
    for layer in staged_data['artifacts'].get('layers') or []:layer['path']=str(out/pathlib.Path(layer['path']).name)
    if not _cache_artifacts_complete(staged_data):raise VisionError('Atomic scene cache staging validation failed for '+sid)
    _replace_scene_cache_directory(out,final_out)
    if logger: logger.log('PASS' if mode!='FLAT_SCENE' else 'WARNING','SCENE_VISION_ANALYZED',mode=mode,source_mode=source_mode,major_groups=gc,composition_slots=slot_count,expected_units=expected,reconstruction_mae=result.reconstruction_mae,reconstruction_psnr=result.reconstruction_psnr,edge_touching=result.edge_touching,hierarchical_children=sum(1 for u in unit_rows if int(u.get('hierarchy_level',0))>0),matte_halo_risk=matte_summary.get('max_edge_halo_risk'),opaque_stage_leak=matte_summary.get('max_opaque_stage_leak_fraction'),grouped_detail_count=grouped_detail_count,translation_safe_after_occlusion=len(occlusion_graph.get('translation_safe_nodes') or []))
    return result
