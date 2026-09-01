from __future__ import annotations
import argparse,json,os,pathlib,subprocess,sys,venv

PACKAGES=(
    'torch==2.5.1','torchvision==0.20.1','transformers==4.49.0',
    'huggingface-hub==0.28.1','safetensors==0.5.2','sam2==1.1.0',
    'numpy==1.26.4','Pillow==11.1.0','hydra-core==1.3.2','iopath==0.1.10','tqdm==4.67.1'
)

def run(cmd,env=None,timeout=7200):
    cp=subprocess.run([str(x) for x in cmd],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=timeout)
    if cp.returncode:raise RuntimeError('Command failed: '+' '.join(map(str,cmd))+'\n'+cp.stdout[-6000:])
    return cp.stdout

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--runtime-root',required=True);p.add_argument('--registry',required=True);a=p.parse_args(argv)
    runtime=pathlib.Path(a.runtime_root);env_root=runtime/'foundation_vision'/'venv';models=runtime/'foundation_vision'/'models';models.mkdir(parents=True,exist_ok=True)
    python=env_root/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():venv.EnvBuilder(with_pip=True,clear=False).create(env_root)
    run([python,'-m','pip','install','--disable-pip-version-check','--no-input','--upgrade','pip==24.3.1'])
    env=os.environ.copy();env['SAM2_BUILD_CUDA']='0'
    run([python,'-m','pip','install','--disable-pip-version-check','--no-input','--only-binary=:all:','--index-url','https://download.pytorch.org/whl/cpu','torch==2.5.1','torchvision==0.20.1'],env=env)
    run([python,'-m','pip','install','--disable-pip-version-check','--no-input',*PACKAGES[2:]],env=env)
    registry=json.loads(pathlib.Path(a.registry).read_text(encoding='utf-8'));quality=[x for x in registry['models'] if x['profile']=='quality']
    for item in quality:
        target=models/item['local_path'];target.mkdir(parents=True,exist_ok=True)
        patterns=['*.json','*.txt','*.py','*.model','*.tiktoken','*.safetensors','tokenizer*','vocab*','merges*'] if item['backend']=='florence2' else [item['checkpoint_file']]
        code="from huggingface_hub import snapshot_download;snapshot_download(repo_id=%r,revision=%r,local_dir=%r,local_dir_use_symlinks=False,allow_patterns=%r)"%(item['model_id'],item['revision'],str(target),patterns)
        run([python,'-c',code],env=env)
    # Integrity is checked by the production registry implementation under the isolated interpreter.
    extension_py=pathlib.Path(a.registry).resolve().parents[1]/'py';probe_env=env.copy();probe_env['PYTHONPATH']=str(extension_py)
    code="from hexa_v31.vision.foundation.model_registry import resolve_models;import json;print(json.dumps(resolve_models(%r,%r,'QUALITY')))"%(str(pathlib.Path(a.registry).resolve()),str(models))
    run([python,'-c',code],env=probe_env)
    print(json.dumps({'status':'PASS','foundation_python_exe':str(python),'foundation_models_root':str(models),'foundation_model_registry':str(pathlib.Path(a.registry).resolve()),'foundation_vision_enabled':True,'dependency_versions':list(PACKAGES)},separators=(',',':')))
    return 0
if __name__=='__main__':raise SystemExit(main())
