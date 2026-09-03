from __future__ import annotations
import html, math, os, pathlib, shutil, subprocess
from typing import Any
from hexa_v31.util import write_json, write_text, ffmpeg_exe
from hexa_v31.motion_solver import camera_motion_gain

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


def _planner_event_window(event:dict)->tuple[float,float]:
    return (
        float(event.get('physical_start_seconds',event.get('start_seconds',0.0))),
        float(event.get('physical_end_seconds',event.get('end_seconds',0.0))),
    )


def planner_render_map_completeness_qa(motion_plan:dict, mapped_events:list[dict], fps:float=30.0)->dict:
    """Prove the final planner representation survived integration unchanged."""
    from hexa_v31.visual_timeline_coverage import visual_timeline_coverage_qa
    expected=[
        e for e in (motion_plan.get('events') or [])
        if not e.get('suppressed_by_card_density')
        and _planner_event_window(e)[1]>_planner_event_window(e)[0]+1e-6
    ]
    expected_ids=[str(e.get('event_id')) for e in expected]
    mapped_ids=[str(e.get('event_id')) for e in mapped_events]
    expected_set=set(expected_ids);mapped_set=set(mapped_ids)
    duplicate_expected=sorted({eid for eid in expected_ids if expected_ids.count(eid)>1})
    duplicate_mapped=sorted({eid for eid in mapped_ids if mapped_ids.count(eid)>1})
    missing=sorted(expected_set-mapped_set);unexpected=sorted(mapped_set-expected_set)
    expected_by={str(e.get('event_id')):e for e in expected}
    mapped_by={str(e.get('event_id')):e for e in mapped_events}
    lifetime_mismatches=[];missing_sources=[]
    for eid in sorted(expected_set & mapped_set):
        source=expected_by[eid];mapped=mapped_by[eid]
        source_window=_planner_event_window(source);mapped_window=_planner_event_window(mapped)
        if any(abs(a-b)>1e-6 for a,b in zip(source_window,mapped_window)):
            lifetime_mismatches.append({
                'event_id':eid,
                'planner_physical_window_seconds':[round(source_window[0],6),round(source_window[1],6)],
                'render_map_physical_window_seconds':[round(mapped_window[0],6),round(mapped_window[1],6)],
            })
        path=mapped.get('source_path')
        if not path or not pathlib.Path(path).is_file():
            missing_sources.append({'event_id':eid,'source_path':path})
    coverage_plan=dict(motion_plan);coverage_plan['events']=mapped_events
    coverage=visual_timeline_coverage_qa(coverage_plan,fps=fps)
    passed=not (duplicate_expected or duplicate_mapped or missing or unexpected or lifetime_mismatches or missing_sources) and bool(coverage.get('pass'))
    return {
        'schema':'HEXA_PLANNER_RENDER_MAP_COMPLETENESS_QA_V1','pass':passed,
        'expected_renderable_event_count':len(expected),'mapped_event_count':len(mapped_events),
        'expected_renderable_event_ids':expected_ids,'mapped_event_ids':mapped_ids,
        'missing_event_ids':missing,'unexpected_event_ids':unexpected,
        'duplicate_planner_event_ids':duplicate_expected,'duplicate_mapped_event_ids':duplicate_mapped,
        'physical_lifetime_mismatches':lifetime_mismatches,'missing_source_events':missing_sources,
        'visual_timeline_coverage_pass':bool(coverage.get('pass')),
        'visual_timeline_coverage_qa':coverage,
        'authority':'FINAL_PLANNER_SELECTED_SOURCE_BACKED_REPRESENTATION',
    }


