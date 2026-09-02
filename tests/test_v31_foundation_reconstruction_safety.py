from __future__ import annotations
import pathlib,tempfile
import numpy as np
from PIL import Image
from hexa_v31.extraction.reconstruction import validate_partition_masks,build_lossless_foundation_partition,FOUNDATION_RECONSTRUCTION_VERSION
from hexa_v31.preset_story_planner import _select_render_units

source=np.zeros((100,160),np.uint8);source[10:90,5:155]=255
a=np.zeros_like(source);a[15:55,10:60]=255
b=np.zeros_like(source);b[35:85,95:145]=255
# Actor count alone is never completeness evidence.
missing=validate_partition_masks(source,[a,b]);assert not missing['partition_complete'] and missing['unexplained_loss_fraction']>.5
residual=(source>0)&~((a>0)|(b>0));complete=validate_partition_masks(source,[a,b],residual);assert complete['partition_complete'] and complete['unexplained_foreground_pixels']==0
overlap=np.zeros_like(source);overlap[15:75,40:120]=255
bad=validate_partition_masks(source,[a,overlap,overlap],residual);assert not bad['partition_complete'] and bad['overlap_fraction']>.05

with tempfile.TemporaryDirectory() as td:
 root=pathlib.Path(td);out=root/'stage';final=root/'final';out.mkdir();rgb=np.full((100,160,3),255,np.uint8);rgb[source>0]=(40,100,210);rgb[30:48,20:40]=(255,255,255)
 actors=[{'physical_id':'A','candidate_source':'FLORENCE_2','partition_complete':False,'mask_path':'a'},{'physical_id':'B','candidate_source':'FLORENCE_2','partition_complete':False,'mask_path':'b'}];alphas={'A':a,'B':b}
 residual_row,layer,qa=build_lossless_foundation_partition(rgb,(255,255,255),source,actors,alphas,out,final)
 assert qa['partition_complete'] and qa['residual_support_present'] and qa['unexplained_loss_fraction']==0
 assert residual_row and residual_row['render_mode']=='RESIDUAL_SUPPORT' and not residual_row['translation_safe_after_occlusion']
 # Internal white source content remains assigned to an actor, not mistaken for stage loss.
 assert a[35,30]==255 and qa['source_foreground_pixels']==12000
 units=[]
 for actor in actors:
  units.append(dict(actor,physical_id=actor['physical_id'],partition_complete=True,layer_path='x',mask_path='x',translation_safe_after_occlusion=True,animation_safe=True,semantic_role='PRIMARY',bbox_norm=[.1,.1,.2,.2],hierarchy_level=1))
 residual_row['partition_complete']=True;units.append(residual_row);artifacts={'foundation_vision':{'reconstruction_qa':qa}}
 selected,diag=_select_render_units({'units':units,'artifacts':artifacts});assert diag['foundation_actor_partition'] and len(selected)==3 and any(x['render_mode']=='RESIDUAL_SUPPORT' for x in selected)
 unsafe_units=[dict(x,partition_complete=False) for x in units];selected2,diag2=_select_render_units({'units':unsafe_units,'artifacts':{'foundation_vision':{'reconstruction_qa':dict(qa,partition_complete=False)}}});assert not diag2.get('foundation_actor_partition') and not any(x.get('candidate_source') for x in selected2)
print('V31_FOUNDATION_RECONSTRUCTION_SAFETY_PASS',FOUNDATION_RECONSTRUCTION_VERSION)
