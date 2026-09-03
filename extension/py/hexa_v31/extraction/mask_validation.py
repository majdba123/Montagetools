from __future__ import annotations
import cv2,numpy as np

MASK_VALIDATION_VERSION='FOUNDATION_MASK_VALIDATION_1.1_CROP_ENVELOPE'

def bbox_from_mask(mask):
    yy,xx=np.where(mask>0)
    return None if not len(xx) else (int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1))

def _intersection(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    x1=max(ax,bx);y1=max(ay,by);x2=min(ax+aw,bx+bw);y2=min(ay+ah,by+bh)
    return max(0,x2-x1)*max(0,y2-y1)

def _iou_box(a,b):
    inter=_intersection(a,b)
    return inter/max(1,a[2]*a[3]+b[2]*b[3]-inter)

def _envelope_metrics(mask,mask_bbox,candidate_bbox):
    m=np.asarray(mask)>0;h,w=m.shape
    cx,cy,cw,ch=[int(v) for v in candidate_bbox]
    if cw<=0 or ch<=0 or mask_bbox is None:
        return {'bbox_iou':0.0,'candidate_bbox_coverage':0.0,'mask_bbox_containment':0.0,'mask_outside_candidate_fraction':1.0,'bbox_center_distance_norm':1.0}
    inter=_intersection(mask_bbox,(cx,cy,cw,ch))
    area=max(1,int(np.count_nonzero(m)))
    pad=max(2,int(round(max(cw,ch)*.08)))
    x0=max(0,cx-pad);y0=max(0,cy-pad);x1=min(w,cx+cw+pad);y1=min(h,cy+ch+pad)
    allowed=np.zeros((h,w),dtype=bool);allowed[y0:y1,x0:x1]=True
    outside=int(np.count_nonzero(m&(~allowed)))/float(area)
    mx,my,mw,mh=mask_bbox
    mcx=mx+mw/2.0;mcy=my+mh/2.0;ccx=cx+cw/2.0;ccy=cy+ch/2.0
    diag=max(1.0,float((cw*cw+ch*ch)**.5))
    return {
        'bbox_iou':round(_iou_box(mask_bbox,(cx,cy,cw,ch)),6),
        'candidate_bbox_coverage':round(inter/float(max(1,cw*ch)),6),
        'mask_bbox_containment':round(inter/float(max(1,mw*mh)),6),
        'mask_outside_candidate_fraction':round(outside,6),
        'bbox_center_distance_norm':round(float(((mcx-ccx)**2+(mcy-ccy)**2)**.5)/diag,6),
    }

def validate_mask(mask,bbox,foreground_mask,other_masks=()):
    m=(np.asarray(mask)>0).astype(np.uint8);h,w=m.shape;area=int(m.sum());fraction=area/max(1,h*w);mb=bbox_from_mask(m)
    if not area:return False,'EMPTY_MASK',{}
    metrics=_envelope_metrics(m,mb,bbox)
    base={'area_fraction':round(fraction,6),'bbox':mb,'candidate_bbox':list(bbox),**metrics}
    if fraction<.0015:return False,'TOO_SMALL',base
    if fraction>.88:return False,'ROOT_DUPLICATE',base
    if mb is None or float(metrics['bbox_iou'])<.24:return False,'BBOX_MISMATCH',base
    if float(metrics['mask_outside_candidate_fraction'])>.30:return False,'MASK_ESCAPES_CANDIDATE_ENVELOPE',base
    n,_,stats,_=cv2.connectedComponentsWithStats(m,8);substantial=sum(int(stats[i,cv2.CC_STAT_AREA])>=max(10,int(area*.04)) for i in range(1,n))
    base['component_count']=substantial
    if substantial>5:return False,'MASK_FRAGMENTED',base
    fg_overlap=int(np.count_nonzero((m>0)&(foreground_mask>0)))/max(1,area)
    base['foreground_overlap']=round(fg_overlap,6)
    if fg_overlap<.58:return False,'WHITE_STAGE_LEAK',base
    overlap_max=0.0
    for old in other_masks:
        inter=int(np.count_nonzero((m>0)&(old>0)));union=int(np.count_nonzero((m>0)|(old>0)))
        overlap_max=max(overlap_max,inter/max(1,union))
    base['other_mask_iou_max']=round(overlap_max,6)
    if overlap_max>.84:return False,'EXCESSIVE_OVERLAP',base
    edge=bool(np.any(m[0]) or np.any(m[-1]) or np.any(m[:,-1]));base['edge_touch']=edge
    return True,None,base
