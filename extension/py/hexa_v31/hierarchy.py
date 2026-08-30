from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Any
import cv2
import numpy as np

@dataclass
class HierarchyChild:
    child_index: int
    bbox: tuple[int,int,int,int]
    area_px: int
    center_norm: tuple[float,float]
    bbox_norm: tuple[float,float,float,float]
    confidence: float
    animation_safe: bool
    reveal_safe: bool
    animation_mode: str
    occlusion_class: str
    role_candidate: str
    mask: np.ndarray

class TopologicalDecompositionValidator:
    """Deterministic physical proof that a child partition preserves topology."""
    version='HEXA_TOPOLOGICAL_DECOMPOSITION_VALIDATOR_V1'

    @staticmethod
    def _skeleton(binary:np.ndarray)->np.ndarray:
        # Zhang-Suen thinning keeps connector endpoints and junctions stable
        # without adding a heavyweight runtime dependency.
        img=np.pad((binary>0).astype(np.uint8),1)
        for _ in range(128):
            changed=False
            for first in (True,False):
                p2=img[:-2,1:-1];p3=img[:-2,2:];p4=img[1:-1,2:];p5=img[2:,2:]
                p6=img[2:,1:-1];p7=img[2:,:-2];p8=img[1:-1,:-2];p9=img[:-2,:-2];c=img[1:-1,1:-1]
                neighbors=p2+p3+p4+p5+p6+p7+p8+p9
                transitions=sum(x.astype(np.uint8) for x in (((p2==0)&(p3==1)),((p3==0)&(p4==1)),((p4==0)&(p5==1)),((p5==0)&(p6==1)),((p6==0)&(p7==1)),((p7==0)&(p8==1)),((p8==0)&(p9==1)),((p9==0)&(p2==1))))
                if first:guard=(p2*p4*p6==0)&(p4*p6*p8==0)
                else:guard=(p2*p4*p8==0)&(p2*p6*p8==0)
                remove=(c==1)&(neighbors>=2)&(neighbors<=6)&(transitions==1)&guard
                if np.any(remove):c[remove]=0;changed=True
            if not changed:break
        return img[1:-1,1:-1]

    def validate(self,root:np.ndarray,children:list[np.ndarray],mode:str)->dict:
        root=(root>0).astype(np.uint8);parts=[(m>0).astype(np.uint8) for m in children]
        union=np.zeros_like(root);overlap=np.zeros_like(root,dtype=np.uint16)
        for part in parts:union|=part;overlap+=part
        total=max(1,int(root.sum()));reconstruction_error=float(np.count_nonzero(union!=root))/total
        overlap_error=float(np.count_nonzero(overlap>1))/total
        components=max(0,cv2.connectedComponents(root,8)[0]-1)
        owner=np.full(root.shape,-1,np.int16)
        for i,part in enumerate(parts):owner[part>0]=i
        seam=np.zeros_like(root)
        seam[:,1:]|=((owner[:,1:]!=owner[:,:-1])&(owner[:,1:]>=0)&(owner[:,:-1]>=0)).astype(np.uint8)
        seam[1:,:]|=((owner[1:,:]!=owner[:-1,:])&(owner[1:,:]>=0)&(owner[:-1,:]>=0)).astype(np.uint8)
        skeleton=self._skeleton(root);neighbors=cv2.filter2D(skeleton,-1,np.ones((3,3),np.uint8))-skeleton
        branches=(skeleton>0)&(neighbors>=3);endpoints=(skeleton>0)&(neighbors==1)
        seam_dil=cv2.dilate(seam,np.ones((3,3),np.uint8))
        skeleton_cut_fraction=float(np.count_nonzero((skeleton>0)&(seam_dil>0)))/max(1,int(skeleton.sum()))
        branch_damage_fraction=float(np.count_nonzero(branches&(seam_dil>0)))/max(1,int(np.count_nonzero(branches)))
        seam_length_fraction=float(np.count_nonzero(seam))/max(1,int(skeleton.sum()))
        detached=components>=len(parts) and mode=='DETACHED_LOBES'
        reasons=[]
        if reconstruction_error>0.001 or overlap_error>0.001:reasons.append('SOURCE_RECONSTRUCTION_ERROR')
        if not detached and skeleton_cut_fraction>0.012:reasons.append('SKELETON_CONNECTOR_CUT')
        if not detached and branch_damage_fraction>0.0:reasons.append('SKELETON_BRANCH_DAMAGE')
        if not detached and seam_length_fraction>0.08:reasons.append('ARTIFICIAL_EXPOSED_SEAM')
        if any(int(p.sum())<max(80,int(total*.055)) for p in parts):reasons.append('CHILD_NOT_INDEPENDENTLY_READABLE')
        confidence=max(0.0,1.0-reconstruction_error*20-overlap_error*20-skeleton_cut_fraction*2-branch_damage_fraction*.6-seam_length_fraction)
        if not detached:confidence=min(confidence,.58)
        return {'pass':not reasons and confidence>=.64,'version':self.version,'confidence':round(confidence,4),'reasons':reasons,
                'root_component_count':components,'child_count':len(parts),'detached_partition':detached,
                'reconstruction_error':round(reconstruction_error,6),'overlap_error':round(overlap_error,6),
                'skeleton_pixel_count':int(skeleton.sum()),'skeleton_endpoint_count':int(np.count_nonzero(endpoints)),
                'skeleton_branch_count':int(np.count_nonzero(branches)),'skeleton_cut_fraction':round(skeleton_cut_fraction,6),
                'branch_damage_fraction':round(branch_damage_fraction,6),'artificial_seam_fraction':round(seam_length_fraction,6)}


