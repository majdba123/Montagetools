from __future__ import annotations
import time
from PIL import Image

FLORENCE_TASKS=('<OD>','<DENSE_REGION_CAPTION>','<REGION_PROPOSAL>')

class Florence2Backend:
    def __init__(self,model_path,device='cpu',revision=None):
        import torch
        from transformers import AutoModelForCausalLM,AutoProcessor
        self.torch=torch;self.device=device;self.model_path=str(model_path);self.revision=revision
        dtype=torch.float16 if device=='cuda' else torch.float32
        kwargs={'local_files_only':True,'trust_remote_code':True,'torch_dtype':dtype}
        self.processor=AutoProcessor.from_pretrained(self.model_path,local_files_only=True,trust_remote_code=True)
        self.model=AutoModelForCausalLM.from_pretrained(self.model_path,**kwargs).to(device).eval()

    def _run(self,image,prompt,task=None):
        task=task or prompt
        inputs=self.processor(text=prompt,images=image,return_tensors='pt')
        inputs={k:v.to(self.device) for k,v in inputs.items()}
        with self.torch.inference_mode():
            generated=self.model.generate(**inputs,max_new_tokens=1024,num_beams=3,do_sample=False)
        text=self.processor.batch_decode(generated,skip_special_tokens=False)[0]
        parsed=self.processor.post_process_generation(text,task=task,image_size=image.size)
        row=parsed.get(task,{}) if isinstance(parsed,dict) else {}
        return row if isinstance(row,dict) else {}

    def discover(self,image_path,scene_semantics=None):
        image=Image.open(image_path).convert('RGB');rows=[];started=time.perf_counter()
        for task in FLORENCE_TASKS:
            parsed=self._run(image,task);boxes=parsed.get('bboxes') or parsed.get('quad_boxes') or [];labels=parsed.get('labels') or []
            for i,box in enumerate(boxes):
                x0,y0,x1,y1=map(float,box[:4]);label=str(labels[i] if i<len(labels) else 'object')
                rows.append({'semantic_label':label,'description':label,'confidence':.72 if task=='<OD>' else .58,'bbox':[x0,y0,max(1,x1-x0),max(1,y1-y0)],'source':'FLORENCE_2','signals':[task]})
        if scene_semantics:
            caption=' '.join(str(x.get('text') or x.get('label') or '') for x in scene_semantics if isinstance(x,dict)).strip()
            if caption:
                task='<CAPTION_TO_PHRASE_GROUNDING>';parsed=self._run(image,task+caption,task);boxes=parsed.get('bboxes') or [];labels=parsed.get('labels') or []
                for i,box in enumerate(boxes):
                    x0,y0,x1,y1=map(float,box[:4]);label=str(labels[i] if i<len(labels) else caption)
                    rows.append({'semantic_label':label,'description':label,'confidence':.68,'bbox':[x0,y0,max(1,x1-x0),max(1,y1-y0)],'source':'FLORENCE_GROUNDING','signals':['<CAPTION_TO_PHRASE_GROUNDING>']})
        return rows,{'florence_seconds':round(time.perf_counter()-started,4),'florence_signal_count':len(FLORENCE_TASKS)}
