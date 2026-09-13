from __future__ import annotations

import argparse, hashlib, json, os, pathlib, shutil, subprocess, tempfile, time, uuid, venv, zipfile

TORCH_VERSION = '2.5.1'
TORCHVISION_VERSION = '0.20.1'
CUDA_INDEX = 'https://download.pytorch.org/whl/cu118'
CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
MIN_FOUNDATION_CUDA_VRAM_BYTES = 4 * 1024 ** 3
PACKAGES = (
    'transformers==4.49.0', 'huggingface-hub==0.28.1', 'safetensors==0.5.2',
    'numpy==1.26.4', 'Pillow==11.1.0', 'hydra-core==1.3.2',
    'iopath==0.1.10', 'tqdm==4.67.1', 'opencv-python-headless==4.11.0.86',
    'timm==1.0.15', 'einops==0.8.1',
)

def provision_contract():
    payload={'torch':TORCH_VERSION,'torchvision':TORCHVISION_VERSION,'cuda_index':CUDA_INDEX,
             'cpu_index':CPU_INDEX,'minimum_foundation_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES,
             'packages':PACKAGES}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def run(cmd, env=None, timeout=7200, cwd=None):
    cp = subprocess.run([str(x) for x in cmd], text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, env=env, timeout=timeout,cwd=str(cwd) if cwd else None)
    if cp.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, cmd)) + '\n' + cp.stdout[-6000:])
    return cp.stdout


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def detect_hardware(run_command=run):
    result = {'nvidia_present': False, 'gpu_name': None, 'vram_bytes': 0,
              'compute_capability': None, 'profile': 'LOW_MEMORY', 'cuda_eligible': False,
              'minimum_foundation_cuda_vram_bytes': MIN_FOUNDATION_CUDA_VRAM_BYTES}
    try:
        output = run_command(['nvidia-smi', '--query-gpu=name,memory.total,compute_cap',
                              '--format=csv,noheader,nounits'], timeout=30).splitlines()[0]
        name, memory_mb, capability = [part.strip() for part in output.split(',', 2)]
        vram_bytes=int(float(memory_mb)) * 1024 ** 2
        result.update(nvidia_present=True, gpu_name=name,
                      vram_bytes=vram_bytes,
                      compute_capability=capability,
                      cuda_eligible=bool(vram_bytes>=MIN_FOUNDATION_CUDA_VRAM_BYTES))
        result['profile'] = 'QUALITY' if vram_bytes >= 10 * 1024 ** 3 else 'LOW_MEMORY'
    except Exception as exc:
        result['detection_error'] = str(exc)
    return result


def cuda_probe(python, require_cuda, run_command=run):
    code = ('import json,torch,torchvision; d={"torch":torch.__version__,"torchvision":torchvision.__version__,'
            '"cuda_runtime":torch.version.cuda,"cuda_available":torch.cuda.is_available()};'
            'd.update({"gpu_count":torch.cuda.device_count()});'
            'assert (not %r) or d["cuda_available"],"CUDA wheel loaded but CUDA is unavailable";'
            'device="cuda" if d["cuda_available"] else "cpu";'
            'x=torch.tensor([2.0],device=device);d["tensor_result"]=(x*x+1).item();'
            'd["device"]=device;'
            'd.update({"gpu_name":torch.cuda.get_device_name(0),"vram_bytes":torch.cuda.get_device_properties(0).total_memory} if d["cuda_available"] else {});'
            'print(json.dumps(d))') % bool(require_cuda)
    return json.loads(run_command([python, '-c', code], timeout=300).splitlines()[-1])


