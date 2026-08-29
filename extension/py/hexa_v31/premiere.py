from __future__ import annotations
import html, math, os, pathlib, shutil, subprocess
from typing import Any
from .util import write_json, write_text, ffmpeg_exe
from .motion_solver import camera_motion_gain

class PremiereError(RuntimeError): pass


def _url(path:str|os.PathLike)->str:
    return pathlib.Path(path).resolve().as_uri()


def _xml(s): return html.escape(str(s),quote=True)


def _rate_xml(fps:float):
    ntsc='TRUE' if abs(fps-29.97)<0.02 or abs(fps-59.94)<0.02 else 'FALSE'
    tb=30 if abs(fps-29.97)<0.02 else int(round(fps))
    return f'<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate>'


def _clipitem(clip_id,name,path,start,end,media_w,media_h,fps,track_kind='video'):
    """Legacy diagnostic FCP-XML emitter.

    V31.0.1 does not import this XML into Premiere.  It is retained only as a
    forensic artifact because real Premiere 2022 proved that app.project.importFiles()
    is not a reliable FCP-XML project/sequence importer.
    """
    dur=max(1,end-start)
    rate=_rate_xml(fps)
    if track_kind=='video':
        return f'''<clipitem id="{_xml(clip_id)}"><name>{_xml(name)}</name><enabled>TRUE</enabled><duration>{dur}</duration>{rate}<start>{start}</start><end>{end}</end><in>0</in><out>{dur}</out><file id="file-{_xml(clip_id)}"><name>{_xml(pathlib.Path(path).name)}</name><pathurl>{_xml(_url(path))}</pathurl>{rate}<duration>999999</duration><media><video><samplecharacteristics>{rate}<width>{media_w}</width><height>{media_h}</height><pixelaspectratio>square</pixelaspectratio></samplecharacteristics></video></media></file></clipitem>'''
    return f'''<clipitem id="{_xml(clip_id)}"><name>{_xml(name)}</name><enabled>TRUE</enabled><duration>{dur}</duration>{rate}<start>{start}</start><end>{end}</end><in>0</in><out>{dur}</out><file id="file-{_xml(clip_id)}"><name>{_xml(pathlib.Path(path).name)}</name><pathurl>{_xml(_url(path))}</pathurl>{rate}<duration>{dur}</duration><media><audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio></media></file></clipitem>'''


def _ensure_sequence_bootstrap(out:pathlib.Path,width:int,height:int,fps:float,logger=None)->pathlib.Path:
    """Create a tiny real video+audio clip whose only job is to define Premiere sequence settings.

    Premiere 2022's public ExtendScript API can create a sequence from clips.  A
    physical 1920x1080/30p clip is a much stronger settings authority than relying
    on the user's current default sequence preset.  The clip is removed immediately
    after the sequence is created.
    """
    p=out/'HEXA_V31_SEQUENCE_BOOTSTRAP_1920x1080_30P.mp4'
    if p.is_file() and p.stat().st_size>4096:
        return p
    ff=ffmpeg_exe()
    if not ff:
        raise PremiereError('FFmpeg is unavailable while creating the Premiere sequence bootstrap media.')
    fps_s=(str(int(round(fps))) if abs(fps-round(fps))<1e-6 else f'{fps:.6f}')
    cmd=[
        ff,'-y','-v','error',
        '-f','lavfi','-i',f'color=c=black:s={int(width)}x{int(height)}:r={fps_s}:d=1',
        '-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000',
        '-t','1','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','64k','-movflags','+faststart',str(p)
    ]
    cp=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
    if cp.returncode!=0 or not p.is_file() or p.stat().st_size<=4096:
        raise PremiereError('Failed to create Premiere sequence bootstrap media: '+(cp.stdout or '')[-2000:])
    if logger: logger.log('PASS','PREMIERE_SEQUENCE_BOOTSTRAP_READY',path=str(p),width=width,height=height,fps=fps)
    return p


