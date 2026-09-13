from __future__ import annotations
import os

MIN_FOUNDATION_CUDA_VRAM_BYTES=4*1024**3

def select_device(torch_module=None)->dict:
    forced=os.environ.get('HEXA_FOUNDATION_DEVICE','').strip().lower();forced_profile=os.environ.get('HEXA_FOUNDATION_PROFILE','').strip().upper();profile=forced_profile if forced_profile in ('QUALITY','LOW_MEMORY') else 'QUALITY'
    if forced=='cpu':return {'device':'cpu','profile':profile,'reason':'FORCED_CPU','gpu_name':None,'vram_bytes':None,'minimum_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES}
    try:
        torch=torch_module or __import__('torch')
        if torch.cuda.is_available():
            props=torch.cuda.get_device_properties(0);vram=int(getattr(props,'total_memory',0));gpu_name=str(getattr(props,'name','CUDA'));profile=forced_profile if forced_profile in ('QUALITY','LOW_MEMORY') else ('QUALITY' if vram>=10*1024**3 else 'LOW_MEMORY')
            # A trivial CUDA tensor probe is not enough authority to load Florence +
            # SAM2 on legacy low-VRAM GPUs. Keep the pinned CUDA wheel reusable, but
            # run Foundation inference on CPU below the production memory floor.
            if vram<MIN_FOUNDATION_CUDA_VRAM_BYTES:
                return {'device':'cpu','profile':profile,'reason':'CUDA_VRAM_BELOW_MINIMUM','gpu_name':gpu_name,'vram_bytes':vram,'minimum_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES}
            return {'device':'cuda','profile':profile,'reason':'CUDA_AVAILABLE_AND_MEMORY_CERTIFIED','gpu_name':gpu_name,'vram_bytes':vram,'minimum_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES}
    except Exception as exc:
        return {'device':'cpu','profile':profile,'reason':'CUDA_PROBE_FAILED','gpu_name':None,'vram_bytes':None,'probe_error':str(exc),'minimum_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES}
    return {'device':'cpu','profile':profile,'reason':'CUDA_UNAVAILABLE','gpu_name':None,'vram_bytes':None,'minimum_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES}