def _python(env_root):
    return env_root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def _install_stack(env_root, use_cuda):
    venv.EnvBuilder(with_pip=True, clear=True).create(env_root)
    python = _python(env_root)
    env = os.environ.copy(); env['SAM2_BUILD_CUDA'] = '0'
    run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--upgrade', 'pip==24.3.1'], env=env)
    run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
         '--index-url', CUDA_INDEX if use_cuda else CPU_INDEX,
         f'torch=={TORCH_VERSION}', f'torchvision=={TORCHVISION_VERSION}'], env=env)
    run([python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', *PACKAGES], env=env)
    return python, env


def _install_official_sam2(python, env, authority, scratch, artifact_cache=None):
    scratch.mkdir(parents=True, exist_ok=True)
    git_cache=pathlib.Path(artifact_cache)/'sam2-sparse' if artifact_cache else None
    source_root=None;install_source=None
    if git_cache and (git_cache/'.git').is_dir():
        try:
            head=run(['git','-C',git_cache,'rev-parse','HEAD'],timeout=30).strip()
            dirty=run(['git','-C',git_cache,'status','--short'],timeout=30).strip()
            if head==authority['commit'] and not dirty:
                source_root=git_cache;install_source='OFFICIAL_PINNED_GIT_COMMIT'
        except Exception:pass
    archive = scratch / 'sam2.zip'
    cached = pathlib.Path(artifact_cache) / 'sam2.zip' if artifact_cache else None
    if cached and cached.is_file() and sha256_file(cached) == authority['archive_sha256']:
        shutil.copy2(cached, archive)
    code = ('import urllib.request;urllib.request.urlretrieve(%r,%r)' %
            (authority['archive_url'], str(archive)))
    failures=[]
    for attempt in range(1,5) if not archive.exists() and source_root is None else ():
        try:
            if archive.exists(): archive.unlink()
            run([python, '-c', code], env=env)
            break
        except Exception as exc:
            failures.append(f'attempt {attempt}: {exc}')
            if attempt==4: raise RuntimeError('Official SAM2 archive download failed after retries:\n'+'\n'.join(failures))
            time.sleep(attempt*2)
    actual=authority['archive_sha256']
    if source_root is None:
        actual = sha256_file(archive)
        if actual != authority['archive_sha256']:
            raise RuntimeError(f'SAM2 source archive SHA256 mismatch: {actual}')
        if cached:
            cached.parent.mkdir(parents=True,exist_ok=True)
            if not cached.exists(): shutil.copy2(archive,cached)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(scratch / 'sam2-source')
        roots = [x for x in (scratch / 'sam2-source').iterdir() if x.is_dir()]
        if len(roots) != 1: raise RuntimeError('Unexpected official SAM2 archive layout')
        source_root=roots[0];install_source='OFFICIAL_PINNED_ARCHIVE'
    run([python, 'setup.py', 'install'], env=env,cwd=source_root)
    run([python, '-c', 'import sam2;print(sam2.__file__)'], env=env)
    return {'repository': authority['repository'], 'commit': authority['commit'],
            'archive_sha256': actual, 'install_source': install_source}


def _download_models(python, env, registry, models_root, profile):
    selected = [m for m in registry['models'] if m['profile'] == profile.lower()]
    if {m['backend'] for m in selected} != {'florence2', 'sam2'}:
        raise RuntimeError('Selected profile does not contain both Florence2 and SAM2')
    for index,item in enumerate(selected):
        target = models_root / item['local_path']
        partial = models_root / ('.p' + str(index))
        patterns = (['*.json', '*.txt', '*.py', '*.model', '*.tiktoken', '*.safetensors',
                     'tokenizer*', 'vocab*', 'merges*'] if item['backend'] == 'florence2'
                    else [item['checkpoint_file']])
        code = ('from huggingface_hub import snapshot_download;'
                'snapshot_download(repo_id=%r,revision=%r,local_dir=%r,'
                'local_dir_use_symlinks=False,allow_patterns=%r)') % (
                    item['model_id'], item['revision'], str(partial), patterns)
        completed=False
        try:
            checkpoint = partial / item['checkpoint_file']
            expected_size=int(item.get('expected_file_size') or 0)
            complete_local=checkpoint.is_file() and (not expected_size or checkpoint.stat().st_size==expected_size) and sha256_file(checkpoint)==item['checkpoint_sha256']
            if not complete_local:
                failures=[]
                for attempt in range(1,5):
                    try:
                        run([python, '-c', code], env=env);completed=True;break
                    except Exception as exc:
                        failures.append(f'attempt {attempt}: {exc}')
                        if attempt==4:raise RuntimeError('Model download failed after resumable retries:\n'+'\n'.join(failures))
                        time.sleep(attempt*2)
            else:completed=True
            if not checkpoint.is_file() or (expected_size and checkpoint.stat().st_size!=expected_size) or sha256_file(checkpoint) != item['checkpoint_sha256']:
                raise RuntimeError('Model integrity failure: ' + item['model_id'])
            if target.exists(): shutil.rmtree(target)
            partial.replace(target)
        finally:
            if completed and partial.exists(): shutil.rmtree(partial, ignore_errors=True)
    return selected


def _reuse_existing(destination, registry_path, registry, profile, desired_device):
    report_path = destination / 'provision_report.json'; python = _python(destination / 'venv')
    if not report_path.is_file() or not python.is_file(): return None
    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if report.get('foundation_profile') != profile: return None
        if str(report.get('foundation_device') or '').lower()!=str(desired_device).lower(): return None
        if report.get('sam2_source', {}).get('commit') != registry['sam2_source']['commit']: return None
        env = os.environ.copy(); env['PYTHONPATH'] = str(registry_path.parents[1] / 'py')
        code = ('from hexa_v31.vision.foundation.model_registry import resolve_models,fingerprint;import json;'
                'r=resolve_models(%r,%r,%r);assert set(r)=={"florence2","sam2"};'
                'assert all(x["installation_status"]=="INSTALLED" for x in r.values());'
                'print(fingerprint(%r,%r))') % (str(registry_path), str(destination/'models'), profile,
                                                str(registry_path), profile)
        current = run([python, '-c', code], env=env).splitlines()[-1]
        if current != report.get('registry_fingerprint'): return None
        expected={'torch':TORCH_VERSION,'torchvision':TORCHVISION_VERSION}
        expected.update(dict(item.rsplit('==',1) for item in PACKAGES))
        dep_code=('import importlib.metadata,json;expected=json.loads(%r);'
                  'actual={k:importlib.metadata.version(k) for k in expected};'
                  'assert all(actual[k].split("+")[0]==v for k,v in expected.items()),(expected,actual);print(json.dumps(actual))') % json.dumps(expected)
        dependency_probe=json.loads(run([python,'-c',dep_code],env=env).splitlines()[-1])
        probe = cuda_probe(python, desired_device == 'cuda')
        if str(probe.get('device') or '').lower()!=str(desired_device).lower(): return None
        report.update(status='PASS', reused_existing=True, foundation_cuda_probe=probe,
                      foundation_python_exe=str(python), foundation_models_root=str(destination/'models'),
                      provision_contract=provision_contract(),dependency_probe=dependency_probe,
                      dependency_versions=[f'torch=={TORCH_VERSION}',f'torchvision=={TORCHVISION_VERSION}',*PACKAGES])
        report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report
    except Exception:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True); parser.add_argument('--registry', required=True)
    parser.add_argument('--continue-after-observed-cuda-failure', action='store_true')
    args = parser.parse_args(argv)
    runtime = pathlib.Path(args.runtime_root).resolve(); registry_path = pathlib.Path(args.registry).resolve()
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    hardware = detect_hardware(); profile = hardware['profile'];use_cuda=bool(hardware.get('cuda_eligible'));desired_device='cuda' if use_cuda else 'cpu'
    destination = runtime / 'foundation_vision'
    reused = _reuse_existing(destination, registry_path, registry, profile, desired_device)
    if reused:
        print(json.dumps(reused, separators=(',', ':'))); return 0
    resumable=sorted((p for p in runtime.glob('.fv-*') if _python(p/'venv').is_file()),key=lambda p:p.stat().st_mtime,reverse=True)
    resumed=bool(args.continue_after_observed_cuda_failure and resumable and use_cuda)
    stage = resumable[0] if resumed else runtime / ('.fv-' + uuid.uuid4().hex[:8])
    stage.mkdir(parents=True,exist_ok=True); env_root = stage / 'venv'; models = stage / 'models'; models.mkdir(exist_ok=True)
    cuda_failure = None
    try:
        if resumed:
            python=_python(env_root);env=os.environ.copy();env['SAM2_BUILD_CUDA']='0'
            probe=cuda_probe(python,False);cuda_failure='PRIOR_REAL_CUDA_TENSOR_PROBE_FAILED_ON_THIS_MACHINE'
        else:
            try:
                if args.continue_after_observed_cuda_failure and use_cuda:
                    raise RuntimeError('PRIOR_REAL_CUDA_TENSOR_PROBE_FAILED_ON_THIS_MACHINE')
                python, env = _install_stack(env_root, use_cuda)
                probe = cuda_probe(python, use_cuda)
            except Exception as exc:
                if not use_cuda: raise
                cuda_failure = str(exc)
                python, env = _install_stack(env_root, False)
                probe = cuda_probe(python, False);desired_device='cpu'
        sam2 = _install_official_sam2(python, env, registry['sam2_source'], stage / 'source',runtime/'.downloads')
        selected = _download_models(python, env, registry, models, profile)
        extension_py = registry_path.parents[1] / 'py'
        probe_env = env.copy(); probe_env['PYTHONPATH'] = str(extension_py)
        code = ('from hexa_v31.vision.foundation.model_registry import resolve_models;import json;'
                'r=resolve_models(%r,%r,%r);assert set(r)=={"florence2","sam2"};'
                'assert all(x["installation_status"]=="INSTALLED" for x in r.values());print(json.dumps(r))') % (
                    str(registry_path), str(models), profile)
        run([python, '-c', code], env=probe_env)
        if not hardware.get('nvidia_present'):classification='CPU_ONLY_NO_NVIDIA'
        elif not hardware.get('cuda_eligible'):classification='CUDA_VRAM_BELOW_FOUNDATION_MINIMUM'
        elif cuda_failure:classification='CUDA_UNSUPPORTED_FOR_FOUNDATION'
        else:classification='CUDA_SUPPORTED_FOR_FOUNDATION'
        report = {'status': 'PASS', 'foundation_profile': profile,
                  'foundation_device': probe['device'], 'foundation_cuda_probe': probe,
                  'foundation_cuda_failure': cuda_failure,
                  'foundation_device_classification': classification,
                  'minimum_foundation_cuda_vram_bytes':MIN_FOUNDATION_CUDA_VRAM_BYTES,
                  'foundation_hardware': hardware,
                  'foundation_python_exe': str(destination / 'venv' / python.relative_to(env_root)),
                  'foundation_models_root': str(destination / 'models'),
                  'foundation_model_registry': str(registry_path), 'foundation_vision_enabled': True,
                  'provision_contract':provision_contract(),
                  'registry_fingerprint': run([python, '-c',
                    ('from hexa_v31.vision.foundation.model_registry import fingerprint;print(fingerprint(%r,%r))' %
                     (str(registry_path), profile))], env=probe_env).splitlines()[-1],
                  'sam2_source': sam2, 'models': [{k: m[k] for k in ('backend','model_id','revision','checkpoint_sha256')} for m in selected],
                  'dependency_versions': [f'torch=={TORCH_VERSION}', f'torchvision=={TORCHVISION_VERSION}', *PACKAGES]}
        (stage / 'provision_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        old = runtime / ('foundation_vision.old-' + uuid.uuid4().hex)
        if destination.exists(): destination.replace(old)
        stage.replace(destination)
        if old.exists(): shutil.rmtree(old, ignore_errors=True)
        print(json.dumps(report, separators=(',', ':'))); return 0
    except Exception:
        (stage/'provision_failure.json').write_text(json.dumps({'status':'FAILED_RETRYABLE','stage':str(stage)},indent=2),encoding='utf-8')
        raise


if __name__ == '__main__':
    raise SystemExit(main())