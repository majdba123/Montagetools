"""Backward-compatible render facade with interaction guards and encoded certification."""
from __future__ import annotations
import hashlib, importlib, inspect, pathlib
from .render import scene_media as _implementation
from .util import write_json
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
_base_render_scene_media=_implementation.render_scene_media


def _renderer_dependency_signature()->str:
    """Version scene-media cache by the code that actually produces pixels.

    Motion/text plans already participate in each scene signature, but a renderer or
    typography implementation change can alter pixels without changing those plans.
    Namespacing the cache by implementation bytes prevents a stale previous render from
    surviving a production code update. This is generic and package-independent.
    """
    from hexa_v31.typography import render_text_rgba
    from hexa_v31.composition_solver import composition_state_at
    files={pathlib.Path(_implementation.__file__).resolve()}
    for module_name in ('hexa_v31.typography.premium','hexa_v31.typography.premium_v2'):
        module=importlib.import_module(module_name)
        files.add(pathlib.Path(module.__file__).resolve())
    for fn in (render_text_rgba,composition_state_at):
        source=inspect.getsourcefile(fn)
        if source:files.add(pathlib.Path(source).resolve())
    digest=hashlib.sha256()
    for path in sorted(files,key=lambda p:str(p).lower()):
        digest.update(str(path.name).encode('utf-8'));digest.update(b'\0')
        digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()


def render_scene_media(render_edit_map,motion_plan,vision_results,text_plan,graphics_plan,out_dir,cache_dir,width=1920,height=1080,fps=30.0,logger=None):
    framed_render_map=render_edit_map;framing_report=None
    if motion_plan.get('interaction_engine') is not None:
        from hexa_v31.interaction.source_framing import normalize_render_sources
        framed_render_map,framing_report=normalize_render_sources(render_edit_map,cache_dir,logger=logger)
    guarded_graphics=graphics_plan;graphics_guard=None
    if motion_plan.get('interaction_engine') is not None:
        from hexa_v31.interaction.graphics_guard import guard_relationship_graphics
        guarded_graphics=guard_relationship_graphics(graphics_plan,motion_plan,fps=fps)
        graphics_guard=guarded_graphics.get('interaction_graphics_guard')
        if logger and graphics_guard:logger.log('PASS','INTERACTION_GRAPHICS_GUARD',relationship_graphics=graphics_guard.get('relationship_graphic_count'),suppressed=graphics_guard.get('suppressed_count'),clamped=graphics_guard.get('clamped_count'))
    renderer_signature=_renderer_dependency_signature()
    pixel_cache=pathlib.Path(cache_dir)/('scene_media_pixels_'+renderer_signature[:16])
    pixel_cache.mkdir(parents=True,exist_ok=True)
    if logger:logger.log('INFO','SCENE_MEDIA_RENDERER_CACHE_NAMESPACE',signature=renderer_signature[:16],cache=str(pixel_cache))
    manifest=_base_render_scene_media(framed_render_map,motion_plan,vision_results,text_plan,guarded_graphics,out_dir,pixel_cache,width=width,height=height,fps=fps,logger=logger)
    manifest['renderer_dependency_sha256']=renderer_signature
    composition_sources=pathlib.Path(out_dir)/'HEXA_V31_COMPOSITION_RENDER_SOURCES.json'
    write_json(composition_sources,dict(framed_render_map,
        composition_text_events=list((text_plan or {}).get('events') or []),
        composition_graphic_events=list((guarded_graphics or {}).get('events') or [])))
    manifest['composition_render_map_path']=str(composition_sources)
    if motion_plan.get('interaction_engine') is not None:
        from hexa_v31.interaction.pixel_qa import verify_encoded_interactions
        clip=(manifest.get('clips') or [{}])[0];report=verify_encoded_interactions(str(clip.get('source_path') or ''),motion_plan,fps=fps)
        manifest['interaction_pixel_qa']=report
        if graphics_guard is not None:manifest['interaction_graphics_guard']=graphics_guard
        if framing_report is not None:manifest['visible_ink_source_framing']=framing_report
        write_json(pathlib.Path(out_dir)/'HEXA_V31_INTERACTION_PIXEL_QA.json',report)
        write_json(pathlib.Path(out_dir)/'HEXA_V31_INTERACTION_GRAPHICS_GUARD.json',graphics_guard or {'pass':True,'relationship_graphic_count':0,'rows':[]})
        write_json(pathlib.Path(out_dir)/'HEXA_V31_VISIBLE_INK_SOURCE_FRAMING.json',framing_report or {'pass':True,'changed_event_count':0,'rows':[]})
        write_json(pathlib.Path(out_dir)/'HEXA_V31_ANIMATED_SCENE_MEDIA_MANIFEST.json',manifest)
        if logger:logger.log('PASS' if report.get('pass') else 'FAIL','INTERACTION_PIXEL_QA',physical_actions=report.get('physical_action_count'),verified=report.get('verified_action_count'),actionable=report.get('actionable_interaction_count'))
        if not report.get('pass'):raise _implementation.SceneMediaError('INTERACTION_PIXEL_QA_FAILED: '+str((report.get('failures') or [])[:4]))
    return manifest
