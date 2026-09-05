from __future__ import annotations
import cv2,numpy as np

ACTOR_VALIDATION_VERSION='FOUNDATION_ACTOR_VALIDATION_1.1_BOUNDARY_CONTACT'

def classify_actor(mask,all_foreground,validation,foreign_candidate_overlap_fraction=0.0):
    m=np.asarray(mask)>0;fg=np.asarray(all_foreground)>0
    x,y,w,h=validation['bbox'];crop=m[y:y+h,x:x+w];fill=float(np.count_nonzero(crop))/max(1,w*h)
    other=fg&(~m)
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    outer=(cv2.dilate(m.astype(np.uint8),kernel,iterations=1)>0)&(~m)
    eroded=cv2.erode(m.astype(np.uint8),kernel,iterations=1)>0
    boundary=m&(~eroded)
    contact_pixels=int(np.count_nonzero(outer&other))
    boundary_contact=contact_pixels/max(1,int(np.count_nonzero(boundary)))
    area_contact=contact_pixels/max(1,int(np.count_nonzero(m)))
    foreign=max(0.0,min(1.0,float(foreign_candidate_overlap_fraction or 0.0)))
    edge=bool(validation.get('edge_touch'))
    escape=float(validation.get('mask_outside_candidate_fraction') or 0.0)
    reasons=[]
    if edge:reasons.append('SOURCE_CANVAS_EDGE_CLIPPED')
    if boundary_contact>.035 or area_contact>.010:reasons.append('PHYSICAL_FOREGROUND_CONTACT')
    if foreign>.18:reasons.append('FOREIGN_CANDIDATE_CONTACT')
    if escape>.10:reasons.append('CANDIDATE_ENVELOPE_UNCERTAIN')
    confidence=1.0
    confidence-=min(.55,boundary_contact*1.8)
    confidence-=min(.30,area_contact*8.0)
    confidence-=min(.35,foreign*.9)
    confidence-=min(.25,escape*.8)
    if edge:confidence-=.25
    confidence=max(0.0,min(1.0,confidence))
    base={'boundary_contact_ratio':round(boundary_contact,6),'foreground_contact_fraction':round(area_contact,6),'foreign_candidate_overlap_fraction':round(foreign,6),'physical_independence_confidence':round(confidence,4),'independence_block_reasons':reasons,'source_bbox_fill_fraction':round(fill,6)}
    if reasons:
        return {'safety_class':'ATOMIC_PARENT_DEPENDENT','animation_safe':False,'translation_safe':False,'reveal_safe':True,'scale_safe':True,'rotation_safe':False,'rejection_reason':None,**base}
    return {'safety_class':'INDEPENDENT_ACTOR','animation_safe':True,'translation_safe':True,'reveal_safe':True,'scale_safe':True,'rotation_safe':True,'rejection_reason':None,**base}
