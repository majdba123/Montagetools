from __future__ import annotations
import pathlib,time
import numpy as np
from PIL import Image
from .matting import refine_alpha

FOUNDATION_RECONSTRUCTION_VERSION='FOUNDATION_LOSSLESS_RECONSTRUCTION_2.0'

def validate_partition_masks(source_foreground,actor_masks,residual_mask=None):
    source=np.asarray(source_foreground)>0;h,w=source.shape;stack=np.stack([np.asarray(x)>0 for x in actor_masks],axis=0) if actor_masks else np.zeros((0,h,w),bool)
    union=np.any(stack,axis=0) if len(stack) else np.zeros_like(source);multiplicity=np.sum(stack,axis=0) if len(stack) else np.zeros_like(source,dtype=np.uint8);residual=np.asarray(residual_mask)>0 if residual_mask is not None else np.zeros_like(source)
    reconstructed=union|residual;source_count=max(1,int(np.count_nonzero(source)));duplicate=int(np.count_nonzero((multiplicity>1)&source));outside=int(np.count_nonzero(union&(~source)));unexplained=int(np.count_nonzero(source&(~reconstructed)))
    metrics={'source_foreground_pixels':int(np.count_nonzero(source)),'actor_union_pixels':int(np.count_nonzero(union&source)),'residual_support_pixels':int(np.count_nonzero(residual&source)),'unexplained_foreground_pixels':unexplained,'duplicate_overlap_pixels':duplicate,'actor_coverage_fraction':round(int(np.count_nonzero(union&source))/source_count,6),'residual_fraction':round(int(np.count_nonzero(residual&source))/source_count,6),'unexplained_loss_fraction':round(unexplained/source_count,6),'overlap_fraction':round(duplicate/source_count,6),'outside_foreground_fraction':round(outside/source_count,6)}
    metrics['partition_complete']=bool(actor_masks and metrics['unexplained_loss_fraction']<=.001 and metrics['overlap_fraction']<=.05 and metrics['outside_foreground_fraction']<=.004)
    return metrics

