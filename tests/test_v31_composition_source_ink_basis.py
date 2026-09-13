import hashlib
import tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from hexa_v31.composition_solver import source_object_visible_fraction,_fp
from hexa_v31.projected_visible_ink import ProjectedVisibleInkModel

with tempfile.TemporaryDirectory() as raw:
    path=Path(raw)/'source.png'
    image=Image.new('RGBA',(400,400),(0,0,0,0))
    ImageDraw.Draw(image).rectangle((100,100,149,299),fill=(20,40,80,255))
    image.save(path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    event={'event_id':'OBJECT','source_layer_path':str(path),
           'source_bbox_norm':[.25,.25,.25,.5],
           'matting':{'opaque_foreground_fraction':.0625}}
    geometry=_fp(event)
    fraction=source_object_visible_fraction(event)
    assert abs(fraction-.5)<1e-9,fraction
    event['visible_ink_fraction']=fraction
    assert (_fp(event).w,_fp(event).h)==(geometry.w,geometry.h)
    model=ProjectedVisibleInkModel()
    assert abs(model.project(event,(.1,.1,.2,.3))-.03)<1e-9
    assert source_object_visible_fraction(event)==fraction
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    # Same object support on a larger transparent canvas retains its object
    # coverage; transparent padding does not make the object itself sparser.
    padded=Image.new('RGBA',(800,800),(0,0,0,0));padded.paste(image,(200,200))
    padded_path=Path(raw)/'padded.png';padded.save(padded_path)
    assert source_object_visible_fraction(dict(event,source_layer_path=str(padded_path),source_bbox_norm=[.375,.375,.125,.25]))==fraction
    assert source_object_visible_fraction(dict(event,source_layer_path=str(Path(raw)/'missing.png'))) is None
print('V31_COMPOSITION_SOURCE_INK_BASIS_PASS')
