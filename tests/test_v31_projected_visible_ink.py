import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel
from hexa_v31.visual_density import build_visual_density_report

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);sparse=root/'sparse.png';dense=root/'dense.png'
    a=Image.new('RGBA',(400,400),(0,0,0,0));ImageDraw.Draw(a).ellipse((175,175,225,225),fill=(20,40,80,255));a.save(sparse)
    Image.new('RGBA',(400,400),(20,40,80,255)).save(dense)
    model=ProjectedVisibleInkModel();rect=(.2,.2,.5,.5)
    assert model.project({'source_path':str(sparse)},rect) < model.project({'source_path':str(dense)},rect)*.05
    def event(eid,path):
        return {'event_id':eid,'visual_card_id':'C','source_path':str(path),'start_seconds':0.,'end_seconds':2.,'source_bbox_norm':[0,0,.5,.5],'card_rest_position_norm':[.45,.45],'layout_scale_multiplier':1.,'attention_priority':'PRIMARY','matting':{'opaque_foreground_fraction':1.0},'preset_actions':[]}
    card={'card_id':'C','start_seconds':0.,'end_seconds':2.,'duration_seconds':2.,'constraint_layout':{'placements':{}},'universal_scene_grammar':{'archetype':'SINGLE_FOCUS'}}
    sparse_report=build_visual_density_report({'visual_cards':{'cards':[card]},'events':[event('S',sparse)]})
    dense_report=build_visual_density_report({'visual_cards':{'cards':[card]},'events':[event('D',dense)]})
    assert sparse_report['median_estimated_alpha_coverage'] < dense_report['median_estimated_alpha_coverage']*.05
    assert sparse_report['visible_ink_authority']=='HEXA_PROJECTED_VISIBLE_INK_V1'
print('V31_PROJECTED_VISIBLE_INK_PASS')