def build_lossless_foundation_partition(rgb,bg,source_foreground,actors,alpha_by_id,out_dir,final_out):
    """Preserve every validated source pixel as an actor or residual support layer."""
    started=time.perf_counter();source=np.asarray(source_foreground)>0;h,w=source.shape
    actor_masks=[np.asarray(alpha_by_id[a['physical_id']])>4 for a in actors if a.get('physical_id') in alpha_by_id]
    stack=np.stack(actor_masks,axis=0) if actor_masks else np.zeros((0,h,w),bool)
    union=np.any(stack,axis=0) if len(stack) else np.zeros_like(source)
    multiplicity=np.sum(stack,axis=0) if len(stack) else np.zeros_like(source,dtype=np.uint8)
    duplicate=(multiplicity>1)&source;outside=union&(~source);residual=source&(~union)
    reconstructed=union|residual;unexplained=source&(~reconstructed)
    source_count=max(1,int(np.count_nonzero(source)));actor_union=int(np.count_nonzero(union&source));residual_count=int(np.count_nonzero(residual));unexplained_count=int(np.count_nonzero(unexplained));duplicate_count=int(np.count_nonzero(duplicate));outside_count=int(np.count_nonzero(outside))
    overlap_fraction=duplicate_count/source_count;loss_fraction=unexplained_count/source_count;outside_fraction=outside_count/source_count
    residual_row=None;residual_layer=None
    if residual_count:
        hard=residual.astype(np.uint8)*255;alpha,clean,matte=refine_alpha(rgb,hard,bg,group_mask=hard)
        path=pathlib.Path(out_dir)/'RESIDUAL_SUPPORT.png';final_path=pathlib.Path(final_out)/path.name;Image.fromarray(np.dstack([clean,alpha]),'RGBA').save(path)
        yy,xx=np.where(alpha>4);x0=int(xx.min());y0=int(yy.min());x1=int(xx.max()+1);y1=int(yy.max()+1)
        residual_row={'physical_id':'RESIDUAL_SUPPORT','bbox':[x0,y0,x1-x0,y1-y0],'area_px':int(np.count_nonzero(alpha>4)),'center_norm':[round((x0+x1)/(2*w),6),round((y0+y1)/(2*h),6)],'bbox_norm':[round(x0/w,6),round(y0/h,6),round((x1-x0)/w,6),round((y1-y0)/h,6)],'mask_confidence':1.0,'edge_touch':bool(np.any(residual[0]) or np.any(residual[-1]) or np.any(residual[:,0]) or np.any(residual[:,-1])),'semantic_unit_id':None,'semantic_type':'RESIDUAL_SUPPORT','semantic_role':'SUPPORTING','hierarchy_level':1,'composition_slot_id':'ROOT_COMPOSITE','subobject_role':'RECONSTRUCTION_SUPPORT','animation_safe':False,'translation_safe':False,'translation_safe_after_occlusion':False,'reveal_safe':True,'scale_safe':False,'rotation_safe':False,'animation_mode':'STATIC_SUPPORT','occlusion_class':'RESIDUAL_SUPPORT','matting':matte,'semantic_mapping_confidence':1.0,'layer_path':str(final_path),'mask_path':str(final_path),'layer_canvas_mode':'FULL_SCENE_ALPHA_CANVAS','layer_source_size_px':[w,h],'crop_origin_px':[x0,y0],'crop_size_px':[x1-x0,y1-y0],'root_id':'ROOT_COMPOSITE','parent_id':'ROOT_COMPOSITE','child_id':'ROOT_COMPOSITE::RESIDUAL_SUPPORT','visible_area':round(float(np.count_nonzero(alpha>4))/(h*w),6),'optical_center':[round((x0+x1)/(2*w),6),round((y0+y1)/(2*h),6)],'independence_confidence':1.0,'reconstruction_error':0.0,'render_mode':'RESIDUAL_SUPPORT','partition_root_id':'ROOT_COMPOSITE','partition_complete':False,'independent_motion_allowed':False,'foundation_residual_support':True}
        residual_layer={'path':str(final_path),'origin_px':[0,0],'size_px':[w,h],'content_origin_px':[x0,y0],'content_size_px':[x1-x0,y1-y0],'canvas_mode':'FULL_SCENE_ALPHA_CANVAS'};alpha_by_id['RESIDUAL_SUPPORT']=alpha
    alpha_reconstruction=(np.maximum.reduce([np.asarray(alpha_by_id[a['physical_id']]) for a in actors]+([np.asarray(alpha_by_id['RESIDUAL_SUPPORT'])] if residual_row else [np.zeros((h,w),np.uint8)]))>4)
    alpha_loss=int(np.count_nonzero(source&(~alpha_reconstruction)))/source_count
    mask_validation=validate_partition_masks(source,actor_masks,residual)
    partition_complete=bool(mask_validation['partition_complete'] and alpha_loss<=.003)
    diagnostics={'schema':'HEXA_FOUNDATION_RECONSTRUCTION_QA','version':FOUNDATION_RECONSTRUCTION_VERSION,'source_foreground_pixels':int(np.count_nonzero(source)),'actor_union_pixels':actor_union,'residual_support_pixels':residual_count,'unexplained_foreground_pixels':unexplained_count,'duplicate_overlap_pixels':duplicate_count,'actor_coverage_fraction':round(actor_union/source_count,6),'residual_fraction':round(residual_count/source_count,6),'unexplained_loss_fraction':round(loss_fraction,6),'overlap_fraction':round(overlap_fraction,6),'outside_foreground_fraction':round(outside_fraction,6),'alpha_reconstruction_loss_fraction':round(alpha_loss,6),'reconstruction_error':round(alpha_loss+outside_fraction+overlap_fraction,6),'partition_complete':partition_complete,'residual_support_present':bool(residual_row),'root_fallback_available':True,'validation_seconds':round(time.perf_counter()-started,4)}
    return residual_row,residual_layer,diagnostics
