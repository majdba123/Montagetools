from __future__ import annotations
import json,pathlib,tempfile
import numpy as np
from PIL import Image,ImageDraw
from hexa_v31.vision import analyze_scene
from hexa_v31.preset_story_planner import _select_render_units

with tempfile.TemporaryDirectory() as td:
 root=pathlib.Path(td);source=root/'source.png';im=Image.new('RGB',(320,180),'white');d=ImageDraw.Draw(im)
 d.rectangle((20,35,100,145),fill=(30,110,210));d.rectangle((205,45,290,135),fill=(230,80,55));d.rectangle((48,68,72,94),fill='white')
 im.save(source);mask_dir=root/'foundation';mask_dir.mkdir();candidates=[];masks=[]
 for i,(label,box) in enumerate((('bank building',(20,35,81,111)),('payment terminal',(205,45,86,91))),1):
  cid=f'FV_{i:03d}';arr=np.zeros((180,320),np.uint8);x,y,w,h=box;arr[y:y+h,x:x+w]=255;mp=mask_dir/(cid+'.png');Image.fromarray(arr).save(mp)
  candidates.append({'candidate_id':cid,'semantic_label':label,'description':label,'confidence':.94,'bbox':list(box),'source':'FLORENCE_2','semantic_role':'PRIMARY'})
  masks.append({'candidate_id':cid,'mask_path':str(mp),'sam_score':.95,'bbox_agreement':1.0})
 foundation={'status':'PASS','backend_used':'FLORENCE2_SAM2','candidates':candidates,'masks':masks,'diagnostics':{'sam2_mask_count':2},'cache_state':{'status':'CACHE_MISS','reason':'CACHE_MISS','signature':'mock-foundation-v1'},'error':None}
 scene={'scene_id':'GENERIC_COMPLEX','units':[{'unit_id':'ROOT','type':'CONCEPT','role':'PRIMARY'}]}
 result=analyze_scene(scene,source,root/'out',foundation_result=foundation)
 actors=[u for u in result.units if u.get('candidate_source')]
 assert len(actors)==2 and all(pathlib.Path(u['layer_path']).is_file() for u in actors)
 assert len({u['physical_id'] for u in actors})==2
 assert all(u['parent_id']=='ROOT_COMPOSITE' for u in actors)
 assert any(u.get('translation_safe_after_occlusion') for u in actors),actors
 assert len(result.units)>len(actors) # legacy/root safety representation remains
 # Internal white content in the blue object remains opaque after HEXA matting.
 blue=next(u for u in actors if u['semantic_label']=='bank building');alpha=np.array(Image.open(blue['layer_path']).convert('RGBA'))[:,:,3]
 assert alpha[80,60]>=245
 assert result.artifacts['foundation_vision']['accepted_actor_count']==2
 assert result.artifacts['foundation_vision']['actor_qa']['pass']
 assert result.artifacts['foundation_vision']['actor_qa']['motion_addressable_actor_count']>=2
 assert result.artifacts['matting_summary']['max_opaque_stage_leak_fraction']<=.004
 selected,selection=_select_render_units({'units':result.units,'artifacts':result.artifacts})
 assert selection['foundation_actor_partition'] and len(selected)==2
 assert all(u['render_mode']=='CHILD_PARTITION' and u['source_layer_path'] if 'source_layer_path' in u else u['layer_path'] for u in selected)
print('V31_FOUNDATION_ACTOR_INTEGRATION_PASS')
