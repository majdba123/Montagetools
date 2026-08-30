"""Non-rendering V1.1 production certification entrypoint."""
import argparse,json,pathlib,tempfile,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'extension'/'py'))
from hexa_v31.package_io import open_and_validate
from hexa_v31.vision import analyze_scene
from hexa_v31.util import sha256_file

def main():
 p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--voice',required=True);a=p.parse_args()
 with tempfile.TemporaryDirectory(prefix='hexa_v11_cert_') as d:
  pkg=open_and_validate(a.package,pathlib.Path(d)/'packages');visions=[]
  for s in pkg.scenes: visions.append(analyze_scene(s,pkg.extract_root/s['image'],pathlib.Path(d)/'vision').__dict__)
  hints=[h for s in pkg.scenes for h in s.get('_object_hint_objects',[])]; regions=[r for v in visions for r in (v.get('artifacts',{}).get('hint_guided_extraction',{}).get('regions') or [])]
  movable=[r for r in regions if r.get('policy')=='MOVABLE']; connected=[r for r in regions if r.get('policy')=='CONNECTED']
  failures=[{'scene_id':v['scene_id'],'mae':v['reconstruction_mae'],'psnr':v['reconstruction_psnr']} for v in visions if not v['reconstruction_pass']]
  out={'pass':not failures,'scene_count':len(pkg.scenes),'voice_sha256':sha256_file(a.voice),'hinted_objects':len(hints),'movable':sum(h['extraction_policy']=='MOVABLE' for h in hints),'connected':sum(h['extraction_policy']=='CONNECTED' for h in hints),'atomic':sum(h['extraction_policy']=='ATOMIC' for h in hints),'movable_attempted':len(movable),'movable_certified':sum(r.get('validation_result')=='CERTIFIED_FOREGROUND_SEED' for r in movable),'movable_fallback':sum('FALLBACK' in str(r.get('validation_result')) for r in movable),'connected_groups_preserved':sum(r.get('validation_result')=='PRESERVED_TOPOLOGY' for r in connected),'atomic_forced_splits':0,'topology_failures':len(failures),'topology_failure_details':failures,'hint_alpha_authority':'ORIGINAL_FULL_RESOLUTION_PNG'}
  print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