def _planner_render_source(package, scenes:dict, vision_row:dict, event:dict)->tuple[str,dict|None,str]:
    """Resolve one final planner event to physical source media without re-planning it."""
    eid=str(event.get('event_id'));sid=str(event.get('scene_id'));pid=str(event.get('physical_id'))
    render_mode=str(event.get('render_mode') or 'UNSPECIFIED')
    if pid=='FULL_SCENE':
        scene=scenes.get(sid)
        if not scene or not scene.get('image'):
            raise PremiereError(f'PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={eid} scene_id={sid} physical_id={pid} render_mode={render_mode} reason=FULL_SCENE_SOURCE_MISSING')
        path=(package.extract_root/scene['image']).resolve()
        if not path.is_file():
            raise PremiereError(f'PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={eid} scene_id={sid} physical_id={pid} render_mode={render_mode} reason=FULL_SCENE_FILE_MISSING source_path={path}')
        return str(path),None,'PLANNER_FULL_SCENE_FALLBACK'
    units={str(u.get('physical_id')):u for u in (vision_row.get('units') or []) if u.get('physical_id') is not None}
    unit=units.get(pid)
    if unit is None:
        raise PremiereError(f'PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={eid} scene_id={sid} physical_id={pid} render_mode={render_mode} reason=VISION_PHYSICAL_UNIT_MISSING')
    source=event.get('source_layer_path') or unit.get('layer_path') or unit.get('mask_path')
    if not source:
        raise PremiereError(f'PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={eid} scene_id={sid} physical_id={pid} render_mode={render_mode} reason=SOURCE_PATH_MISSING')
    path=pathlib.Path(source).resolve()
    if not path.is_file():
        raise PremiereError(f'PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={eid} scene_id={sid} physical_id={pid} render_mode={render_mode} reason=SOURCE_FILE_MISSING source_path={path}')
    return str(path),unit,'PLANNER_PHYSICAL_UNIT'


