from __future__ import annotations
import pathlib
import numpy as np
from PIL import Image

ACTOR_QA_VERSION='HEXA_FOUNDATION_ACTOR_QA_1.0'

def _iou(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b;ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by));inter=ix*iy
    return inter/max(1,aw*ah+bw*bh-inter)

def actor_qa(actors,rejected=()):
    failures=[];seen=[]
    for actor in actors:
        pid=str(actor.get('physical_id'));path=pathlib.Path(str(actor.get('layer_path') or ''))
        if not path.is_file():failures.append({'physical_id':pid,'reason':'RGBA_CUTOUT_MISSING'});continue
        alpha=np.array(Image.open(path).convert('RGBA'))[:,:,3];yy,xx=np.where(alpha>4)
        if not len(xx):failures.append({'physical_id':pid,'reason':'EMPTY_ACTOR'});continue
        actual=(int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1));declared=tuple(actor.get('bbox') or (0,0,0,0))
        if _iou(actual,declared)<.7:failures.append({'physical_id':pid,'reason':'BBOX_ALPHA_DISAGREEMENT'})
        if float((actor.get('matting') or {}).get('opaque_stage_leak_fraction',0))>.004:failures.append({'physical_id':pid,'reason':'WHITE_STAGE_LEAK'})
        for old_id,old_box in seen:
            if _iou(actual,old_box)>.9:failures.append({'physical_id':pid,'reason':'NEAR_DUPLICATE_ACTOR','duplicate_of':old_id})
        seen.append((pid,actual))
    return {'schema':'HEXA_FOUNDATION_ACTOR_QA','version':ACTOR_QA_VERSION,'pass':not failures,'accepted_actor_count':len(actors),'motion_addressable_actor_count':sum(bool(x.get('translation_safe_after_occlusion',x.get('translation_safe'))) for x in actors),'rejected_actor_count':len(rejected),'failures':failures,'white_stage_limit':.004}
