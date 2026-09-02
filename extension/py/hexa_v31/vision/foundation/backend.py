from __future__ import annotations
import json,os,pathlib,queue,subprocess,sys,threading
from .contracts import FoundationResult

class FoundationVisionClient:
    """Persistent JSON-lines client for the isolated Foundation Vision environment."""
    def __init__(self,runtime_config,extension_root):
        self.cfg=dict(runtime_config or {});self.extension_root=pathlib.Path(extension_root);self.process=None;self._lock=threading.Lock();self.failure=None

    @property
    def enabled(self):return bool(self.cfg.get('foundation_vision_enabled'))

    def start(self):
        if not self.enabled:return False
        exe=self.cfg.get('foundation_python_exe');registry=self.cfg.get('foundation_model_registry');models=self.cfg.get('foundation_models_root')
        if not exe or not pathlib.Path(exe).is_file():self.failure='FOUNDATION_PYTHON_MISSING';return False
        cmd=[str(exe),'-m','hexa_v31.vision.foundation.worker','--registry',str(registry),'--models-root',str(models)]
        env=os.environ.copy();env['PYTHONPATH']=str(self.extension_root/'py');env['HF_HUB_OFFLINE']='1';env['TRANSFORMERS_OFFLINE']='1'
        env['HF_MODULES_CACHE']=str(pathlib.Path(models).resolve().parent/'module-cache')
        if self.cfg.get('foundation_profile'):env['HEXA_FOUNDATION_PROFILE']=str(self.cfg['foundation_profile'])
        if self.cfg.get('foundation_device')=='cpu':env['HEXA_FOUNDATION_DEVICE']='cpu'
        try:
            self.process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,env=env)
            reply=self._request({'command':'initialize'},timeout=900)
            if reply.get('status')!='READY':raise RuntimeError(reply.get('error') or 'worker not ready')
            return True
        except Exception as exc:self.failure='FOUNDATION_INITIALIZATION_FAILED: '+str(exc);self.close();return False

    def _request(self,payload,timeout=600):
        if not self.process or not self.process.stdin or not self.process.stdout:raise RuntimeError('Foundation worker is not running')
        with self._lock:
            self.process.stdin.write(json.dumps(payload,separators=(',',':'))+'\n');self.process.stdin.flush();responses=queue.Queue(maxsize=1)
            threading.Thread(target=lambda:responses.put(self.process.stdout.readline()),daemon=True).start()
            try:line=responses.get(timeout=timeout)
            except queue.Empty:raise TimeoutError(f'Foundation worker response timeout after {timeout}s')
        if not line:raise RuntimeError('Foundation worker exited: '+((self.process.stderr.read() if self.process.stderr else '')[-2000:]))
        return json.loads(line)

    def analyze(self,scene,image_path,cache_root,source_identity):
        if not self.process:return FoundationResult('FALLBACK','LEGACY_CV',error=self.failure or 'FOUNDATION_DISABLED')
        try:
            row=self._request({'command':'analyze','scene':scene,'image_path':str(image_path),'cache_root':str(cache_root),'source_identity':source_identity})
            return FoundationResult(**row)
        except Exception as exc:
            self.failure='FOUNDATION_ANALYZE_FAILED: '+str(exc)
            return FoundationResult('FALLBACK','LEGACY_CV',error=self.failure)

    def close(self):
        p=self.process;self.process=None
        if not p:return
        try:
            if p.poll() is None and p.stdin:p.stdin.write('{"command":"shutdown"}\n');p.stdin.flush();p.wait(timeout=10)
        except Exception:
            try:p.terminate()
            except Exception:pass

    def __enter__(self):self.start();return self
    def __exit__(self,*_):self.close()
