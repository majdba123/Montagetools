from pathlib import Path
import tempfile
from PIL import Image,ImageDraw
import numpy as np
from hexa_v31.vision import analyze_scene
with tempfile.TemporaryDirectory() as raw:
    td=Path(raw);im=Image.new('RGB',(640,360),'white');d=ImageDraw.Draw(im)
    # white interior intentionally enclosed by dark outline: border-connected background
    # removal must not punch a transparent hole through it.
    d.ellipse((180,70,460,330),fill='white',outline=(20,25,40),width=12)
    d.ellipse((255,145,385,275),fill=(70,150,230),outline=(20,25,40),width=8)
    p=td/'s.png';im.save(p)
    scene={'scene_id':'S','units':[{'unit_id':'U','semantic_name':'icon','type':'CONCEPT','role':'PRIMARY'}]}
    r=analyze_scene(scene,p,td/'out')
    assert all(int(u.get('hierarchy_level') or 0)==0 for u in r.units)
    lp=Path(r.units[0]['layer_path']);a=np.array(Image.open(lp).convert('RGBA'))[:,:,3]
    assert a[100,320]>245,'enclosed white interior was cut away'
    assert r.source_mode=='BORDER_CONNECTED_WHITE_STAGE_MATTE'
print('V31_CUTOUT_INTEGRITY_PASS')
