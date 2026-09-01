from __future__ import annotations
import time
import numpy as np
from PIL import Image

class SAM2Backend:
    def __init__(self,model_path,device='cpu',revision=None):
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        self.torch=torch;self.device=device;self.model_path=str(model_path);self.revision=revision
        cfg='configs/sam2.1/sam2.1_hiera_l.yaml' if 'large' in self.model_path.lower() else 'configs/sam2.1/sam2.1_hiera_b+.yaml'
        self.predictor=SAM2ImagePredictor(build_sam2(cfg,self.model_path,device=device,apply_postprocessing=False))

    def segment(self,image_path,candidates):
        image=np.array(Image.open(image_path).convert('RGB'));self.predictor.set_image(image);rows=[];started=time.perf_counter()
        for cand in candidates:
            x,y,w,h=cand.bbox;box=np.asarray([x,y,x+w,y+h],dtype=np.float32)
            with self.torch.inference_mode():
                masks,scores,_=self.predictor.predict(box=box,multimask_output=True)
            # Physical validation downstream decides among masks; preserve every option.
            rows.append({'candidate_id':cand.candidate_id,'masks':[m.astype(bool) for m in masks],'scores':[float(s) for s in scores]})
        return rows,{'sam2_seconds':round(time.perf_counter()-started,4),'sam2_mask_count':sum(len(x['masks']) for x in rows)}