def _bbox_gap(a:dict,b:dict)->float:
    ax1,ay1,aw,ah=a['x'],a['y'],a['w'],a['h'];bx1,by1,bw,bh=b['x'],b['y'],b['w'],b['h']
    dx=max(0,max(ax1,bx1)-min(ax1+aw,bx1+bw))
    dy=max(0,max(ay1,by1)-min(ay1+ah,by1+bh))
    return math.hypot(dx,dy)


def _raw_components(mask:np.ndarray):
    n,labels,stats,cent=cv2.connectedComponentsWithStats((mask>0).astype(np.uint8),8)
    rows=[]
    for i in range(1,n):
        x,y,w,h,area=[int(v) for v in stats[i]]
        rows.append({'label':i,'x':x,'y':y,'w':w,'h':h,'area':area,'cx':float(cent[i][0]),'cy':float(cent[i][1])})
    return rows,labels


def _union_mask(labels:np.ndarray, ids:list[int])->np.ndarray:
    return (np.isin(labels,ids).astype(np.uint8)*255)


def _row_from_mask(mask:np.ndarray)->dict|None:
    yy,xx=np.where(mask>0)
    if len(xx)<24:return None
    x0=int(xx.min());x1=int(xx.max())+1;y0=int(yy.min());y1=int(yy.max())+1
    return {'x':x0,'y':y0,'w':x1-x0,'h':y1-y0,'area':int(len(xx)),'cx':float(xx.mean()),'cy':float(yy.mean())}


