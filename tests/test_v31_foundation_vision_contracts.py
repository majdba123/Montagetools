from __future__ import annotations
import json,pathlib,tempfile
import numpy as np
from PIL import Image,ImageDraw
from hexa_v31.vision.foundation.candidate_fusion import fuse_candidates
from hexa_v31.extraction.mask_validation import validate_mask
from hexa_v31.vision.foundation.device_policy import select_device
from hexa_v31.vision.foundation.model_registry import resolve_models,ModelIntegrityError
from hexa_v31.extraction.actor_validation import classify_actor

rows=[
 {'label':'bank building','confidence':.9,'bbox':[10,15,70,70],'source':'OD'},
 {'label':'bank building','confidence':.8,'bbox':[11,16,69,69],'source':'DENSE'},
 {'label':'payment terminal','confidence':.91,'bbox':[105,25,60,65],'source':'OD'},
 {'label':'decoration','confidence':.99,'bbox':[2,2,3,3],'source':'REGION'},
 {'label':'coin','confidence':.9,'bbox':[190,100,2,2],'source':'REGION'},
]
accepted,rejected=fuse_candidates(rows,(200,120))
assert [x.semantic_label for x in accepted]==['payment terminal','bank building']
assert {'DUPLICATE','LOW_SEMANTIC_VALUE','TOO_SMALL'}<=set(x['rejection_reason'] for x in rejected)

fg=np.zeros((120,200),np.uint8);fg[15:85,10:80]=255;fg[25:90,105:165]=255
ok,reason,evidence=validate_mask(fg==255,(10,15,155,75),fg);assert ok and reason is None
tiny=np.zeros_like(fg);tiny[2:4,2:4]=1;assert validate_mask(tiny,(2,2,2,2),fg)[1]=='TOO_SMALL'
fragment=np.zeros_like(fg)
for x in range(10,110,18):fragment[20:28,x:x+8]=1
assert validate_mask(fragment,(10,20,100,8),np.ones_like(fg)*255)[1]=='MASK_FRAGMENTED'
edge=np.zeros_like(fg);edge[0:40,20:70]=1;assert validate_mask(edge,(20,0,50,40),edge*255)[2]['edge_touch']
edge_policy=classify_actor(edge,edge*255,{'bbox':(20,0,50,40),'edge_touch':True,'mask_outside_candidate_fraction':0.0});assert not edge_policy['translation_safe'] and 'SOURCE_CANVAS_EDGE_CLIPPED' in edge_policy['independence_block_reasons']
# Detached objects remain independently addressable; touching/held/occluded objects are conservative.
detached=np.zeros_like(fg,dtype=bool);detached[20:60,20:60]=True;detached_fg=detached.copy();detached_fg[80:110,130:170]=True
assert classify_actor(detached,detached_fg,{'bbox':(20,20,40,40),'edge_touch':False})['translation_safe']
held=np.zeros_like(fg,dtype=bool);held[35:65,70:105]=True;character=np.zeros_like(fg,dtype=bool);character[20:100,100:145]=True;held_fg=held|character
held_policy=classify_actor(held,held_fg,{'bbox':(70,35,35,30),'edge_touch':False});assert held_policy['safety_class']=='ATOMIC_PARENT_DEPENDENT' and held_policy['reveal_safe'] and not held_policy['translation_safe']
assert held_policy['boundary_contact_ratio']>0 and held_policy['physical_independence_confidence']<1.0

class CPUCuda:
 def is_available(self):return False
class CPUTorch:cuda=CPUCuda()
assert select_device(CPUTorch())['device']=='cpu'
class Props:name='GPU';total_memory=16*1024**3
class GPUCuda:
 def is_available(self):return True
 def get_device_properties(self,_):return Props()
class GPUTorch:cuda=GPUCuda()
assert select_device(GPUTorch())['device']=='cuda' and select_device(GPUTorch())['profile']=='QUALITY'

with tempfile.TemporaryDirectory() as td:
 root=pathlib.Path(td);model=root/'model';model.mkdir();checkpoint=model/'weights.bin';checkpoint.write_bytes(b'corrupt')
 registry=root/'registry.json';registry.write_text(json.dumps({'schema':'HEXA_FOUNDATION_VISION_MODEL_REGISTRY_1.0','models':[{'backend':'sam2','profile':'quality','model_id':'x','revision':'abc','checkpoint_sha256':'0'*64,'checkpoint_file':'weights.bin','local_path':'model','license':'Apache-2.0'}]}),encoding='utf-8')
 try:resolve_models(registry,root)
 except ModelIntegrityError:pass
 else:raise AssertionError('corrupt checkpoint accepted')
print('V31_FOUNDATION_VISION_CONTRACTS_PASS')
