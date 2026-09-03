from __future__ import annotations
import dataclasses,hashlib,json,pathlib,tempfile,wave
from types import SimpleNamespace
import cv2,numpy as np
from PIL import Image,ImageDraw
from hexa_v31.vision import analyze_scene
from hexa_v31.motion import build_motion_plan
from hexa_v31.premiere import build_layer_render_map
from hexa_v31.scene_media import render_scene_media
from hexa_v31.preset_story_planner import _select_render_units
from hexa_v31.extraction.actor_validation import classify_actor

ROOT=pathlib.Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def make_foundation(mask_root,scene_id,specs,partial_first=False,signature='foundation-problem1'):
    mask_dir=mask_root/('masks_'+scene_id);mask_dir.mkdir();candidates=[];masks=[]
    for index,(label,box,_color) in enumerate(specs,1):
        x,y,w,h=box;cid=f'{scene_id}_OBJ_{index}'
        arr=np.zeros((360,640),np.uint8)
        if partial_first and index==1:
            pw=max(1,int(round(w*.27)));arr[y:y+h,x:x+pw]=255;bbox_agreement=round(pw/float(w),4)
        else:
            arr[y:y+h,x:x+w]=255;bbox_agreement=1.0
        mp=mask_dir/(cid+'.png');Image.fromarray(arr).save(mp)
        candidates.append({'candidate_id':cid,'semantic_label':label,'description':label,'confidence':.96,'bbox':[x,y,w,h],'source':'FLORENCE_2','semantic_role':'PRIMARY'})
        masks.append({'candidate_id':cid,'mask_path':str(mp),'sam_score':.97,'bbox_agreement':bbox_agreement})
    return {'status':'PASS','backend_used':'FLORENCE2_SAM2','candidates':candidates,'masks':masks,'diagnostics':{'sam2_mask_count':len(masks)},'cache_state':{'status':'CACHE_MISS','reason':'TEST','signature':signature+'-'+scene_id},'error':None}

def make_scene(root,sid,specs,partial,relation,out_root):
    source=root/(sid+'.png');image=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(image)
    for _label,(x,y,w,h),color in specs:draw.rounded_rectangle((x,y,x+w-1,y+h-1),14,fill=color)
    image.save(source)
    units=[{'unit_id':f'{sid}_OBJ_{i}','semantic_name':label,'type':'CONCEPT','role':'PRIMARY','appear_trigger':label.split()[0]} for i,(label,_box,_color) in enumerate(specs,1)]
    scene={'scene_id':sid,'units':units,'visual_progression':[],'script_span':{'global_char_start':0,'global_char_end':20,'text':' '.join(x['semantic_name'] for x in units)},'relation_to_previous':relation}
    foundation=make_foundation(root,sid,specs,partial_first=partial)
    vision=dataclasses.asdict(analyze_scene(scene,source,out_root,foundation_result=foundation))
    return scene,source,vision,foundation

