from __future__ import annotations
import cv2,numpy as np

ACTOR_VALIDATION_VERSION='FOUNDATION_ACTOR_VALIDATION_1.0'

def classify_actor(mask,all_foreground,validation):
    m=np.asarray(mask)>0;fg=np.asarray(all_foreground)>0
    # Missing pixels inside a candidate bbox imply hidden/occluded source content.
    x,y,w,h=validation['bbox'];crop=m[y:y+h,x:x+w];fill=float(np.count_nonzero(crop))/max(1,w*h)
    other=fg&(~m);dilated=cv2.dilate(m.astype(np.uint8),np.ones((5,5),np.uint8),iterations=1)>0
    contact=float(np.count_nonzero(dilated&other))/max(1,np.count_nonzero(m))
    touches_other=bool(contact>.025 and fill>.62)
    if touches_other:return {'safety_class':'ATOMIC_PARENT_DEPENDENT','animation_safe':False,'translation_safe':False,'reveal_safe':True,'scale_safe':True,'rotation_safe':False,'rejection_reason':None}
    return {'safety_class':'INDEPENDENT_ACTOR','animation_safe':True,'translation_safe':True,'reveal_safe':True,'scale_safe':True,'rotation_safe':not validation.get('edge_touch',False),'rejection_reason':None}
