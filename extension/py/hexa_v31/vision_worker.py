from __future__ import annotations
import argparse, json, pathlib, sys
from dataclasses import asdict
from .vision import analyze_scene
from .util import read_json

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--scene-json',required=True);p.add_argument('--image',required=True);p.add_argument('--out-dir',required=True)
    a=p.parse_args(argv)
    scene=read_json(a.scene_json);r=analyze_scene(scene,a.image,a.out_dir,logger=None)
    print('HEXA_V31_VISION_RESULT='+json.dumps(asdict(r),ensure_ascii=False,separators=(',',':')))
    return 0
if __name__=='__main__':raise SystemExit(main())
