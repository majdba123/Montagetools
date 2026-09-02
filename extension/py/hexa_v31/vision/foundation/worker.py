from __future__ import annotations
import argparse,hashlib,json,pathlib,sys,time,traceback
import numpy as np
from PIL import Image
from .candidate_fusion import FUSION_VERSION,fuse_candidates
from .contracts import FoundationResult
from .device_policy import select_device
from .diagnostics import summarize
from .florence2_backend import Florence2Backend
from .model_registry import fingerprint,resolve_models
from .sam2_backend import SAM2Backend
from hexa_v31.util import sha256_file,write_json,read_json,ensure_dir
from hexa_v31.extraction.mask_validation import MASK_VALIDATION_VERSION,bbox_from_mask
from hexa_v31.extraction.actor_validation import ACTOR_VALIDATION_VERSION
from hexa_v31.extraction.actor_extraction import ACTOR_EXTRACTION_VERSION
from hexa_v31.extraction.reconstruction import FOUNDATION_RECONSTRUCTION_VERSION
from hexa_v31.extraction.matting import __file__ as matting_source

WORKER_VERSION='HEXA_FOUNDATION_VISION_WORKER_1.0'

def _box_iou(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b;ix=max(0,min(ax+aw,bx+bw)-max(ax,bx));iy=max(0,min(ay+ah,by+bh)-max(ay,by));inter=ix*iy
    return inter/max(1,aw*ah+bw*bh-inter)

class Worker:
    def __init__(self,registry,models_root):self.registry=pathlib.Path(registry);self.models_root=pathlib.Path(models_root);self.device=select_device();self.models={};self.florence=None;self.sam=None
    def initialize(self):
        self.models=resolve_models(self.registry,self.models_root,self.device['profile'])
        missing=[k for k,v in self.models.items() if v['installation_status']!='INSTALLED']
        if missing:raise RuntimeError('MODEL_NOT_INSTALLED: '+','.join(missing))
        self.florence=Florence2Backend(self.models['florence2']['absolute_path'],self.device['device'],self.models['florence2']['revision'])
        self.sam=SAM2Backend(self.models['sam2']['checkpoint_path'],self.device['device'],self.models['sam2']['revision'])
        return {'status':'READY','backend_used':'FLORENCE2_SAM2','device':self.device,'models':{k:v['model_id'] for k,v in self.models.items()}}
    def analyze(self,payload):
        image=pathlib.Path(payload['image_path']);scene=payload.get('scene') or {};cache_root=ensure_dir(pathlib.Path(payload['cache_root'])/'foundation');sid=str(scene.get('scene_id') or image.stem);out=ensure_dir(cache_root/sid)
        deps={'worker':WORKER_VERSION,'model_registry':fingerprint(self.registry,self.device['profile']),'fusion':FUSION_VERSION,'mask_validation':MASK_VALIDATION_VERSION,'actor_validation':ACTOR_VALIDATION_VERSION,'actor_extraction':ACTOR_EXTRACTION_VERSION,'reconstruction':FOUNDATION_RECONSTRUCTION_VERSION,'matting_source_sha256':sha256_file(matting_source),'occlusion':'OCCLUSION_1.0_CONSERVATIVE_GRAPH'}
        identity={'image_sha256':sha256_file(image),'source_identity':payload.get('source_identity'),'scene_units':scene.get('units') or []}
        signature=hashlib.sha256(json.dumps({'input':identity,'dependencies':deps},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest();meta=out/'cache_meta.json';result_path=out/'foundation_result.json'
        if meta.is_file() and result_path.is_file():
            old=read_json(meta)
            if old.get('signature')==signature:
                result=read_json(result_path)
                if all(pathlib.Path(x['mask_path']).is_file() for x in result.get('masks') or []):result['cache_state']={'status':'CACHE_HIT','reason':None,'signature':signature};return result
            reason='MODEL_OR_IMPLEMENTATION_CHANGED' if old.get('input')==identity else 'SOURCE_IDENTITY_CHANGED'
        else:reason='CACHE_MISS'
        raw,fd=self.florence.discover(image,scene.get('units') or []);size=Image.open(image).size;candidates,rejected=fuse_candidates(raw,size)
        segmented,sd=self.sam.segment(image,candidates);mask_rows=[]
        for row in segmented:
            cand=next(c for c in candidates if c.candidate_id==row['candidate_id']);ranked=[]
            for mask,score in zip(row['masks'],row['scores']):
                mb=bbox_from_mask(mask);agreement=_box_iou(mb,cand.bbox) if mb else 0;ranked.append((float(score)*.55+agreement*.45,mask,float(score),agreement))
            if not ranked:continue
            _,mask,score,agreement=max(ranked,key=lambda x:x[0]);mp=out/(cand.candidate_id+'.png');Image.fromarray((mask.astype(np.uint8)*255),'L').save(mp);mask_rows.append({'candidate_id':cand.candidate_id,'mask_path':str(mp),'sam_score':round(score,5),'bbox_agreement':round(agreement,5),'candidate_mask_count':len(ranked)})
        cache={'status':'CACHE_MISS' if reason=='CACHE_MISS' else 'CACHE_INVALIDATED','reason':reason,'signature':signature}
        diag=summarize([c.to_dict() for c in candidates],segmented,[],rejected,'FLORENCE2_SAM2',self.device,dict(fd,**sd),cache);diag['model_ids']={k:v['model_id'] for k,v in self.models.items()}
        result=FoundationResult('PASS','FLORENCE2_SAM2',[c.to_dict() for c in candidates],mask_rows,diag,cache).to_dict();write_json(result_path,result);write_json(meta,{'schema':'HEXA_FOUNDATION_CACHE_1.0','signature':signature,'input':identity,'dependencies':deps});return result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--registry',required=True);p.add_argument('--models-root',required=True);a=p.parse_args(argv);worker=Worker(a.registry,a.models_root)
    for line in sys.stdin:
        try:
            req=json.loads(line);cmd=req.get('command')
            if cmd=='initialize':reply=worker.initialize()
            elif cmd=='analyze':reply=worker.analyze(req)
            elif cmd=='shutdown':print('{"status":"BYE"}',flush=True);return 0
            else:reply={'status':'ERROR','error':'UNKNOWN_COMMAND'}
        except Exception as exc:reply={'status':'ERROR','error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(limit=3)}
        print(json.dumps(reply,ensure_ascii=False,separators=(',',':')),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
