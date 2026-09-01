from __future__ import annotations
import cv2,numpy as np

MASK_VALIDATION_VERSION='FOUNDATION_MASK_VALIDATION_1.0'

def bbox_from_mask(mask):
    yy,xx=np.where(mask>0)
    return None if not len(xx) else (int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1))

def _iou_box(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b;ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by));inter=ix*iy
    return inter/max(1,aw*ah+bw*bh-inter)

def validate_mask(mask,bbox,foreground_mask,other_masks=()):
    m=(np.asarray(mask)>0).astype(np.uint8);h,w=m.shape;area=int(m.sum());fraction=area/max(1,h*w);mb=bbox_from_mask(m)
    if not area:return False,'EMPTY_MASK',{}
    if fraction<.0015:return False,'TOO_SMALL',{'area_fraction':fraction}
    if fraction>.88:return False,'ROOT_DUPLICATE',{'area_fraction':fraction}
    if mb is None or _iou_box(mb,bbox)<.24:return False,'BBOX_MISMATCH',{'bbox':mb}
    n,_,stats,_=cv2.connectedComponentsWithStats(m,8);substantial=sum(int(stats[i,cv2.CC_STAT_AREA])>=max(10,int(area*.04)) for i in range(1,n))
    if substantial>5:return False,'MASK_FRAGMENTED',{'component_count':substantial}
    fg_overlap=int(np.count_nonzero((m>0)&(foreground_mask>0)))/max(1,area)
    if fg_overlap<.58:return False,'WHITE_STAGE_LEAK',{'foreground_overlap':fg_overlap}
    for old in other_masks:
        inter=int(np.count_nonzero((m>0)&(old>0)));union=int(np.count_nonzero((m>0)|(old>0)))
        if inter/max(1,union)>.84:return False,'EXCESSIVE_OVERLAP',{'overlap_iou':inter/max(1,union)}
    edge=bool(np.any(m[0]) or np.any(m[-1]) or np.any(m[:,0]) or np.any(m[:,-1]))
    return True,None,{'area_fraction':round(fraction,6),'foreground_overlap':round(fg_overlap,6),'bbox':mb,'edge_touch':edge,'component_count':substantial}
