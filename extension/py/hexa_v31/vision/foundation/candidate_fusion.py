from __future__ import annotations
from .contracts import SemanticObjectCandidate

FUSION_VERSION='FOUNDATION_CANDIDATE_FUSION_1.0'
MEANINGLESS={'background','image','illustration','graphic','pattern','decoration','shape'}

def _iou(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by));inter=ix*iy
    return inter/max(1,aw*ah+bw*bh-inter)

def fuse_candidates(rows,image_size,min_area_fraction=.0015,max_area_fraction=.88):
    w,h=image_size; accepted=[];rejected=[]
    normalized=[]
    for i,row in enumerate(rows):
        label=str(row.get('semantic_label') or row.get('label') or '').strip().lower()
        bbox=tuple(int(round(x)) for x in row.get('bbox',[0,0,0,0]));area=bbox[2]*bbox[3]/max(1,w*h);conf=float(row.get('confidence',0))
        reason=None
        if not label or label in MEANINGLESS:reason='LOW_SEMANTIC_VALUE'
        elif conf<.28:reason='LOW_CONFIDENCE'
        elif area<min_area_fraction:reason='TOO_SMALL'
        elif area>max_area_fraction:reason='ROOT_DUPLICATE'
        if reason:rejected.append(dict(row,rejection_reason=reason));continue
        normalized.append(SemanticObjectCandidate(str(row.get('candidate_id') or f'FV_{i+1:03d}'),label,str(row.get('description') or label),conf,bbox,str(row.get('source') or 'FLORENCE'),row.get('semantic_role'),row.get('parent_id'),tuple(row.get('signals') or ())))
    for cand in sorted(normalized,key=lambda x:(-x.confidence,-x.bbox[2]*x.bbox[3],x.candidate_id)):
        duplicate=next((old for old in accepted if _iou(old.bbox,cand.bbox)>=.78 and (old.semantic_label==cand.semantic_label or _iou(old.bbox,cand.bbox)>=.9)),None)
        if duplicate:
            rejected.append(dict(cand.to_dict(),rejection_reason='DUPLICATE'));continue
        accepted.append(cand)
    return accepted,rejected
