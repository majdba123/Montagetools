from __future__ import annotations

import dataclasses
import importlib
import json
import pathlib
import tempfile
from types import SimpleNamespace

from PIL import Image,ImageDraw

from hexa_v31.app import pipeline

vision=importlib.import_module('hexa_v31.vision.vision')


def foundation(signature):
    return {'status':'PASS','backend_used':'FLORENCE2_SAM2','candidates':[],'masks':[],'diagnostics':{},'cache_state':{'status':'CACHE_HIT','reason':None,'signature':signature},'error':None}


class CachedFoundation:
    def __init__(self,signature):self.signature=signature;self.calls=0
    def analyze(self,*_args):
        self.calls+=1;data=foundation(self.signature)
        return SimpleNamespace(status='PASS',backend_used='FLORENCE2_SAM2',cache_state=data['cache_state'],error=None,to_dict=lambda:data)


with tempfile.TemporaryDirectory(prefix='hexa_foundation_route_') as raw:
    root=pathlib.Path(raw);image_path=root/'scene.png';spec=root/'SCENE_TEST.json';final_root=root/'scene_vision';cache_root=root/'cache'
    image=Image.new('RGB',(240,135),'white');ImageDraw.Draw(image).ellipse((65,25,175,125),fill=(30,120,220));image.save(image_path)
    scene={'scene_id':'SCENE_TEST','units':[{'unit_id':'U1','semantic_name':'actor','type':'CONCEPT','role':'PRIMARY'}]};spec.write_text(json.dumps(scene),encoding='utf-8')
    first=vision.analyze_scene(scene,image_path,final_root,foundation_result=foundation('FOUNDATION_A'))
    assert first.cache_state['status']=='GENERATED',first.cache_state
    assert vision.cached_final_foundation_scene(scene,image_path,final_root)

    calls=[]
    def worker(_python,_ext,_spec,image,out_dir,foundation_path=None):
        calls.append({'out_dir':str(out_dir),'foundation':bool(foundation_path)})
        result=json.loads(pathlib.Path(foundation_path).read_text(encoding='utf-8')) if foundation_path else None
        return dataclasses.asdict(vision.analyze_scene(scene,image,out_dir,foundation_result=result))

    client=CachedFoundation('FOUNDATION_A')
    second,fr,routed=pipeline._analyze_scene_with_foundation_routing('python',root,scene,image_path,spec,final_root,client,True,cache_root,{},worker=worker)
    assert fr.cache_state['status']=='CACHE_HIT' and routed
    assert second['cache_state']['status']=='HIT',second['cache_state']
    assert calls==[{'out_dir':str(final_root),'foundation':True}],calls

    # Planning/QA source changes are intentionally absent from the Vision signature.
    third,_,routed=pipeline._analyze_scene_with_foundation_routing('python',root,scene,image_path,spec,final_root,client,True,cache_root,{'motion_qa_source_changed':True},worker=worker)
    assert routed and third['cache_state']['status']=='HIT',third['cache_state']

    client.signature='FOUNDATION_B'
    changed_foundation,_,routed=pipeline._analyze_scene_with_foundation_routing('python',root,scene,image_path,spec,final_root,client,True,cache_root,{},worker=worker)
    assert routed and changed_foundation['cache_state']['status']=='INVALIDATED_DEPENDENCY_CHANGED',changed_foundation['cache_state']

    old=vision.VISION_CACHE_DEPENDENCIES['foundation_reconstruction'];vision.VISION_CACHE_DEPENDENCIES['foundation_reconstruction']=old+'__TEST_CHANGE'
    try:
        assert not vision.cached_final_foundation_scene(scene,image_path,final_root)
        changed_dependency=vision.analyze_scene(scene,image_path,final_root,foundation_result=foundation('FOUNDATION_B'))
        assert changed_dependency.cache_state['status']=='INVALIDATED_DEPENDENCY_CHANGED',changed_dependency.cache_state
    finally:vision.VISION_CACHE_DEPENDENCIES['foundation_reconstruction']=old

    ImageDraw.Draw(image).rectangle((5,5,15,15),fill='black');image.save(image_path)
    changed_image=vision.analyze_scene(scene,image_path,final_root,foundation_result=foundation('FOUNDATION_B'))
    assert changed_image.cache_state['status']=='MISS_INPUT_CHANGED',changed_image.cache_state

    legacy_root=root/'legacy_scene_vision'
    legacy_first=vision.analyze_scene(scene,image_path,legacy_root)
    legacy_second,legacy_fr,legacy_routed=pipeline._analyze_scene_with_foundation_routing('python',root,scene,image_path,spec,legacy_root,CachedFoundation('UNUSED'),False,cache_root,{},worker=worker)
    assert legacy_first.cache_state['status']=='GENERATED'
    assert legacy_fr is None and not legacy_routed and legacy_second['cache_state']['status']=='HIT',legacy_second['cache_state']

print('V31_FOUNDATION_SCENE_CACHE_ROUTING_PASS FOUNDATION_CACHE_HIT SCENE_VISION_CACHE_HIT RECONSTRUCTION_RERUN_COUNT=0')
