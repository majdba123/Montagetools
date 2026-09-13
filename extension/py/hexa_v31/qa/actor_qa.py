from __future__ import annotations
import pathlib
import numpy as np
from PIL import Image

ACTOR_QA_VERSION='HEXA_FOUNDATION_ACTOR_QA_2.0_CROP_INDEPENDENCE'

BBOX_ALPHA_IOU_MIN=.70
CANDIDATE_BBOX_IOU_MIN=.42
CANDIDATE_ENVELOPE_COVERAGE_MIN=.38
MASK_ESCAPE_MAX=.10
SOURCE_FOREGROUND_PRECISION_MIN=.72
OPAQUE_STAGE_LEAK_MAX=.004
EXTREME_HALO_RISK_MAX=.80
TRANSLATION_HALO_RISK_MAX=.32
TRANSLATION_CONTACT_MAX=.035
TRANSLATION_FOREIGN_OVERLAP_MAX=.18

def _iou(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b;ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by));inter=ix*iy
    return inter/max(1,aw*ah+bw*bh-inter)

def actor_qa(actors,rejected=()):
    failures=[];seen=[];crop_failures=[];independence_failures=[];rows=[]
    for actor in actors:
        pid=str(actor.get('physical_id'));path=pathlib.Path(str(actor.get('layer_path') or ''));row={'physical_id':pid,'source_path':str(path)}
        if not path.is_file():
            f={'physical_id':pid,'reason':'RGBA_CUTOUT_MISSING'};failures.append(f);crop_failures.append(f);rows.append(row);continue
        rgba=np.array(Image.open(path).convert('RGBA'));alpha=rgba[:,:,3];hh,ww=alpha.shape;yy,xx=np.where(alpha>4)
        expected_size=actor.get('layer_source_size_px') or []
        row['layer_size_px']=[ww,hh];row['expected_layer_size_px']=list(expected_size)
        if len(expected_size)==2 and [ww,hh]!=[int(expected_size[0]),int(expected_size[1])]:
            f={'physical_id':pid,'reason':'LAYER_CANVAS_SIZE_MISMATCH','actual':[ww,hh],'expected':list(expected_size)};failures.append(f);crop_failures.append(f)
        if not len(xx):
            f={'physical_id':pid,'reason':'EMPTY_ACTOR'};failures.append(f);crop_failures.append(f);rows.append(row);continue
        actual=(int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1));declared=tuple(actor.get('bbox') or (0,0,0,0))
        alpha_iou=_iou(actual,declared);row['bbox_alpha_iou']=round(alpha_iou,6)
        if alpha_iou<BBOX_ALPHA_IOU_MIN:
            f={'physical_id':pid,'reason':'BBOX_ALPHA_DISAGREEMENT','value':round(alpha_iou,6)};failures.append(f);crop_failures.append(f)
        validation=actor.get('foundation_mask_validation') or {}
        bbox_iou=float(validation.get('bbox_iou',actor.get('sam_bbox_agreement') or 0.0))
        candidate_coverage=float(validation.get('candidate_bbox_coverage',1.0))
        escape=float(validation.get('mask_outside_candidate_fraction',0.0))
        foreground_precision=float(validation.get('foreground_overlap',1.0))
        sam_score=float(actor.get('sam_score') or 0.0)
        row.update({'candidate_bbox_iou':bbox_iou,'candidate_bbox_coverage':candidate_coverage,'mask_outside_candidate_fraction':escape,'source_foreground_precision':foreground_precision,'sam_score':sam_score})
        if validation and bbox_iou<CANDIDATE_BBOX_IOU_MIN:
            f={'physical_id':pid,'reason':'CANDIDATE_BBOX_AGREEMENT_LOW','value':round(bbox_iou,6)};failures.append(f);crop_failures.append(f)
        if validation and candidate_coverage<CANDIDATE_ENVELOPE_COVERAGE_MIN:
            f={'physical_id':pid,'reason':'CANDIDATE_ENVELOPE_COVERAGE_LOW','value':round(candidate_coverage,6)};failures.append(f);crop_failures.append(f)
        if validation and escape>MASK_ESCAPE_MAX:
            f={'physical_id':pid,'reason':'MASK_ESCAPES_CANDIDATE_ENVELOPE','value':round(escape,6)};failures.append(f);crop_failures.append(f)
        if validation and foreground_precision<SOURCE_FOREGROUND_PRECISION_MIN:
            f={'physical_id':pid,'reason':'SOURCE_FOREGROUND_PRECISION_LOW','value':round(foreground_precision,6)};failures.append(f);crop_failures.append(f)
        if actor.get('sam_score') is not None and sam_score<.35:
            f={'physical_id':pid,'reason':'SAM_MASK_CONFIDENCE_LOW','value':round(sam_score,6)};failures.append(f);crop_failures.append(f)
        matte=actor.get('matting') or {};stage=float(matte.get('opaque_stage_leak_fraction',0));halo=float(matte.get('edge_halo_risk',0))
        row.update({'opaque_stage_leak_fraction':stage,'edge_halo_risk':halo})
        if stage>OPAQUE_STAGE_LEAK_MAX:
            f={'physical_id':pid,'reason':'WHITE_STAGE_LEAK','value':stage};failures.append(f);crop_failures.append(f)
        if halo>EXTREME_HALO_RISK_MAX:
            f={'physical_id':pid,'reason':'EXTREME_EDGE_HALO_RISK','value':halo};failures.append(f);crop_failures.append(f)
        boundary_contact=float(actor.get('boundary_contact_ratio') or 0.0);foreign=float(actor.get('foreign_candidate_overlap_fraction') or 0.0)
        translation_safe=bool(actor.get('translation_safe_after_occlusion',actor.get('translation_safe')))
        row.update({'boundary_contact_ratio':boundary_contact,'foreign_candidate_overlap_fraction':foreign,'translation_safe_after_occlusion':translation_safe})
        unsafe_translation=translation_safe and (
            bool(actor.get('edge_touch')) or boundary_contact>TRANSLATION_CONTACT_MAX or
            foreign>TRANSLATION_FOREIGN_OVERLAP_MAX or halo>TRANSLATION_HALO_RISK_MAX or
            stage>OPAQUE_STAGE_LEAK_MAX or escape>.05
        )
        if unsafe_translation:
            f={'physical_id':pid,'reason':'UNSAFE_TRANSLATION_CLASSIFICATION','edge_touch':bool(actor.get('edge_touch')),'boundary_contact_ratio':boundary_contact,'foreign_candidate_overlap_fraction':foreign,'edge_halo_risk':halo,'mask_escape_fraction':escape}
            failures.append(f);independence_failures.append(f)
        for old_id,old_box in seen:
            if _iou(actual,old_box)>.90:
                f={'physical_id':pid,'reason':'NEAR_DUPLICATE_ACTOR','duplicate_of':old_id};failures.append(f);crop_failures.append(f)
        seen.append((pid,actual));rows.append(row)
    return {
        'schema':'HEXA_FOUNDATION_ACTOR_QA','version':ACTOR_QA_VERSION,'pass':not failures,
        'crop_quality_pass':not crop_failures,'independence_classification_pass':not independence_failures,
        'accepted_actor_count':len(actors),
        'motion_addressable_actor_count':sum(bool(x.get('translation_safe_after_occlusion',x.get('translation_safe'))) for x in actors),
        'rejected_actor_count':len(rejected),'failures':failures,'crop_failures':crop_failures,
        'independence_failures':independence_failures,'actors':rows,
        'thresholds':{
            'bbox_alpha_iou_min':BBOX_ALPHA_IOU_MIN,'candidate_bbox_iou_min':CANDIDATE_BBOX_IOU_MIN,
            'candidate_envelope_coverage_min':CANDIDATE_ENVELOPE_COVERAGE_MIN,'mask_escape_max':MASK_ESCAPE_MAX,
            'source_foreground_precision_min':SOURCE_FOREGROUND_PRECISION_MIN,'opaque_stage_leak_max':OPAQUE_STAGE_LEAK_MAX,
            'extreme_halo_risk_max':EXTREME_HALO_RISK_MAX,'translation_halo_risk_max':TRANSLATION_HALO_RISK_MAX,
            'translation_contact_max':TRANSLATION_CONTACT_MAX,'translation_foreign_overlap_max':TRANSLATION_FOREIGN_OVERLAP_MAX,
        },
    }
