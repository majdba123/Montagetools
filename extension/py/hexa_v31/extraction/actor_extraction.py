from __future__ import annotations
import pathlib
import cv2,numpy as np
from PIL import Image
from .matting import refine_alpha
from .mask_validation import validate_mask
from .actor_validation import classify_actor

ACTOR_EXTRACTION_VERSION='FOUNDATION_ACTOR_EXTRACTION_1.1_CROP_QUALITY'

def _candidate_foreign_overlap(mask,candidates,current_id):
    m=np.asarray(mask)>0;area=max(1,int(np.count_nonzero(m)));h,w=m.shape;worst=0.0
    current=candidates.get(str(current_id),{})
    for cid,other in candidates.items():
        if str(cid)==str(current_id):continue
        if str(current.get('parent_id') or '')==str(cid) or str(other.get('parent_id') or '')==str(current_id):continue
        box=other.get('bbox') or [0,0,0,0]
        try:x,y,bw,bh=[int(v) for v in box]
        except Exception:continue
        x0=max(0,x);y0=max(0,y);x1=min(w,x+bw);y1=min(h,y+bh)
        if x1<=x0 or y1<=y0:continue
        worst=max(worst,float(np.count_nonzero(m[y0:y1,x0:x1]))/area)
    return round(worst,6)

def extract_foundation_actors(foundation_result,rgb,bg,foreground_mask,out_dir,final_out,start_index):
    accepted=[];rejected=[];alpha_by_id={};layers=[];accepted_masks=[]
    candidates={str(x.get('candidate_id')):x for x in foundation_result.get('candidates') or []}
    for mask_row in foundation_result.get('masks') or []:
        cid=str(mask_row.get('candidate_id'));cand=candidates.get(cid,{});path=pathlib.Path(str(mask_row.get('mask_path') or ''))
        if not path.is_file():rejected.append(dict(cand,rejection_reason='EMPTY_MASK'));continue
        raw=np.array(Image.open(path).convert('L'));bbox=tuple(int(v) for v in cand.get('bbox',[0,0,0,0]))
        ok,reason,evidence=validate_mask(raw,bbox,foreground_mask,accepted_masks)
        if not ok:rejected.append(dict(cand,rejection_reason=reason,validation=evidence));continue
        pid=f'FV_ACTOR_{start_index+len(accepted):02d}';hard=(raw>0).astype(np.uint8)*255
        alpha,clean,matte=refine_alpha(rgb,hard,bg,group_mask=hard)
        if float(matte.get('opaque_stage_leak_fraction',0))>.004:
            rejected.append(dict(cand,rejection_reason='WHITE_STAGE_LEAK',validation={**evidence,**matte}));continue
        foreign=_candidate_foreign_overlap(hard,candidates,cid)
        safety=classify_actor(alpha,foreground_mask,evidence,foreign)
        x,y,w,h=evidence['bbox'];rgba=np.dstack([clean,alpha])
        out_path=pathlib.Path(out_dir)/(pid+'.png');final_path=pathlib.Path(final_out)/(pid+'.png');Image.fromarray(rgba,'RGBA').save(out_path)
        semantic_conf=float(cand.get('confidence',0));physical_conf=float(safety.get('physical_independence_confidence',1.0))
        row={
            'physical_id':pid,'bbox':[x,y,w,h],'area_px':int(np.count_nonzero(alpha>4)),
            'center_norm':[round((x+w/2)/rgb.shape[1],6),round((y+h/2)/rgb.shape[0],6)],
            'bbox_norm':[round(x/rgb.shape[1],6),round(y/rgb.shape[0],6),round(w/rgb.shape[1],6),round(h/rgb.shape[0],6)],
            'mask_confidence':round(semantic_conf*.95,4),'edge_touch':bool(evidence.get('edge_touch')),
            'semantic_unit_id':cand.get('candidate_id'),'semantic_type':'FOUNDATION_OBJECT',
            'semantic_role':cand.get('semantic_role') or 'SUPPORTING','semantic_label':cand.get('semantic_label'),
            'semantic_description':cand.get('description'),'candidate_source':cand.get('source'),
            'candidate_bbox':list(bbox),'sam_score':float(mask_row.get('sam_score') or 0.0),
            'sam_bbox_agreement':float(mask_row.get('bbox_agreement') if mask_row.get('bbox_agreement') is not None else evidence.get('bbox_iou',0.0)),
            'foundation_mask_validation':evidence,'foreign_candidate_overlap_fraction':foreign,
            'hierarchy_level':1,'parent_semantic_unit_id':cand.get('parent_id'),'composition_slot_id':cand.get('candidate_id'),
            'subobject_role':'FOUNDATION_SEMANTIC_ACTOR','hierarchy_confidence':semantic_conf,
            'animation_mode':'TRANSLATE_SAFE' if safety['translation_safe'] else 'REVEAL_ONLY',
            'occlusion_class':safety['safety_class'],'matting':matte,'semantic_mapping_confidence':semantic_conf,
            'layer_path':str(final_path),'mask_path':str(final_path),'layer_canvas_mode':'FULL_SCENE_ALPHA_CANVAS',
            'layer_source_size_px':[rgb.shape[1],rgb.shape[0]],'crop_origin_px':[x,y],'crop_size_px':[w,h],
            'root_id':'ROOT_COMPOSITE','parent_id':'ROOT_COMPOSITE','child_id':'ROOT_COMPOSITE::'+pid,
            'visible_area':round(float(np.count_nonzero(alpha>4))/(rgb.shape[0]*rgb.shape[1]),6),
            'optical_center':[round((x+w/2)/rgb.shape[1],6),round((y+h/2)/rgb.shape[0],6)],
            'independence_confidence':round(min(semantic_conf,physical_conf),4),'reconstruction_error':0.0,
            **safety,
        }
        accepted.append(row);accepted_masks.append(alpha);alpha_by_id[pid]=alpha
        layers.append({'path':str(final_path),'origin_px':[0,0],'size_px':[rgb.shape[1],rgb.shape[0]],'content_origin_px':[x,y],'content_size_px':[w,h],'canvas_mode':'FULL_SCENE_ALPHA_CANVAS'})
    return accepted,rejected,alpha_by_id,layers