def _assign_track_lanes(items:list[dict[str,Any]])->tuple[list[dict[str,Any]],int,dict[int,int]]:
    """Interval-color each visual tier so pre-roll overlap never causes same-track collisions.

    Lower semantic tiers are allocated first, so every primary/character lane is
    physically above all lower-tier lanes in Premiere.
    """
    by_tier:dict[int,list[dict[str,Any]]]={}
    for row in items:
        by_tier.setdefault(int(row.get('base_track_tier',0)),[]).append(row)
    out=[];offset=0;lane_counts={}
    for tier in sorted(by_tier):
        lane_ends:list[int]=[]
        rows=sorted(by_tier[tier],key=lambda r:(int(r['start_frame']),int(r['end_frame']),str(r['clip_display_name'])))
        for row in rows:
            st=int(row['start_frame']);en=max(st+1,int(row['end_frame']))
            lane=None
            for i,last_end in enumerate(lane_ends):
                if st>=last_end:
                    lane=i;break
            if lane is None:
                lane=len(lane_ends);lane_ends.append(-1)
            lane_ends[lane]=en
            rr=dict(row);rr['premiere_track_index']=offset+lane;rr['lane_index_within_tier']=lane
            out.append(rr)
        lane_counts[tier]=len(lane_ends)
        offset+=len(lane_ends)
    return out,max(1,offset),lane_counts


