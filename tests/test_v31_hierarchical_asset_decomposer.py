import tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from hexa_v31.vision import analyze_scene

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);image=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(image)
    # Two detached source-backed lobes intentionally map to one semantic root.
    draw.rounded_rectangle((90,90,250,270),20,fill=(30,90,180))
    draw.ellipse((275,115,435,255),fill=(220,130,30))
    source=root/'asset.png';image.save(source)
    scene={'scene_id':'GENERIC','units':[{'unit_id':'OBJECT','semantic_name':'object','type':'CONCEPT','role':'PRIMARY'}]}
    result=analyze_scene(scene,source,root/'out')
    roots=[u for u in result.units if u['hierarchy_level']==0]
    children=[u for u in result.units if u['hierarchy_level']>0]
    assert len(roots)==1 and roots[0]['root_id']
    assert len(children)>=2,result.artifacts['hierarchy_decisions']
    assert all(c['parent_id']==roots[0]['root_id'] and c['reveal_safe'] for c in children)
    assert all(Path(c['mask_path']).is_file() for c in children)
print('V31_HIERARCHICAL_ASSET_DECOMPOSER_PASS')
