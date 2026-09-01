from __future__ import annotations
import argparse, json, pathlib, sys
from dataclasses import asdict
from hexa_v31.vision import analyze_scene
from hexa_v31.util import read_json

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--scene-json',required=True);p.add_argument('--image',required=True);p.add_argument('--out-dir',required=True);p.add_argument('--foundation-result')
    a=p.parse_args(argv)
    scene=read_json(a.scene_json);foundation=read_json(a.foundation_result) if a.foundation_result else None;r=analyze_scene(scene,a.image,a.out_dir,logger=None,foundation_result=foundation)
    print('HEXA_V31_VISION_RESULT='+json.dumps(asdict(r),ensure_ascii=False,separators=(',',':')))
    return 0
if __name__=='__main__':raise SystemExit(main())
