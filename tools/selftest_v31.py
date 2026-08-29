from __future__ import annotations
import argparse,pathlib,tempfile
from types import SimpleNamespace
from PIL import Image,ImageDraw
from hexa_v31.vision import analyze_scene
from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa,preset_story_plan_qa
from hexa_v31.premiere import build_layer_render_map,build_premiere_handoff_from_scene_media
from hexa_v31.scene_media import render_scene_media
from hexa_v31.util import read_json,write_json
from hexa_v31.preset_authority import authority as preset_authority


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--extension-root',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    ext=pathlib.Path(args.extension_root);out=pathlib.Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);checks={}
    with tempfile.TemporaryDirectory(prefix='hexa_v31_selftest_') as raw:
        td=pathlib.Path(raw)
        # One clean primary + three clean secondary supports on a white stage.  The
        # physical separation is intentional: V31 must never invent child cutouts.
        img=Image.new('RGB',(640,360),(255,255,255));d=ImageDraw.Draw(img)
        d.rounded_rectangle((230,90,410,270),radius=28,fill=(46,142,232),outline=(24,34,54),width=8)
        d.ellipse((65,145,125,205),fill=(248,187,52),outline=(24,34,54),width=6)
        d.rounded_rectangle((495,125,565,195),radius=12,fill=(105,190,109),outline=(24,34,54),width=6)
        d.polygon([(475,265),(525,225),(575,265),(525,305)],fill=(218,92,92),outline=(24,34,54))
        p=td/'SCENE_001.png';img.save(p)
        phrase='Ø§Ù„Ø±ØµÙŠØ¯ Ø§Ù„Ù…ØªØ§Ø­ ÙŠØ¸Ù‡Ø± Ù…Ø¹ Ø«Ù„Ø§Ø« Ø¥Ø´Ø§Ø±Ø§Øª ØªÙˆØ¶ÙŠØ­ÙŠØ©'
        def unit(uid,name,role,typ='CONCEPT'):
            return {'unit_id':uid,'semantic_name':name,'type':typ,'role':role,'narrative_function':'SELFTEST','appear_trigger':None,'focus_trigger':None,'exit_trigger':None}
        scene={'scene_id':'SCENE_001','order':1,'image':'SCENE_001.png','script_span':{'global_char_start':0,'global_char_end':len(phrase),'text':phrase},'purpose':'V31 runtime selftest','visual_concept':'clean primary with three supporting symbols','units':[unit('UNIT_MAIN','balance','PRIMARY'),unit('UNIT_S1','support_one','SUPPORTING'),unit('UNIT_S2','support_two','SUPPORTING'),unit('UNIT_S3','support_three','SUPPORTING')],'visual_progression':[]}
        v=analyze_scene(scene,p,td/'vision');vd=v.__dict__
        checks['vision_reconstruction_pass']=bool(v.reconstruction_pass);checks['vision_mode']=v.mode
        checks['top_level_only']=all(int(u.get('hierarchy_level') or 0)==0 for u in v.units)
        matting_summary=v.artifacts.get('matting_summary') or {}
        checks['edge_matting_ready']=bool(matting_summary.get('layer_count',0)>=1)
        checks['opaque_stage_leak_fraction']=float(matting_summary.get('max_opaque_stage_leak_fraction') or 0.0)
        checks['opaque_stage_leak_hard_gate']=checks['opaque_stage_leak_fraction']<=0.004
        if not v.reconstruction_pass or v.mode=='FLAT_SCENE' or not checks['top_level_only'] or not checks['edge_matting_ready'] or not checks['opaque_stage_leak_hard_gate']:raise RuntimeError('V31 cutout/matting selftest failed')
        plan={'project_id':'HEXA_V31_0_25_RUNTIME_SELFTEST','canonical_script':{'text':phrase},'scenes':[scene]};pkg=SimpleNamespace(plan=plan,scenes=[scene],extract_root=td)
        align={'method':'SELFTEST','scene_count':1,'scene_timings':[{'scene_id':'SCENE_001','start':0.0,'end':3.6,'trigger_start':0.2}],'word_timings':[],'quality':{'scene_timing_projection':'SELFTEST','internal_trigger_support':False}}
        motion=build_motion_plan(plan,align,[vd],ext/'resources/HEXA_EDITING_RULES_V20.json',ext/'resources/HEXA_REFERENCE_QA_PROFILE_V20.json',fps=30.0)
        pqa=preset_motion_qa(motion,30.0);sqa=preset_story_plan_qa(motion,[vd])
        checks['preset_motion_qa_pass']=pqa['pass'];checks['preset_story_qa_pass']=sqa['pass']
        composition=sqa.get('composition_qa') or {}
        checks['composition_constraint_qa_pass']=bool(composition.get('pass',False))
        checks['composition_constraint_authority']=composition.get('authority')
        checks['visual_card_count']=len((motion.get('visual_cards') or {}).get('cards') or [])
        checks['preset_authority_ready']=preset_authority().get('status')=='HARD_LOCK'
        checks['legacy_motion_disabled']=bool((motion.get('hard_invariants') or {}).get('legacy_motion_heuristics_disabled'))
        if not pqa['pass'] or not sqa['pass'] or not checks['composition_constraint_qa_pass'] or checks['visual_card_count']!=1 or not checks['preset_authority_ready'] or not checks['legacy_motion_disabled']:
            raise RuntimeError('V31 user preset/story choreography contract failed: '+str(pqa.get('failures') or sqa.get('failures')))
        render_map=build_layer_render_map(pkg,td/'voice.wav',align,[vd],motion,td/'render_map',width=640,height=360,fps=30.0)
        text_plan={'events':[],'text_event_count':0};graphics_plan={'events':[],'event_count':0}
        media=render_scene_media(read_json(render_map['edit_map']),motion,[vd],text_plan,graphics_plan,td/'animated',td/'cache',width=640,height=360,fps=30.0)
        checks['continuous_clip_count']=media['scene_count'];checks['visual_card_count_rendered']=media.get('visual_card_count');checks['frame_blends']=media.get('full_frame_crossfade_count',-1)+media.get('mask_wipe_count',-1)+media.get('white_dip_count',-1)
        if media['scene_count']!=1 or checks['frame_blends']!=0 or not pathlib.Path(media['clips'][0]['source_path']).is_file():raise RuntimeError('V31 continuous story media selftest failed')
        (td/'voice.wav').write_bytes(b'RIFF'+b'0'*4096)
        prem=build_premiere_handoff_from_scene_media(pkg,td/'voice.wav',align,media,motion,td/'premiere',width=640,height=360,fps=30.0)
        em=read_json(prem['edit_map']);checks['premiere_execution_mode']=em['assembly']['execution_mode'];checks['premiere_final_events_count']=len(em['events'])
        if checks['premiere_execution_mode']!='PREMIERE_2022_ANIMATED_SCENE_MEDIA_ASSEMBLY' or checks['premiere_final_events_count']!=0:raise RuntimeError('Final Premiere pre-rendered timeline contract failed')
        host=(ext/'jsx'/'host.jsx').read_text(encoding='utf-8',errors='ignore');checks['host_no_apply_motion_stage']=("stage='APPLY_MOTION'" not in host and 'PREMIERE_2022_ANIMATED_SCENE_MEDIA_ASSEMBLY' in host)
        if not checks['host_no_apply_motion_stage']:raise RuntimeError('Host still contains active final APPLY_MOTION stage')
    report={'schema':'HEXA_V31_RUNTIME_SELFTEST','version':'31.0.25','status':'PASS','checks':checks};write_json(out,report);print('HEXA_V31_RUNTIME_SELFTEST_PASS');return 0
if __name__=='__main__':raise SystemExit(main())

