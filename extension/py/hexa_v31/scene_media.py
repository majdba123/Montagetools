"""Backward-compatible render facade with interaction guards and encoded certification."""
from __future__ import annotations
import pathlib
from .render import scene_media as _implementation
from .util import write_json
globals().update({key: value for key, value in vars(_implementation).items() if key not in {'__name__','__package__','__loader__','__spec__','__file__','__cached__'}})
_base_render_scene_media=_implementation.render_scene_media

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
    manifest=_base_render_scene_media(framed_render_map,motion_plan,vision_results,text_plan,guarded_graphics,out_dir,cache_dir,width=width,height=height,fps=fps,logger=logger)
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
