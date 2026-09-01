REJECTION_REASONS=('LOW_CONFIDENCE','TOO_SMALL','DUPLICATE','EXCESSIVE_OVERLAP','MASK_FRAGMENTED','UNSAFE_OCCLUSION','ROOT_DUPLICATE','WHITE_STAGE_LEAK','RECONSTRUCTION_FAILURE','LOW_SEMANTIC_VALUE','EMPTY_MASK','BBOX_MISMATCH')

def summarize(candidates,masks,accepted,rejected,backend,device,durations,cache):
    reasons={}
    for row in rejected:
        reason=str(row.get('rejection_reason') or 'UNKNOWN');reasons[reason]=reasons.get(reason,0)+1
    return {'semantic_candidate_count':len(candidates),'legacy_candidate_count':0,'merged_candidate_count':len(candidates),'sam2_mask_count':sum(len(x.get('masks') or []) for x in masks),'accepted_actor_count':len(accepted),'translation_safe_actor_count':sum(bool(x.get('translation_safe')) for x in accepted),'reveal_only_actor_count':sum(bool(x.get('reveal_safe')) and not bool(x.get('translation_safe')) for x in accepted),'atomic_actor_count':sum(x.get('safety_class')=='ATOMIC_PARENT_DEPENDENT' for x in accepted),'rejected_actor_count':len(rejected),'rejection_reasons':reasons,'backend_used':backend,'device_used':device,'inference_durations':durations,'cache_status':cache.get('status'),'cache_invalidation_reason':cache.get('reason')}