with tempfile.TemporaryDirectory(prefix='hexa_problem1_closure_') as raw:
    root=pathlib.Path(raw)
    clean_specs=[('red object',(95,120,90,90),(225,40,40)),('blue object',(450,120,90,90),(40,85,225))]
    bad_specs=[('green object',(220,100,180,140),(40,175,85))]
    clean_scene,clean_source,clean,_=make_scene(root,'ARBITRARY_CLEAN',clean_specs,False,'START',root/'vision_clean')
    bad_scene,bad_source,bad,_=make_scene(root,'ARBITRARY_BAD_CROP',bad_specs,True,'NEW_IDEA',root/'vision_bad')

    clean_art=clean['artifacts']['foundation_vision'];bad_art=bad['artifacts']['foundation_vision']
    assert clean_art['actor_qa']['pass'] and clean_art['partition_eligibility_pass'],clean_art
    clean_selected,clean_diag=_select_render_units(clean)
    assert clean_diag['foundation_actor_partition'] and all(x['render_mode'] in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} for x in clean_selected),clean_diag

    assert bad_art['reconstruction_qa']['partition_complete'],bad_art['reconstruction_qa']
    assert not bad_art['actor_qa']['pass'],bad_art['actor_qa']
    assert any(x['reason'] in {'CANDIDATE_BBOX_AGREEMENT_LOW','CANDIDATE_ENVELOPE_COVERAGE_LOW'} for x in bad_art['actor_qa']['crop_failures']),bad_art['actor_qa']
    assert not bad_art['partition_eligibility_pass'],bad_art
    bad_selected,bad_diag=_select_render_units(bad)
    assert not bad_diag['foundation_actor_partition'],bad_diag
    assert bad_selected and all(x['render_mode']=='ROOT_ATOMIC' for x in bad_selected),bad_selected

    edge=np.zeros((180,320),np.uint8);edge[0:80,30:100]=255
    edge_policy=classify_actor(edge,edge,{'bbox':(30,0,70,80),'edge_touch':True,'mask_outside_candidate_fraction':0.0})
    assert not edge_policy['translation_safe'] and 'SOURCE_CANVAS_EDGE_CLIPPED' in edge_policy['independence_block_reasons']

    parity_source=root/'CACHE_PARITY.png';im=Image.new('RGB',(640,360),'white');ImageDraw.Draw(im).rounded_rectangle((245,105,395,255),20,fill=(130,65,195));im.save(parity_source)
    parity_specs=[('purple object',(245,105,150,150),(130,65,195))]
    parity_scene={'scene_id':'CACHE_PARITY','units':[{'unit_id':'CACHE_PARITY_OBJ_1','semantic_name':'purple object','type':'CONCEPT','role':'PRIMARY'}]}
    parity_foundation=make_foundation(root,'CACHE_PARITY',parity_specs,False,'foundation-cache-parity')
    cold=dataclasses.asdict(analyze_scene(parity_scene,parity_source,root/'cache_parity',foundation_result=parity_foundation))
    cold_hashes={u['physical_id']:sha(u['layer_path']) for u in cold['units'] if u.get('layer_path')}
    warm=dataclasses.asdict(analyze_scene(parity_scene,parity_source,root/'cache_parity',foundation_result=parity_foundation))
    warm_hashes={u['physical_id']:sha(u['layer_path']) for u in warm['units'] if u.get('layer_path')}
    assert cold['cache_state']['status']=='GENERATED' and warm['cache_state']['status']=='HIT',(cold['cache_state'],warm['cache_state'])
    c2=dict(cold);w2=dict(warm);c2.pop('cache_state',None);w2.pop('cache_state',None)
    assert c2==w2
    assert cold_hashes==warm_hashes
    assert _select_render_units(cold)[0]==_select_render_units(warm)[0]

    scenes=[clean_scene,bad_scene];visions=[clean,bad]
    alignment={'method':'TEST','scene_count':2,'scene_timings':[{'scene_id':clean_scene['scene_id'],'start':0.0,'end':3.0},{'scene_id':bad_scene['scene_id'],'start':3.0,'end':6.0}],
               'word_timings':[{'word':'red','start':.6,'end':.8},{'word':'green','start':3.6,'end':3.8}]}
    plan={'project_id':'PROBLEM1_ARBITRARY_PACKAGE','scenes':scenes}
    motion=build_motion_plan(plan,alignment,visions,ROOT/'extension/resources/HEXA_EDITING_RULES_V20.json',ROOT/'extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json')
    bad_events=[e for e in motion['events'] if e.get('scene_id')==bad_scene['scene_id'] and not e.get('suppressed_by_card_density')]
    assert bad_events and all(e.get('render_mode')=='ROOT_ATOMIC' for e in bad_events),bad_events
    wav=root/'voice.wav'
    with wave.open(str(wav),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*(16000*6))
    package=SimpleNamespace(scenes=[{'scene_id':clean_scene['scene_id'],'image':clean_source.name},{'scene_id':bad_scene['scene_id'],'image':bad_source.name}],extract_root=root)
    mapped=build_layer_render_map(package,wav,alignment,visions,motion,root/'render_map',width=640,height=360,fps=30)
    assert mapped['planner_render_map_completeness_qa']['pass'],mapped['planner_render_map_completeness_qa']
    edit=json.loads(pathlib.Path(mapped['edit_map']).read_text(encoding='utf-8'))
    manifest=render_scene_media(edit,motion,visions,{'events':[]},{'events':[]},root/'rendered',root/'render_cache',width=640,height=360,fps=30)
    assert manifest['visual_timeline_coverage_qa']['pass'] and manifest['encoded_visual_gap_qa']['pass'],manifest
    cap=cv2.VideoCapture(manifest['clips'][0]['source_path'])
    for fi in (15,105,165):
        cap.set(cv2.CAP_PROP_POS_FRAMES,fi);ok,frame=cap.read();assert ok
        assert np.count_nonzero(np.max(255-frame.astype(np.int16),axis=2)>15)>500,(fi,frame.shape)
    cap.release()

print('V31_FOUNDATION_PROBLEM1_CLOSURE_PASS')
