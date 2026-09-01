from __future__ import annotations
import json,pathlib,tempfile
from hexa_v31.vision.foundation.backend import FoundationVisionClient
from hexa_v31.vision.foundation.model_registry import fingerprint
from hexa_v31.app.pipeline import _foundation_materially_useful
from hexa_v31.vision.foundation.worker import Worker
import numpy as np
from PIL import Image

root=pathlib.Path(__file__).resolve().parents[1]
disabled=FoundationVisionClient({},root/'extension');assert not disabled.start();r=disabled.analyze({},'missing',root,'x');assert r.status=='FALLBACK' and r.backend_used=='LEGACY_CV'
missing=FoundationVisionClient({'foundation_vision_enabled':True,'foundation_python_exe':str(root/'missing-python.exe')},root/'extension');assert not missing.start() and missing.failure=='FOUNDATION_PYTHON_MISSING'
assert _foundation_materially_useful({'units':[{'animation_safe':False}],'expected_semantic_units':3,'grouped_detail_count':3})
assert not _foundation_materially_useful({'units':[{'animation_safe':True},{'animation_safe':True}],'expected_semantic_units':2,'grouped_detail_count':0})

registry=root/'extension/resources/HEXA_FOUNDATION_VISION_MODELS_V31.json';a=fingerprint(registry)
with tempfile.TemporaryDirectory() as td:
 data=json.loads(registry.read_text(encoding='utf-8'));data['models'][0]['revision']='changed-revision';p=pathlib.Path(td)/'registry.json';p.write_text(json.dumps(data),encoding='utf-8');b=fingerprint(p)
 assert a!=b
with tempfile.TemporaryDirectory() as td:
 t=pathlib.Path(td);source=t/'source.png';Image.new('RGB',(100,80),'white').save(source)
 reg=t/'registry.json';reg.write_text(json.dumps({'schema':'HEXA_FOUNDATION_VISION_MODEL_REGISTRY_1.0','models':[{'backend':'florence2','profile':'quality','model_id':'f','revision':'r1','checkpoint_sha256':None},{'backend':'sam2','profile':'quality','model_id':'s','revision':'r1','checkpoint_sha256':None}]}),encoding='utf-8')
 class Florence:
  def discover(self,*_):return ([{'label':'object one','confidence':.9,'bbox':[10,10,30,30],'source':'OD'}],{'florence_seconds':.1})
 class Sam:
  def segment(self,_image,candidates):
   mask=np.zeros((80,100),bool);mask[10:40,10:40]=True
   return ([{'candidate_id':candidates[0].candidate_id,'masks':[mask],'scores':[.9]}],{'sam2_seconds':.1,'sam2_mask_count':1})
 w=Worker(reg,t);w.florence=Florence();w.sam=Sam();w.models={'florence2':{'model_id':'f'},'sam2':{'model_id':'s'}}
 payload={'scene':{'scene_id':'S','units':[]},'image_path':str(source),'cache_root':str(t/'cache'),'source_identity':{'package_sha256':'abc','package_version':'1.0'}}
 first=w.analyze(payload);assert first['cache_state']['status']=='CACHE_MISS'
 second=w.analyze(payload);assert second['cache_state']['status']=='CACHE_HIT'
 changed=json.loads(reg.read_text());changed['models'][0]['revision']='r2';reg.write_text(json.dumps(changed),encoding='utf-8')
 third=w.analyze(payload);assert third['cache_state']==dict(third['cache_state'],status='CACHE_INVALIDATED',reason='MODEL_OR_IMPLEMENTATION_CHANGED')
pipeline=(root/'extension/py/hexa_v31/app/pipeline.py').read_text(encoding='utf-8')
worker=(root/'extension/py/hexa_v31/vision/foundation/worker.py').read_text(encoding='utf-8')
assert 'CACHE_HIT' in worker and 'CACHE_INVALIDATED' in worker and 'cache_invalidation_reason' in pipeline
assert 'package_sha256' in pipeline and 'downloads_during_build' in pipeline
for forbidden in ('SCENE_040','credit card','6abda3a85214'):
 assert forbidden not in '\n'.join((root/'extension/py/hexa_v31/vision/foundation'/p).read_text(encoding='utf-8') for p in ['candidate_fusion.py','worker.py'])
print('V31_FOUNDATION_WORKER_FALLBACK_CACHE_PASS')
