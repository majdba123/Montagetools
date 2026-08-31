from __future__ import annotations
import argparse,hashlib,json,os,pathlib,subprocess,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--voice',required=True);a=ap.parse_args();package=pathlib.Path(a.package).resolve();voice=pathlib.Path(a.voice).resolve()
 if not package.is_file() or not voice.is_file():raise SystemExit('Package or voice missing')
 cfgp=pathlib.Path(os.environ.get('LOCALAPPDATA',''))/'HEXA'/'VideoBuilderV31'/'runtime_config.json';cfg=json.loads(cfgp.read_text(encoding='utf-8'));env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join([str(ROOT/'extension'/'py')]+list(cfg.get('python_import_roots') or []));env['HEXA_FFMPEG']=str(cfg.get('ffmpeg_path') or '')
 state={'schema':'HEXA_CREATIVE_ITERATION_INPUT_AUTHORITY','package':str(package),'package_sha256':sha(package),'voice':str(voice),'voice_sha256':sha(voice),'upstream_cache_policy':'PIPELINE_SIGNATURE_MUST_MATCH_PACKAGE_IMAGE_HINT_AND_AUDIO_HASHES','final_clean_certification':False}
 out=ROOT/'release'/'creative_iteration';out.mkdir(parents=True,exist_ok=True);(out/'input_authority.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
 log=out/'creative_iteration.log'
 cache_authority=pathlib.Path(cfg.get('build_cache_root') or out/'build').resolve();state['durable_build_cache_root']=str(cache_authority);(out/'input_authority.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
 with log.open('w',encoding='utf-8') as f:cp=subprocess.run([sys.executable,'-m','hexa_v31.cli','build','--package',str(package),'--voice',str(voice),'--work-root',str(cache_authority)],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,text=True)
 print(f'EXIT={cp.returncode}\nLOG={log}\nINPUT_AUTHORITY={out / "input_authority.json"}');return cp.returncode
if __name__=='__main__':raise SystemExit(main())