def build_layer_render_map(package, audio_path:str|os.PathLike, alignment:dict, vision_results:list[dict], motion_plan:dict, out_dir:str|os.PathLike, width:int=1920,height:int=1080,fps:float=30.0,logger=None,project_save_path:str|os.PathLike|None=None,production_mp4_path:str|os.PathLike|None=None,export_preset_path:str|os.PathLike|None=None):
    """Translate the final planner state into source-backed renderer inputs.

    Vision mode is analysis evidence, never final render representation authority.
    """
    out=pathlib.Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    vis={str(v['scene_id']):v for v in vision_results};scenes={str(s['scene_id']):s for s in package.scenes}
    planner_events=[
        e for e in (motion_plan.get('events') or [])
        if not e.get('suppressed_by_card_density')
        and _planner_event_window(e)[1]>_planner_event_window(e)[0]+1e-6
    ]
    track_clips=[[] for _ in range(5)]
    edit_events=[];markers=[];timeline_items=[];max_end=0
    for srow in (motion_plan.get('scenes') or []):
        sid=str(srow['scene_id'])
        if sid not in vis:raise PremiereError(f'PLANNER_RENDER_MAP_SCENE_UNRESOLVED scene_id={sid} reason=VISION_RESULT_MISSING')
        startf=int(round(float(srow['start_seconds'])*fps));endf=max(startf+1,int(round(float(srow['end_seconds'])*fps)));max_end=max(max_end,endf)
        markers.append({'name':sid,'frame':startf,'seconds':startf/float(fps)})
    for e in planner_events:
        sid=str(e.get('scene_id'));v=vis.get(sid)
        if v is None:
            raise PremiereError(f"PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={e.get('event_id')} scene_id={sid} physical_id={e.get('physical_id')} render_mode={e.get('render_mode')} reason=VISION_RESULT_MISSING")
        source_path,unit,source_authority=_planner_render_source(package,scenes,v,e)
        src_w=float(v.get('width') or width);src_h=float(v.get('height') or height)
        if src_w<=0 or src_h<=0:
            raise PremiereError(f"PLANNER_RENDER_MAP_EVENT_UNRESOLVED event_id={e.get('event_id')} scene_id={sid} physical_id={e.get('physical_id')} render_mode={e.get('render_mode')} reason=INVALID_SOURCE_DIMENSIONS")
        fit=min(width/src_w,height/src_h);kind=str(e.get('kind') or '');role=str(e.get('attention_priority') or e.get('semantic_role') or '').upper()
        if kind in ('MAIN_NARRATOR','SECONDARY_CHARACTER'):tr=3
        elif role=='PRIMARY' or str(e.get('physical_id'))=='FULL_SCENE':tr=2
        else:tr=1
        ps,pe=_planner_event_window(e);cf=max(0,int(round(ps*fps)));ce=max(cf+1,int(round(pe*fps)))
        clipname=f"{e.get('event_id')}__{e.get('physical_id')}"
        track_clips[tr].append(_clipitem(clipname,clipname,source_path,cf,ce,int(src_w),int(src_h),fps))
        camera_scale=float(e.get('reference_camera_scale',1.0));base_scale=fit*100.0*camera_scale
        timeline_items.append({
            'clip_display_name':clipname,'source_path':source_path,'start_frame':cf,'end_frame':ce,
            'start_seconds':ps,'end_seconds':pe,'physical_start_seconds':ps,'physical_end_seconds':pe,
            'base_track_tier':tr,'scene_id':sid,'item_role':'PLANNER_RENDER_EVENT',
            'event_id':e.get('event_id'),'physical_id':e.get('physical_id'),'render_mode':e.get('render_mode'),
            'source_authority':source_authority,'base_position_norm':[0.5,0.5],
            'base_fit_scale_percent':base_scale,'source_width':int(src_w),'source_height':int(src_h),
        })
        ee=dict(e);neutral=[width/2.0,height/2.0]
        if str(e.get('physical_id'))=='FULL_SCENE':
            ee.update({
                'clip_display_name':clipname,'track_index':tr,'source_path':source_path,'render_source_authority':source_authority,
                'base_fit_scale_percent':base_scale,'rest_position_px':neutral,'start_position_px':neutral,'end_position_px':neutral,
                'exit_position_px':neutral,'micro_position_px':neutral,'rest_position_norm':[0.5,0.5],
                'start_position_norm':[0.5,0.5],'end_position_norm':[0.5,0.5],'exit_position_norm':[0.5,0.5],
                'micro_position_norm':[0.5,0.5],'sequence_width':width,'sequence_height':height,
                'layer_canvas_mode':'FULL_SCENE_OPAQUE_CANVAS','premiere_motion_coordinate_contract':'FULL_CANVAS_INTRINSIC_NORMALIZED_POSITION',
            })
        else:
            center=(unit or {}).get('center_norm') or e.get('card_rest_position_norm') or [0.5,0.5]
            sx=float(e.get('start_x_norm',center[0]));sy=float(e.get('start_y_norm',center[1]))
            ex=float(e.get('end_x_norm',center[0]));ey=float(e.get('end_y_norm',center[1]))
            xx=float(e.get('exit_x_norm',ex));xy=float(e.get('exit_y_norm',ey));mx=float(e.get('micro_x_norm',ex));my=float(e.get('micro_y_norm',ey))
            motion_gain=camera_motion_gain(camera_scale);canvas_w=src_w*fit;canvas_h=src_h*fit;offx=(width-canvas_w)/2;offy=(height-canvas_h)/2
            def pos(nx,ny):return [offx+nx*canvas_w,offy+ny*canvas_h]
            start_pos=pos(sx,sy);end_pos=pos(ex,ey);exit_pos=pos(xx,xy);micro_pos=pos(mx,my);relative_motion_scale=camera_scale*motion_gain
            def rel(abspos):return [neutral[0]+(abspos[0]-end_pos[0])*relative_motion_scale,neutral[1]+(abspos[1]-end_pos[1])*relative_motion_scale]
            start_rel=rel(start_pos);exit_rel=rel(exit_pos);micro_rel=rel(micro_pos)
            def normp(pp):return [pp[0]/float(width),pp[1]/float(height)]
            ee.update({
                'clip_display_name':clipname,'track_index':tr,'source_path':source_path,'render_source_authority':source_authority,
                'base_fit_scale_percent':base_scale,'rest_position_px':neutral,'start_position_px':start_rel,'end_position_px':neutral,
                'exit_position_px':exit_rel,'micro_position_px':micro_rel,'rest_position_norm':[0.5,0.5],
                'start_position_norm':normp(start_rel),'end_position_norm':[0.5,0.5],
                'exit_position_norm':normp(exit_rel),'micro_position_norm':normp(micro_rel),
                'sequence_width':width,'sequence_height':height,
                'layer_canvas_mode':(unit or {}).get('layer_canvas_mode',e.get('layer_canvas_mode','FULL_SCENE_ALPHA_CANVAS')),
                'premiere_motion_coordinate_contract':'FULL_CANVAS_INTRINSIC_NORMALIZED_POSITION',
            })
            ee['motion_amplitude_gain']=motion_gain;ee['relative_motion_scale']=relative_motion_scale
            ee['drift_dx_px']=float(e.get('drift_dx_norm',0.0))*float(width)*relative_motion_scale;ee['drift_dy_px']=float(e.get('drift_dy_norm',0.0))*float(height)*relative_motion_scale
            ee['focus_beats']=[dict(fb,dx_px=float(fb.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(fb.get('dy_norm',0.0))*float(height)*relative_motion_scale) for fb in (e.get('focus_beats') or [])]
            ee['story_beats']=[dict(sb,dx_px=float(sb.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(sb.get('dy_norm',0.0))*float(height)*relative_motion_scale) for sb in (e.get('story_beats') or [])]
            ee['story_actions']=[dict(sa,dx_px=float(sa.get('dx_norm',0.0))*float(width)*relative_motion_scale,dy_px=float(sa.get('dy_norm',0.0))*float(height)*relative_motion_scale,arc_px=float(sa.get('arc_norm',0.0))*float(height)*relative_motion_scale) for sa in (e.get('story_actions') or [])]
        edit_events.append(ee)
    timeline_items,required_video_tracks,lane_counts=_assign_track_lanes(timeline_items)
    clip_track={r['clip_display_name']:r['premiere_track_index'] for r in timeline_items}
    for e in edit_events:e['track_index']=clip_track.get(e['clip_display_name'],e.get('track_index',0))
    completeness=planner_render_map_completeness_qa(motion_plan,edit_events,fps=fps)
    if not completeness.get('pass'):
        if logger:logger.log('ERROR','PLANNER_RENDER_MAP_COMPLETENESS_QA_FAILED',expected=completeness.get('expected_renderable_event_count'),mapped=completeness.get('mapped_event_count'),missing_event_ids=completeness.get('missing_event_ids'),unexpected_event_ids=completeness.get('unexpected_event_ids'),lifetime_mismatches=completeness.get('physical_lifetime_mismatches'),coverage_pass=completeness.get('visual_timeline_coverage_pass'))
        raise PremiereError('PLANNER_RENDER_MAP_COMPLETENESS_QA_FAILED '+f"expected={completeness.get('expected_renderable_event_count')} mapped={completeness.get('mapped_event_count')} missing_event_ids={completeness.get('missing_event_ids')} unexpected_event_ids={completeness.get('unexpected_event_ids')} coverage_pass={completeness.get('visual_timeline_coverage_pass')}")
    if logger:logger.log('PASS','PLANNER_RENDER_MAP_COMPLETENESS_QA',expected=completeness.get('expected_renderable_event_count'),mapped=completeness.get('mapped_event_count'),missing_event_ids=[],unexpected_event_ids=[],coverage_pass=True)
    audio_path=str(pathlib.Path(audio_path).resolve());audio_clip=_clipitem('VOICE_OVER','FINAL_VOICE_OVER',audio_path,0,max_end,0,0,fps,track_kind='audio')
    tracks=''.join('<track>'+''.join(c)+'</track>' for c in track_clips);marker_xml=''.join(f'<marker><name>{_xml(m["name"])}</name><in>{m["frame"]}</in><out>-1</out></marker>' for m in markers);rate=_rate_xml(fps)
    xmeml=f'''<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="HEXA_V31_MASTER"><name>HEXA_V31_MASTER</name><duration>{max_end}</duration>{rate}<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode><media><video><format><samplecharacteristics>{rate}<width>{width}</width><height>{height}</height><anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format>{tracks}</video><audio><format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format><track>{audio_clip}</track></audio></media>{marker_xml}</sequence></xmeml>'''
    xml_path=out/'HEXA_V31_PREMIERE_TIMELINE_DIAGNOSTIC_ONLY.xml';write_text(xml_path,xmeml)
    bootstrap=_ensure_sequence_bootstrap(out,width,height,fps,logger=logger);runtime_report=out/'HEXA_V31_PREMIERE_RUNTIME_REPORT.json'
    edit_map={
        'schema':'HEXA_PREMIERE_EDIT_MAP_V31','version':'2.2',
        'project':{'width':width,'height':height,'fps':fps,'master_sequence':'HEXA_V31_MASTER','source_scene_width':vision_results[0]['width'] if vision_results else None,'source_scene_height':vision_results[0]['height'] if vision_results else None},
        'rules':motion_plan.get('hard_invariants') or {},'events':edit_events,'planner_render_map_completeness_qa':completeness,'fifth_element_overlays':[],
        'assembly':{'execution_mode':'ENGINE_LAYER_RENDER_MAP','xml_import_forbidden':True,'sequence_bootstrap_media':str(bootstrap.resolve()),'sequence_name':'HEXA_V31_MASTER','video_items':timeline_items,
            'audio_items':[{'clip_display_name':'FINAL_VOICE_OVER','source_path':audio_path,'start_frame':0,'end_frame':max_end,'start_seconds':0.0,'end_seconds':max_end/fps,'premiere_track_index':0,'item_role':'FINAL_VOICE_OVER'}],
            'markers':markers,'required_video_tracks':required_video_tracks,'required_audio_tracks':1,'lane_counts_by_semantic_tier':{str(k):v for k,v in lane_counts.items()},'ticks_per_second':254016000000,
            'runtime_report_path':str(runtime_report.resolve()),'project_save_path':str(pathlib.Path(project_save_path).resolve()) if project_save_path else None,'production_mp4_path':str(pathlib.Path(production_mp4_path).resolve()) if production_mp4_path else None,'export_preset_path':str(pathlib.Path(export_preset_path).resolve()) if export_preset_path else None,'export_preset_materialize_path':str((out/'HEXA_V31_RUNTIME_EXPORT_PRESET.epr').resolve()),'export_required':False,'export_policy':'ENGINE_FINAL_MP4_ALREADY_CERTIFIED__PREMIERE_PROJECT_ONLY','sequence_settings_authority':'PHYSICAL_BOOTSTRAP_MEDIA_1920x1080_30P_STEREO_48K','render_representation_authority':'FINAL_PLANNER_SELECTED_SOURCE_BACKED_EVENTS'},
        'note':'V31 integration map. Vision mode never suppresses planner-selected physical events; exact source-backed event completeness is certified before rendering.'
    }
    map_path=out/'HEXA_V31_LAYER_RENDER_MAP.json';write_json(map_path,edit_map)
    if logger:logger.log('PASS','LAYER_RENDER_MAP_BUILT',execution_mode='ENGINE_LAYER_RENDER_MAP',diagnostic_xml=str(xml_path),edit_map=str(map_path),events=len(edit_events),expected_planner_events=len(planner_events),duration_frames=max_end,required_video_tracks=required_video_tracks,lane_counts=lane_counts)
    return {'timeline_xml':str(xml_path),'edit_map':str(map_path),'duration_frames':max_end,'event_count':len(edit_events),'execution_mode':'ENGINE_LAYER_RENDER_MAP','required_video_tracks':required_video_tracks,'bootstrap_media':str(bootstrap),'runtime_report':str(runtime_report),'planner_render_map_completeness_qa':completeness}


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