def _projection_cut(mask:np.ndarray, axis:int)->dict|None:
    """Find a strong sparse neck in one connected composite without inventing pixels."""
    yy,xx=np.where(mask>0)
    if len(xx)<120:return None
    x0,x1=int(xx.min()),int(xx.max())+1;y0,y1=int(yy.min()),int(yy.max())+1
    sub=(mask[y0:y1,x0:x1]>0)
    proj=sub.sum(axis=0 if axis==0 else 1).astype(np.float64);n=len(proj)
    if n<28:return None
    k=max(3,int(round(n*0.02)));k+=1-k%2
    sm=np.convolve(proj,np.ones(k,dtype=np.float64)/k,mode='same')
    lo=max(5,int(n*0.16));hi=min(n-5,int(n*0.84))
    if hi<=lo:return None
    peak=max(1.0,float(np.percentile(sm,90)));total=float(np.count_nonzero(sub));best=None
    for i in sorted(range(lo,hi),key=lambda q:sm[q])[:max(8,int(n*0.14))]:
        valley=float(sm[i]/peak)
        if valley>0.24:continue
        if axis==0:
            a=float(np.count_nonzero(sub[:,:i]));b=float(np.count_nonzero(sub[:,i:]))
            corridor=float(np.count_nonzero(sub[:,max(0,i-k//2):min(n,i+k//2+1)]))/max(1.0,sub.shape[0]*(k+1))
        else:
            a=float(np.count_nonzero(sub[:i,:]));b=float(np.count_nonzero(sub[i:,:]))
            corridor=float(np.count_nonzero(sub[max(0,i-k//2):min(n,i+k//2+1),:]))/max(1.0,sub.shape[1]*(k+1))
        if min(a,b)<max(80.0,total*0.13):continue
        balance=min(a,b)/max(a,b)
        if corridor>0.19:continue
        score=(1.0-valley)*0.50+balance*0.30+(1.0-corridor)*0.20
        if best is None or score>best['score']:
            best={'score':score,'axis':axis,'index':i,'x0':x0,'y0':y0,'valley_ratio':valley,'corridor_occupancy':corridor,'balance':balance}
    return best


def _split_projection_once(mask:np.ndarray)->tuple[list[np.ndarray],dict]|None:
    yy,xx=np.where(mask>0)
    if len(xx)<120:return None
    bw=int(xx.max())-int(xx.min())+1;bh=int(yy.max())-int(yy.min())+1
    axes=[0,1] if 0.62<=bw/max(1,bh)<=1.62 else ([0] if bw>bh else [1])
    choices=[c for c in (_projection_cut(mask,a) for a in axes) if c]
    if not choices:return None
    c=max(choices,key=lambda d:d['score']);a=np.zeros_like(mask);b=np.zeros_like(mask)
    if c['axis']==0:
        cut=c['x0']+c['index'];a[:,:cut]=mask[:,:cut];b[:,cut:]=mask[:,cut:]
    else:
        cut=c['y0']+c['index'];a[:cut,:]=mask[:cut,:];b[cut:,:]=mask[cut:,:]
    if np.count_nonzero(a)<80 or np.count_nonzero(b)<80:return None
    return [a,b],c


def _projection_children(mask:np.ndarray,max_children:int)->tuple[list[np.ndarray],list[dict]]:
    masks=[(mask>0).astype(np.uint8)*255];evidence=[]
    while len(masks)<max(2,max_children):
        cand=[]
        for i,m in enumerate(masks):
            r=_split_projection_once(m)
            if r:cand.append((r[1]['score'],i,r))
        if not cand:break
        _,i,(parts,ev)=max(cand,key=lambda z:z[0]);masks.pop(i);masks[i:i]=parts;evidence.append(ev)
    return masks,evidence




def _color_watershed_children(mask:np.ndarray,rgb:np.ndarray|None,max_children:int)->tuple[list[np.ndarray],list[dict]]:
    """Conservative color+geometry watershed for connected illustrated objects.

    It is intentionally never translation-safe by itself: a color boundary inside
    a flat illustration proves a useful sub-object reveal boundary, not hidden-pixel
    availability. The method exists to recover screen/coin/button/indicator style
    internal parts that binary connected components cannot see.
    """
    if rgb is None:return [],[]
    b=(mask>0).astype(np.uint8);total=int(b.sum())
    if total<420:return [],[]
    yy,xx=np.where(b>0);x0,x1=int(xx.min()),int(xx.max())+1;y0,y1=int(yy.min()),int(yy.max())+1
    roi=b[y0:y1,x0:x1]; img=rgb[y0:y1,x0:x1]
    if min(roi.shape)<24:return [],[]
    dist=cv2.distanceTransform(roi,cv2.DIST_L2,5)
    mx=float(dist.max())
    if mx<2.2:return [],[]
    # Stable interior seeds from local distance maxima. Higher thresholds are tried
    # first; this strongly resists splitting every shaded facet of a 3D icon.
    candidates=[]
    for frac in (0.48,0.42,0.36,0.31):
        peak=(dist>=mx*frac).astype(np.uint8)
        peak=cv2.morphologyEx(peak,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3)))
        n,lab,stats,cent=cv2.connectedComponentsWithStats(peak,8)
        seeds=[]
        for i in range(1,n):
            area=int(stats[i,cv2.CC_STAT_AREA])
            if area>=max(12,int(total*0.010)):
                seeds.append(i)
        if 2<=len(seeds)<=max_children:
            balance=min(int(stats[i,cv2.CC_STAT_AREA]) for i in seeds)/max(int(stats[i,cv2.CC_STAT_AREA]) for i in seeds)
            if balance>=0.10:candidates.append((frac,seeds,lab,stats,balance))
    if not candidates:return [],[]
    frac,seeds,seed_labels,stats,balance=max(candidates,key=lambda z:(z[0],z[4]))

    # Watershed image combines Lab chroma/luma gradient with outline gradient.
    labimg=cv2.cvtColor(img,cv2.COLOR_RGB2LAB)
    gray=cv2.cvtColor(img,cv2.COLOR_RGB2GRAY)
    def grad(ch):
        gx=cv2.Sobel(ch,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(ch,cv2.CV_32F,0,1,ksize=3)
        return cv2.magnitude(gx,gy)
    g=grad(gray)*0.45+grad(labimg[:,:,0])*0.25+grad(labimg[:,:,1])*0.15+grad(labimg[:,:,2])*0.15
    g=cv2.GaussianBlur(g,(0,0),0.8)
    if float(g.max())>1e-6:g=(g/g.max()*255.0).astype(np.uint8)
    else:g=np.zeros_like(gray)
    wsimg=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
    markers=np.zeros(roi.shape,np.int32)
    markers[roi==0]=1
    for j,seed_id in enumerate(seeds,2):markers[seed_labels==seed_id]=j
    # Unknown foreground remains zero and is assigned by watershed.
    cv2.watershed(wsimg,markers)
    masks=[]
    for j in range(2,2+len(seeds)):
        cm=((markers==j)&(roi>0)).astype(np.uint8)*255
        # Watershed boundary pixels (-1) are assigned after all regions exist.
        if np.count_nonzero(cm)>=max(70,int(total*0.065)):
            full=np.zeros_like(mask);full[y0:y1,x0:x1]=cm;masks.append(full)
    if len(masks)<2:return [],[]
    # Assign unclaimed original foreground to nearest child using distance transforms,
    # preserving an exact partition of source pixels.
    claimed=np.zeros_like(mask,dtype=np.uint8)
    for m in masks:claimed|=(m>0).astype(np.uint8)
    missing=(b>0)&(claimed==0)
    if np.any(missing):
        dmaps=[]
        for m in masks:
            inv=(m==0).astype(np.uint8);dmaps.append(cv2.distanceTransform(inv,cv2.DIST_L2,5))
        stack=np.stack(dmaps,axis=2);owner=np.argmin(stack,axis=2)
        for j,m in enumerate(masks):m[(missing)&(owner==j)]=255
    areas=[int(np.count_nonzero(m)) for m in masks]
    amin=min(areas)/float(total);amax=max(areas)/float(total)
    if amin<0.065 or amax>0.86:return [],[]
    # Boundary evidence: accepted splits should pass through a meaningful physical
    # color/outline gradient, not a visually uniform body.
    boundary=np.zeros_like(roi,np.uint8)
    local_owner=np.full(roi.shape,-1,np.int16)
    for j,m in enumerate(masks):local_owner[(m[y0:y1,x0:x1]>0)]=j
    boundary[:,1:]|=((local_owner[:,1:]!=local_owner[:,:-1])&(local_owner[:,1:]>=0)&(local_owner[:,:-1]>=0)).astype(np.uint8)
    boundary[1:,:]|=((local_owner[1:,:]!=local_owner[:-1,:])&(local_owner[1:,:]>=0)&(local_owner[:-1,:]>=0)).astype(np.uint8)
    bg_grad=float(np.median(g[roi>0])) if np.any(roi>0) else 0.0
    edge_grad=float(np.mean(g[boundary>0])) if np.any(boundary>0) else 0.0
    strength=edge_grad/max(1.0,bg_grad)
    if strength<1.08:return [],[]
    evidence=[{'method':'COLOR_GEOMETRIC_WATERSHED','seed_fraction':round(float(frac),3),'seed_count':len(seeds),'area_min_fraction':round(amin,4),'area_max_fraction':round(amax,4),'boundary_gradient_ratio':round(strength,4),'seed_balance':round(float(balance),4)}]
    return masks,evidence


def _morphological_neck_children(mask:np.ndarray,max_children:int)->tuple[list[np.ndarray],list[dict]]:
    """Split connected lobes at thin necks using physical morphology, then repartition original pixels.

    The opened image is used only to find robust seed lobes. Every output child receives original
    source pixels via nearest-seed assignment, so the union of children exactly covers the original
    foreground. These children are reveal-safe, but never translation-safe by default because a
    removed connector/occlusion may otherwise expose a seam.
    """
    binary=(mask>0).astype(np.uint8);total=int(binary.sum())
    if total<220:return [],[]
    yy,xx=np.where(binary>0);bw=int(xx.max()-xx.min()+1);bh=int(yy.max()-yy.min()+1);short=max(8,min(bw,bh))
    candidates=[]
    for frac in (0.010,0.014,0.018,0.024,0.030):
        k=max(3,int(round(short*frac)));k+=1-k%2
        ker=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(k,k));opened=cv2.morphologyEx(binary,cv2.MORPH_OPEN,ker)
        n,labels,stats,cent=cv2.connectedComponentsWithStats(opened,8)
        seeds=[]
        for i in range(1,n):
            area=int(stats[i,cv2.CC_STAT_AREA])
            if area>=max(55,int(total*0.09)):
                seeds.append({'label':i,'area':area,'cx':float(cent[i][0]),'cy':float(cent[i][1])})
        if not (2<=len(seeds)<=max_children):continue
        retained=float(opened.sum())/max(1.0,float(total))
        if retained<0.72:continue
        balance=min(s['area'] for s in seeds)/max(s['area'] for s in seeds)
        if balance<0.18:continue
        score=0.58*retained+0.26*balance+0.16*(1.0-min(1.0,(k/short)*12.0))
        candidates.append((score,k,seeds,labels,retained,balance))
    if not candidates:return [],[]
    score,k,seeds,labels,retained,balance=max(candidates,key=lambda z:z[0])
    centers=np.asarray([[s['cx'],s['cy']] for s in seeds],dtype=np.float64)
    fy,fx=np.where(binary>0);pts=np.stack([fx,fy],axis=1).astype(np.float64)
    # nearest physical seed center; only used on pixels not retained by opening, preserving exact union
    d=((pts[:,None,:]-centers[None,:,:])**2).sum(axis=2);owner=d.argmin(axis=1)
    out=[]
    for j in range(len(seeds)):
        cm=np.zeros_like(binary,dtype=np.uint8);pick=(owner==j);cm[fy[pick],fx[pick]]=255;out.append(cm)
    evidence=[{'method':'MORPHOLOGICAL_NECK_SEEDS','kernel':k,'seed_count':len(seeds),'retained_ratio':round(retained,4),'balance':round(balance,4),'score':round(score,4)}]
    return out,evidence


def _assign_role(idx:int,count:int,area_rank:int,semantic_type:str,dominant_axis:str,area_fraction:float=0.0)->str:
    """Assign an animation role without pretending spatial order is semantic truth.

    The dominant physical body of a composite is CONTEXT. Smaller detached/revealable lobes
    become ACTOR/TARGET/RESULT in stable visual order. This makes machines/phones/systems keep
    their shell still while movable details carry the story.
    """
    typ=str(semantic_type or '').upper()
    if typ in {'STATUS','NUMBER','PRICE','LABEL'}:
        return 'RESULT'
    # Largest/dominant lobe is usually the visual body/context, not the thing that should travel.
    if area_rank==0 and (area_fraction>=0.42 or count>=3):
        return 'CONTEXT'
    if count==2:
        return 'ACTOR' if area_rank>0 else 'CONTEXT'
    # Among non-context pieces, preserve visual order as a neutral animation sentence.
    if idx==0:return 'ACTOR'
    if idx==count-1:return 'RESULT'
    return 'TARGET'


def decompose_semantic_group(mask:np.ndarray,*,W:int,H:int,semantic_type:str='',semantic_role:str='',max_children:int=4,rgb:np.ndarray|None=None)->dict:
    """Hierarchical animation decomposition with explicit translation/reveal safety.

    V31 distinguishes *what can be isolated* from *what can safely travel*. Detached lobes may be
    translated; connected lobes discovered through projection/morphology are reveal-only. This
    avoids the V26 failure mode where a technically separated child moved away and exposed a seam.
    """
    rows,labels=_raw_components(mask);total=max(1,int(np.count_nonzero(mask)));diag=math.hypot(W,H)
    evidence=[];mode='NONE';children=[]
    min_major=max(70,int(total*0.065),int(W*H*0.00055))
    majors=[r for r in rows if r['area']>=min_major and r['w']>=max(5,int(W*0.015)) and r['h']>=max(5,int(H*0.015))]
    if len(majors)>=2:
        mode='DETACHED_LOBES';majors=sorted(majors,key=lambda r:r['area'],reverse=True)[:max_children];groups={m['label']:[m['label']] for m in majors};major_ids=set(groups)
        for r in rows:
            if r['label'] in major_ids:continue
            nearest=min(majors,key=lambda m:_bbox_gap(r,m))
            if _bbox_gap(r,nearest)<=0.050*diag or r['area']<total*0.025:groups[nearest['label']].append(r['label'])
        for ids in groups.values():
            cm=_union_mask(labels,ids);row=_row_from_mask(cm)
            if row:children.append((row,cm))
    else:
        masks,we=_color_watershed_children(mask,rgb,max_children)
        if len(masks)>=2 and we:
            mode='COLOR_GEOMETRIC_WATERSHED';evidence.extend(we)
            for cm in masks:
                row=_row_from_mask(cm)
                if row:children.append((row,cm))
        if len(children)<2:
            masks,pe=_projection_children(mask,max_children)
            if len(masks)>=2 and pe:
                mode='THIN_CONNECTOR_LOBES';evidence.extend(pe);children=[]
                for cm in masks:
                    row=_row_from_mask(cm)
                    if row:children.append((row,cm))
        if len(children)<2:
            masks,me=_morphological_neck_children(mask,max_children)
            if len(masks)>=2:
                mode='MORPHOLOGICAL_SUBOBJECTS';evidence.extend(me);children=[]
                for cm in masks:
                    row=_row_from_mask(cm)
                    if row:children.append((row,cm))
    if len(children)<2:return {'accepted':False,'reason':'NO_ANIMATABLE_SUBOBJECT_DECOMPOSITION','children':[],'confidence':0.0,'decomposition_mode':'NONE','evidence':evidence}
    children=sorted(children,key=lambda z:(z[0]['cx'],z[0]['cy']))
    topology=TopologicalDecompositionValidator().validate(mask,[cm for _,cm in children],mode)
    evidence.append({'method':'TOPOLOGICAL_DECOMPOSITION_VALIDATION',**topology})
    if not topology['pass']:
        return {'accepted':False,'reason':'TOPOLOGY_VALIDATION_FAILED','children':[],'confidence':topology['confidence'],'decomposition_mode':mode,'evidence':evidence,'topology_validation':topology}
    min_gap=999999.0;max_center=0.0
    for i in range(len(children)):
        for j in range(i+1,len(children)):
            a,b=children[i][0],children[j][0];gap=_bbox_gap(a,b);min_gap=min(min_gap,gap);max_center=max(max_center,math.hypot(a['cx']-b['cx'],a['cy']-b['cy']))
    coverage=sum(c[0]['area'] for c in children)/float(total);min_fraction=min(c[0]['area']/float(total) for c in children);dominant=max(c[0]['area']/float(total) for c in children)
    if coverage<0.96:return {'accepted':False,'reason':'PARTITION_DOES_NOT_COVER_SOURCE','children':[],'confidence':0.0,'decomposition_mode':mode}
    if min_fraction<0.055 or dominant>0.88:return {'accepted':False,'reason':'UNBALANCED_CHILDREN','children':[],'confidence':0.0,'decomposition_mode':mode}
    if max_center<0.060*diag:return {'accepted':False,'reason':'INSUFFICIENT_SPATIAL_SEPARATION','children':[],'confidence':0.0,'decomposition_mode':mode}
    separation=min(1.0,max_center/(0.28*diag));gap_score=min(1.0,max(0.0,min_gap)/(0.045*diag)) if min_gap<999999 else 0.0;balance=1.0-max(0.0,dominant-0.50)/0.50
    if mode=='DETACHED_LOBES':confidence=max(0.0,min(1.0,0.43*coverage+0.31*separation+0.16*balance+0.10*gap_score))
    elif mode in {'THIN_CONNECTOR_LOBES','COLOR_GEOMETRIC_WATERSHED'}:
        if mode=='COLOR_GEOMETRIC_WATERSHED':
            ev=evidence[0] if evidence else {};edge=min(1.0,max(0.0,(float(ev.get('boundary_gradient_ratio',1.0))-1.0)/0.8));seedbal=float(ev.get('seed_balance',0.5));confidence=max(0.0,min(1.0,0.34*coverage+0.20*separation+0.14*balance+0.20*edge+0.12*seedbal))
        else:
            valley=sum(1.0-float(e.get('valley_ratio',1.0)) for e in evidence if 'valley_ratio' in e)/max(1,sum(1 for e in evidence if 'valley_ratio' in e));corr=sum(1.0-float(e.get('corridor_occupancy',1.0)) for e in evidence if 'corridor_occupancy' in e)/max(1,sum(1 for e in evidence if 'corridor_occupancy' in e));confidence=max(0.0,min(1.0,0.34*coverage+0.22*separation+0.14*balance+0.18*valley+0.12*corr))
    else:
        ev=evidence[0] if evidence else {};confidence=max(0.0,min(1.0,0.35*coverage+0.22*separation+0.14*balance+0.18*float(ev.get('retained_ratio',0.75))+0.11*float(ev.get('balance',0.5))))
    if confidence<0.64:return {'accepted':False,'reason':'CONFIDENCE_BELOW_THRESHOLD','children':[],'confidence':round(confidence,4),'decomposition_mode':mode}
    xs=[c[0]['cx'] for c in children];ys=[c[0]['cy'] for c in children];dominant_axis='X' if (max(xs)-min(xs))/max(1,W)>=(max(ys)-min(ys))/max(1,H) else 'Y';ordered=sorted(children,key=lambda z:z[0]['cx'] if dominant_axis=='X' else z[0]['cy'])
    area_rank={id(z):rank for rank,z in enumerate(sorted(children,key=lambda z:z[0]['area'],reverse=True))};out=[]
    for i,z in enumerate(ordered):
        row,cm=z;fraction=row['area']/float(total);role=_assign_role(i,len(ordered),area_rank.get(id(z),i),semantic_type,dominant_axis,fraction)
        detached=mode=='DETACHED_LOBES';translate_safe=bool(detached and min_gap>=max(2.0,0.006*diag) and fraction>=0.075 and row['w']/W<=0.58 and row['h']/H<=0.76)
        reveal_safe=bool(fraction>=0.055 and row['w']/W<=0.80 and row['h']/H<=0.88)
        animation_mode='TRANSLATE_SAFE' if translate_safe else ('REVEAL_ONLY' if reveal_safe else 'GROUP_ONLY')
        occlusion='CLEAN_SEPARABLE' if translate_safe else ('CONNECTED_REVEAL_ONLY' if mode!='DETACHED_LOBES' else 'NEAR_TOUCH_REVEAL_ONLY')
        out.append(HierarchyChild(i+1,(row['x'],row['y'],row['w'],row['h']),row['area'],(round(row['cx']/W,6),round(row['cy']/H,6)),(round(row['x']/W,6),round(row['y']/H,6),round(row['w']/W,6),round(row['h']/H,6)),round(confidence,4),translate_safe,reveal_safe,animation_mode,occlusion,role,cm))
    return {'accepted':True,'reason':mode,'children':out,'confidence':round(confidence,4),'dominant_axis':dominant_axis,'coverage':round(coverage,4),'decomposition_mode':mode,'evidence':evidence,'topology_validation':topology,'translation_safe_children':sum(1 for c in out if c.animation_safe),'reveal_only_children':sum(1 for c in out if c.reveal_safe and not c.animation_safe)}


def serialize_child(child:HierarchyChild)->dict[str,Any]:
    d=asdict(child);d.pop('mask',None);return d
