"""Offline real-model Florence2 -> SAM2 -> HEXA PhysicalUnit certification."""
from __future__ import annotations
import argparse, json, os, pathlib, sys, tempfile, time
from PIL import Image, ImageDraw

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--registry',required=True);p.add_argument('--models-root',required=True);p.add_argument('--profile',required=True,choices=('QUALITY','LOW_MEMORY'));p.add_argument('--device',required=True,choices=('cpu','cuda'));a=p.parse_args(argv)
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HEXA_FOUNDATION_PROFILE']=a.profile
    if a.device=='cpu':os.environ['HEXA_FOUNDATION_DEVICE']='cpu'
    from hexa_v31.vision.foundation.worker import Worker
    from hexa_v31.vision.vision import analyze_scene
    from hexa_v31.planning.preset_story_planner import _select_render_units
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='hexa-foundation-real-smoke-') as tmp:
        root=pathlib.Path(tmp);os.environ['HF_MODULES_CACHE']=str(root/'hf-modules');image=root/'scene.png'
        canvas=Image.new('RGB',(768,512),'white');d=ImageDraw.Draw(canvas)
        d.ellipse((90,115,300,330),fill='#e53935',outline='#8b0000',width=9);d.ellipse((235,70,300,140),fill='#43a047');d.text((150,350),'RED APPLE',fill='black')
        d.rounded_rectangle((420,180,700,330),radius=28,fill='#1976d2',outline='#0d47a1',width=9);d.ellipse((455,300,525,370),fill='#202020');d.ellipse((600,300,670,370),fill='#202020');d.text((505,390),'BLUE CAR',fill='black');canvas.save(image)
        scene={'scene_id':'REAL_FOUNDATION_SMOKE','units':[{'unit_id':'APPLE','type':'OBJECT','role':'PRIMARY','text':'red apple'},{'unit_id':'CAR','type':'OBJECT','role':'SUPPORTING','text':'blue car'}]}
        worker=Worker(a.registry,a.models_root);init=worker.initialize();foundation=worker.analyze({'image_path':str(image),'scene':scene,'cache_root':str(root/'foundation-cache'),'source_identity':'REAL_SMOKE_SYNTHETIC_V1'})
        if foundation.get('status')!='PASS' or not foundation.get('masks'):raise RuntimeError('Real Florence/SAM2 produced no accepted masks: '+json.dumps(foundation.get('diagnostics') or {}))
        vision=analyze_scene(scene,image,root/'vision-cache',foundation_result=foundation);row={'units':vision.units,'artifacts':vision.artifacts};selected,selection=_select_render_units(row)
        actors=[u for u in vision.units if u.get('candidate_source')]
        if not actors:raise RuntimeError('HEXA accepted no real-model PhysicalUnit actors')
        if not selected:raise RuntimeError('Planner selected no render units')
        report={'status':'PASS','offline':True,'backend':foundation.get('backend_used'),'device':init.get('device'),'profile':a.profile,'candidate_count':len(foundation.get('candidates') or []),'sam_mask_count':len(foundation.get('masks') or []),'physical_actor_count':len(actors),'partition_complete':bool((vision.artifacts.get('foundation_vision') or {}).get('reconstruction_qa',{}).get('partition_complete')),'selected_render_unit_count':len(selected),'selection':selection,'elapsed_seconds':round(time.perf_counter()-started,3)}
        print(json.dumps(report,separators=(',',':')));return 0

if __name__=='__main__':raise SystemExit(main())
