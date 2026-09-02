from __future__ import annotations
import os

def select_device(torch_module=None)->dict:
    forced=os.environ.get('HEXA_FOUNDATION_DEVICE','').strip().lower()
    forced_profile=os.environ.get('HEXA_FOUNDATION_PROFILE','').strip().upper()
    profile=forced_profile if forced_profile in ('QUALITY','LOW_MEMORY') else 'QUALITY'
    if forced=='cpu':return {'device':'cpu','profile':profile,'reason':'FORCED_CPU','gpu_name':None,'vram_bytes':None}
    try:
        torch=torch_module or __import__('torch')
        if torch.cuda.is_available():
            props=torch.cuda.get_device_properties(0)
            vram=int(getattr(props,'total_memory',0))
            profile=forced_profile if forced_profile in ('QUALITY','LOW_MEMORY') else ('QUALITY' if vram>=10*1024**3 else 'LOW_MEMORY')
            return {'device':'cuda','profile':profile,'reason':'CUDA_AVAILABLE','gpu_name':str(getattr(props,'name','CUDA')),'vram_bytes':vram}
    except Exception as exc:
        return {'device':'cpu','profile':profile,'reason':'CUDA_PROBE_FAILED','gpu_name':None,'vram_bytes':None,'probe_error':str(exc)}
    return {'device':'cpu','profile':profile,'reason':'CUDA_UNAVAILABLE','gpu_name':None,'vram_bytes':None}