def build_layer_render_map(package, audio_path:str|os.PathLike, alignment:dict, vision_results:list[dict], motion_plan:dict, out_dir:str|os.PathLike, width:int=1920,height:int=1080,fps:float=30.0,logger=None,project_save_path:str|os.PathLike|None=None,production_mp4_path:str|os.PathLike|None=None,export_preset_path:str|os.PathLike|None=None):
    out=pathlib.Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    vis={v['scene_id']:v for v in vision_results}; scenes={s['scene_id']:s for s in package.scenes}
    events=motion_plan['events']; ev_by_scene={}
    for e in events: ev_by_scene.setdefault(e['scene_id'],[]).append(e)

    # Keep the old XML as a read-only diagnostic artifact.  Real Premiere execution
    # in V31.0.1 is native DOM assembly and never imports this XML.
    track_clips=[[] for _ in range(5)]
    edit_events=[]; markers=[];timeline_items=[]
    max_end=0
    event_item_by_id={}
    for srow in motion_plan['scenes']:
        sid=srow['scene_id']; v=vis[sid]
        startf=int(round(srow['start_seconds']*fps)); endf=max(startf+1,int(round(srow['end_seconds']*fps))); max_end=max(max_end,endf)
        markers.append({'name':sid,'frame':startf,'seconds':startf/float(fps)})
        if v['mode']=='FLAT_SCENE':
            src=str((package.extract_root/scenes[sid]['image']).resolve()); name=f'{sid}__FULL_SCENE'
            track_clips[2].append(_clipitem(name,name,src,startf,endf,v['width'],v['height'],fps))
            fit=min(width/float(v['width']),height/float(v['height']))
            timeline_items.append({'clip_display_name':name,'source_path':src,'start_frame':startf,'end_frame':endf,'start_seconds':startf/fps,'end_seconds':endf/fps,'base_track_tier':2,'scene_id':sid,'item_role':'FLAT_SCENE','base_position_norm':[0.5,0.5],'base_fit_scale_percent':fit*100.0*float((srow.get('reference_camera_fit') or {}).get('camera_scale',1.0)),'source_width':v['width'],'source_height':v['height']})
            flat_ev=next((e for e in ev_by_scene.get(sid,[]) if e.get('physical_id')=='FULL_SCENE'),None)
            if flat_ev:
                ee=dict(flat_ev); ee.update({'clip_display_name':name,'track_index':2,'source_path':src,'base_fit_scale_percent':fit*100.0*float(flat_ev.get('reference_camera_scale',1.0)),'rest_position_px':[width/2,height/2],'start_position_px':[width/2,height/2],'end_position_px':[width/2,height/2],'exit_position_px':[width/2,height/2],'micro_position_px':[width/2,height/2],'rest_position_norm':[0.5,0.5],'start_position_norm':[0.5,0.5],'end_position_norm':[0.5,0.5],'exit_position_norm':[0.5,0.5],'micro_position_norm':[0.5,0.5],'sequence_width':width,'sequence_height':height,'premiere_motion_coordinate_contract':'FULL_CANVAS_INTRINSIC_NORMALIZED_POSITION'})
                edit_events.append(ee);event_item_by_id[ee['event_id']]=name
        else:
            bg=v['artifacts']['background']; name=f'{sid}__BACKGROUND'
            track_clips[0].append(_clipitem(name,name,bg,startf,endf,v['width'],v['height'],fps))
            fit=min(width/float(v['width']),height/float(v['height']))
            timeline_items.append({'clip_display_name':name,'source_path':str(pathlib.Path(bg).resolve()),'start_frame':startf,'end_frame':endf,'start_seconds':startf/fps,'end_seconds':endf/fps,'base_track_tier':0,'scene_id':sid,'item_role':'BACKGROUND','base_position_norm':[0.5,0.5],'base_fit_scale_percent':fit*100.0,'source_width':v['width'],'source_height':v['height']})
            units={u['physical_id']:u for u in v['units']}
            for e in ev_by_scene.get(sid,[]):
                if e['physical_id']=='FULL_SCENE': continue
                u=units[e['physical_id']]; path=str(pathlib.Path(u['layer_path']).resolve()); kind=e.get('kind')
                if kind in ('MAIN_NARRATOR','SECONDARY_CHARACTER'): tr=3
                elif u.get('semantic_role')=='PRIMARY': tr=2
                else: tr=1
                cf=max(0,int(round(e['start_seconds']*fps))); ce=max(cf+1,int(round(float(e.get('end_seconds',srow['end_seconds']))*fps)))
                clipname=f"{e['event_id']}__{u['physical_id']}"
                track_clips[tr].append(_clipitem(clipname,clipname,path,cf,ce,v['width'],v['height'],fps))
                src_w=float(v['width']); src_h=float(v['height']); fit=min(width/src_w,height/src_h)
                timeline_items.append({'clip_display_name':clipname,'source_path':path,'start_frame':cf,'end_frame':ce,'start_seconds':cf/fps,'end_seconds':ce/fps,'base_track_tier':tr,'scene_id':sid,'item_role':'MOTION_EVENT','event_id':e['event_id'],'base_position_norm':[0.5,0.5],'base_fit_scale_percent':fit*100.0*float(e.get('reference_camera_scale',1.0)),'source_width':v['width'],'source_height':v['height']})
                camera_scale=float(e.get('reference_camera_scale',1.0))
                motion_gain=camera_motion_gain(camera_scale)
                canvas_w=src_w*fit; canvas_h=src_h*fit; offx=(width-canvas_w)/2; offy=(height-canvas_h)/2
                def pos(normx,normy): return [offx+normx*canvas_w,offy+normy*canvas_h]
                start_pos=pos(e['start_x_norm'],e['start_y_norm']); end_pos=pos(e['end_x_norm'],e['end_y_norm'])
                base_scale=fit*100.0*camera_scale
                exit_pos=pos(e.get('exit_x_norm',e['end_x_norm']),e.get('exit_y_norm',e['end_y_norm']))
                micro_pos=pos(e.get('micro_x_norm',e['end_x_norm']),e.get('micro_y_norm',e['end_y_norm']))
                ee=dict(e)
                neutral=[width/2.0,height/2.0]
                relative_motion_scale=camera_scale*motion_gain
                def rel(abspos): return [neutral[0]+(abspos[0]-end_pos[0])*relative_motion_scale, neutral[1]+(abspos[1]-end_pos[1])*relative_motion_scale]
                # Physical unit PNGs are full-scene transparent canvases. Their static/rest composition
                # is therefore always centered and fitted exactly once. the engine render stage carries ONLY relative travel around the neutral
                # sequence center; no cropped-media Position math and no Transform effect dependency exists.
                
                start_rel=rel(start_pos); exit_rel=rel(exit_pos); micro_rel=rel(micro_pos)
                def normp(pp): return [pp[0]/float(width),pp[1]/float(height)]
                ee.update({'clip_display_name':clipname,'track_index':tr,'source_path':path,'base_fit_scale_percent':base_scale,'rest_position_px':neutral,'start_position_px':start_rel,'end_position_px':neutral,'exit_position_px':exit_rel,'micro_position_px':micro_rel,'rest_position_norm':[0.5,0.5],'start_position_norm':normp(start_rel),'end_position_norm':[0.5,0.5],'exit_position_norm':normp(exit_rel),'micro_position_norm':normp(micro_rel),'sequence_width':width,'sequence_height':height,'layer_canvas_mode':u.get('layer_canvas_mode','FULL_SCENE_ALPHA_CANVAS'),'premiere_motion_coordinate_contract':'FULL_CANVAS_INTRINSIC_NORMALIZED_POSITION'})
                ee['motion_amplitude_gain']=motion_gain; ee['relative_motion_scale']=relative_motion_scale; ee['drift_dx_px']=float(e.get('drift_dx_norm',0.0))*float(width)*relative_motion_scale; ee['drift_dy_px']=float(e.get('drift_dy_norm',0.0))*float(height)*relative_motion_scale
                ee['focus_beats']=[dict(fb,dx_px=float(fb.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(fb.get('dy_norm',0.0))*float(height)*relative_motion_scale) for fb in (e.get('focus_beats') or [])]
                ee['story_beats']=[dict(sb,dx_px=float(sb.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(sb.get('dy_norm',0.0))*float(height)*relative_motion_scale) for sb in (e.get('story_beats') or [])]
                ee['story_actions']=[dict(sa,dx_px=float(sa.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(sa.get('dy_norm',0.0))*float(height)*relative_motion_scale,arc_px=float(sa.get('arc_norm',0.0))*float(height)*relative_motion_scale) for sa in (e.get('story_actions') or [])]
                edit_events.append(ee);event_item_by_id[ee['event_id']]=clipname

    # Allocate non-overlapping physical tracks. This remains mandatory because V31's
    # legal pre-roll deliberately overlaps neighboring scene clips by a few frames.
    timeline_items,required_video_tracks,lane_counts=_assign_track_lanes(timeline_items)
    clip_track={r['clip_display_name']:r['premiere_track_index'] for r in timeline_items}
    for e in edit_events:
        e['track_index']=clip_track.get(e['clip_display_name'],e.get('track_index',0))

    # audio full timeline
    audio_path=str(pathlib.Path(audio_path).resolve())
    audio_clip=_clipitem('VOICE_OVER','FINAL_VOICE_OVER',audio_path,0,max_end,0,0,fps,track_kind='audio')
    tracks=''.join('<track>'+''.join(c)+'</track>' for c in track_clips)
    marker_xml=''.join(f'<marker><name>{_xml(m["name"])}</name><in>{m["frame"]}</in><out>-1</out></marker>' for m in markers)
    rate=_rate_xml(fps)
    xmeml=f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="HEXA_V31_MASTER"><name>HEXA_V31_MASTER</name><duration>{max_end}</duration>{rate}<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode><media><video><format><samplecharacteristics>{rate}<width>{width}</width><height>{height}</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format>{tracks}</video><audio><format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format><track>{audio_clip}</track></audio></media>{marker_xml}</sequence></xmeml>'''
    xml_path=out/'HEXA_V31_PREMIERE_TIMELINE_DIAGNOSTIC_ONLY.xml'; write_text(xml_path,xmeml)

    bootstrap=_ensure_sequence_bootstrap(out,width,height,fps,logger=logger)
    runtime_report=out/'HEXA_V31_PREMIERE_RUNTIME_REPORT.json'
    edit_map={
        'schema':'HEXA_PREMIERE_EDIT_MAP_V31','version':'2.0',
        'project':{'width':width,'height':height,'fps':fps,'master_sequence':'HEXA_V31_MASTER','source_scene_width':vision_results[0]['width'] if vision_results else None,'source_scene_height':vision_results[0]['height'] if vision_results else None},
        'rules':motion_plan['hard_invariants'],'events':edit_events,'fifth_element_overlays':[],
        'assembly':{
            'execution_mode':'ENGINE_LAYER_RENDER_MAP',
            'xml_import_forbidden':True,
            'sequence_bootstrap_media':str(bootstrap.resolve()),
            'sequence_name':'HEXA_V31_MASTER',
            'video_items':timeline_items,
            'audio_items':[{'clip_display_name':'FINAL_VOICE_OVER','source_path':audio_path,'start_frame':0,'end_frame':max_end,'start_seconds':0.0,'end_seconds':max_end/fps,'premiere_track_index':0,'item_role':'FINAL_VOICE_OVER'}],
            'markers':markers,
            'required_video_tracks':required_video_tracks,
            'required_audio_tracks':1,
            'lane_counts_by_semantic_tier':{str(k):v for k,v in lane_counts.items()},
            'ticks_per_second':254016000000,
            'runtime_report_path':str(runtime_report.resolve()),
            'project_save_path':str(pathlib.Path(project_save_path).resolve()) if project_save_path else None,
            'production_mp4_path':str(pathlib.Path(production_mp4_path).resolve()) if production_mp4_path else None,
            'export_preset_path':str(pathlib.Path(export_preset_path).resolve()) if export_preset_path else None,
            'export_preset_materialize_path':str((out/'HEXA_V31_RUNTIME_EXPORT_PRESET.epr').resolve()),
            'export_required':False,
            'export_policy':'ENGINE_FINAL_MP4_ALREADY_CERTIFIED__PREMIERE_PROJECT_ONLY',
            'sequence_settings_authority':'PHYSICAL_BOOTSTRAP_MEDIA_1920x1080_30P_STEREO_48K'
        },
        'note':'V31.0.25 engine render map. Full-scene semantic layers + motion DNA are rendered into animated scene media before Premiere; this map is never executed by Premiere.'
    }
    map_path=out/'HEXA_V31_LAYER_RENDER_MAP.json'; write_json(map_path,edit_map)
    if logger: logger.log('PASS','LAYER_RENDER_MAP_BUILT',execution_mode='ENGINE_LAYER_RENDER_MAP',diagnostic_xml=str(xml_path),edit_map=str(map_path),events=len(edit_events),duration_frames=max_end,required_video_tracks=required_video_tracks,lane_counts=lane_counts)
    return {'timeline_xml':str(xml_path),'edit_map':str(map_path),'duration_frames':max_end,'event_count':len(edit_events),'execution_mode':'ENGINE_LAYER_RENDER_MAP','required_video_tracks':required_video_tracks,'bootstrap_media':str(bootstrap),'runtime_report':str(runtime_report)}


def build_premiere_handoff_from_scene_media(package, audio_path:str|os.PathLike, alignment:dict, scene_media:dict, motion_plan:dict, out_dir:str|os.PathLike, width:int=1920,height:int=1080,fps:float=30.0,logger=None,project_save_path:str|os.PathLike|None=None,production_mp4_path:str|os.PathLike|None=None,export_preset_path:str|os.PathLike|None=None):
    """Build the real Premiere 2022 handoff from already-animated Scene video clips.

    V31.0.1 deliberately does not ask Premiere to keyframe PNG stills. Adobe Premiere
    has a long-standing still-image ComponentParam keyframe failure class; the user's
    real V21.0.0 run reproduced it as ``addKey failed: null``.  Motion and selective
    typography are therefore physically rendered into 1920x1080 Scene MP4 clips first.
    Premiere remains responsible only for native sequence assembly, voice placement, and project
    save/readback. The final MP4 is already assembled and certified by the V31 engine from
    the exact same animated Scene clips before Premiere is invoked.
    """
    out=pathlib.Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    clips=scene_media.get('clips') or []
    if not clips: raise PremiereError('Animated scene media manifest is empty.')
    max_end=max(int(x['end_frame']) for x in clips)
    markers=[{'name':x['scene_id'],'frame':int(x['start_frame']),'seconds':float(x['start_seconds'])} for x in clips]
    video_items=[]
    for x in clips:
        p=pathlib.Path(x['source_path']).resolve()
        if not p.is_file() or p.stat().st_size<=4096: raise PremiereError('Animated scene media missing/too small: '+str(p))
        video_items.append({
            'clip_display_name':x['clip_display_name'],'source_path':str(p),
            'start_frame':int(x['start_frame']),'end_frame':int(x['end_frame']),
            'start_seconds':float(x['start_seconds']),'end_seconds':float(x['end_seconds']),
            'premiere_track_index':0,'item_role':'ANIMATED_SCENE_MEDIA',
            'scene_id':x['scene_id'],'source_width':width,'source_height':height,
            'motion_event_count':int(x.get('motion_event_count',0)),'text_event_count':int(x.get('text_event_count',0)),
        })
    # Diagnostic XML now describes the actual video media Premiere will receive.
    rate=_rate_xml(fps)
    diag_track=''.join(_clipitem(x['clip_display_name'],x['clip_display_name'],x['source_path'],int(x['start_frame']),int(x['end_frame']),width,height,fps) for x in clips)
    audio_path=str(pathlib.Path(audio_path).resolve())
    audio_clip=_clipitem('VOICE_OVER','FINAL_VOICE_OVER',audio_path,0,max_end,0,0,fps,track_kind='audio')
    marker_xml=''.join(f'<marker><name>{_xml(m["name"])}</name><in>{m["frame"]}</in><out>-1</out></marker>' for m in markers)
    xmeml=f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="HEXA_V31_MASTER"><name>HEXA_V31_MASTER</name><duration>{max_end}</duration>{rate}<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode><media><video><format><samplecharacteristics>{rate}<width>{width}</width><height>{height}</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format><track>{diag_track}</track></video><audio><format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format><track>{audio_clip}</track></audio></media>{marker_xml}</sequence></xmeml>'''
    xml_path=out/'HEXA_V31_PREMIERE_TIMELINE_DIAGNOSTIC_ONLY.xml';write_text(xml_path,xmeml)
    bootstrap=_ensure_sequence_bootstrap(out,width,height,fps,logger=logger)
    runtime_report=out/'HEXA_V31_PREMIERE_RUNTIME_REPORT.json'
    edit_map={
        'schema':'HEXA_PREMIERE_EDIT_MAP_V31','version':'2.1',
        'project':{'width':width,'height':height,'fps':fps,'master_sequence':'HEXA_V31_MASTER'},
        'rules':motion_plan.get('hard_invariants') or {},
        'events':[],
        'pre_rendered_motion_event_count':int(scene_media.get('motion_event_count',0)),
        'selective_text_event_count':int(scene_media.get('text_event_count',0)),
        'assembly':{
            'execution_mode':'PREMIERE_2022_ANIMATED_SCENE_MEDIA_ASSEMBLY',
            'xml_import_forbidden':True,
            'sequence_bootstrap_media':str(bootstrap.resolve()),
            'sequence_name':'HEXA_V31_MASTER',
            'video_items':video_items,
            'audio_items':[{'clip_display_name':'FINAL_VOICE_OVER','source_path':audio_path,'start_frame':0,'end_frame':max_end,'start_seconds':0.0,'end_seconds':max_end/fps,'premiere_track_index':0,'item_role':'FINAL_VOICE_OVER'}],
            'markers':markers,'required_video_tracks':1,'required_audio_tracks':1,'ticks_per_second':254016000000,
            'runtime_report_path':str(runtime_report.resolve()),
            'project_save_path':str(pathlib.Path(project_save_path).resolve()) if project_save_path else None,
            'production_mp4_path':str(pathlib.Path(production_mp4_path).resolve()) if production_mp4_path else None,
            'export_preset_path':str(pathlib.Path(export_preset_path).resolve()) if export_preset_path else None,
            'export_preset_materialize_path':str((out/'HEXA_V31_RUNTIME_EXPORT_PRESET.epr').resolve()),
            'export_required':False,'export_policy':'ENGINE_FINAL_MP4_ALREADY_CERTIFIED__PREMIERE_PROJECT_ONLY',
            'sequence_settings_authority':'PHYSICAL_BOOTSTRAP_MEDIA_1920x1080_30P_STEREO_48K',
            'motion_execution_authority':'PRE_RENDERED_ANIMATED_SCENE_MEDIA',
            'typography_execution_authority':'PRE_RENDERED_SELECTIVE_TYPOGRAPHY',
            'final_mp4_authority':'ENGINE_CONCAT_OF_IDENTICAL_ANIMATED_SCENE_MEDIA',
        },
        'note':'V31.0.25: Premiere receives actual 1920x1080 animated Scene video media. No PNG keyframes, no Transform effect, no intrinsic Motion addKey calls. Selective Arabic typography is rendered only where semantically justified and negative space allows it.'
    }
    map_path=out/'HEXA_V31_PREMIERE_EDIT_MAP.json';write_json(map_path,edit_map)
    if logger: logger.log('PASS','PREMIERE_HANDOFF_BUILT',execution_mode=edit_map['assembly']['execution_mode'],diagnostic_xml=str(xml_path),edit_map=str(map_path),animated_scene_clips=len(video_items),pre_rendered_motion_events=edit_map['pre_rendered_motion_event_count'],selective_text_events=edit_map['selective_text_event_count'],duration_frames=max_end,required_video_tracks=1)
    return {'timeline_xml':str(xml_path),'edit_map':str(map_path),'duration_frames':max_end,'event_count':edit_map['pre_rendered_motion_event_count'],'execution_mode':edit_map['assembly']['execution_mode'],'required_video_tracks':1,'bootstrap_media':str(bootstrap),'runtime_report':str(runtime_report)}
