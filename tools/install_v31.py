from __future__ import annotations
import argparse, datetime, hashlib, importlib, json, os, pathlib, shutil, subprocess, sys, tempfile, time, traceback, wave

ROOT=pathlib.Path(__file__).resolve().parents[1]
EXT_SRC=ROOT/'extension'
# Keep the stable V31 bundle/location so reinstalling does not create migration friction.
VERSION='31.0.25'
BUNDLE='com.hexaterminal.videobuilder.v31_0_1'
INSTALL_LOG_FILE=None

# Windows long-path safety. The original V31.0.1 package could exceed MAX_PATH
# when extracted inside a descriptive parent directory. Always use the extended
# path namespace for package-source file I/O and staging copies on Windows.
def _windows_extended_path_string(s):
    s=str(s)
    if s.startswith('\\\\?\\'):
        return s
    if s.startswith('\\\\'):
        return '\\\\?\\UNC\\'+s[2:]
    return '\\\\?\\'+s

def _win_extended(path):
    s=os.path.abspath(str(path))
    if os.name!='nt':
        return s
    return _windows_extended_path_string(s)

def _file_exists(path):
    return os.path.isfile(_win_extended(path))

def _dir_exists(path):
    return os.path.isdir(_win_extended(path))

def _copytree_long(src,dst):
    return shutil.copytree(_win_extended(src),_win_extended(dst))

def _rmtree_long(path):
    xp=_win_extended(path)
    if os.path.exists(xp):
        shutil.rmtree(xp)

def now(): return datetime.datetime.now().astimezone().isoformat(timespec='seconds')

def _append_install_log(text):
    global INSTALL_LOG_FILE
    if INSTALL_LOG_FILE:
        try:
            pathlib.Path(INSTALL_LOG_FILE).parent.mkdir(parents=True,exist_ok=True)
            with open(INSTALL_LOG_FILE,'a',encoding='utf-8',newline='\n') as f:f.write(str(text).rstrip('\n')+'\n')
        except Exception:pass

def run(cmd, **kw):
    line='[RUN] '+' '.join(str(x) for x in cmd);print(line,flush=True);_append_install_log(line)
    cp=subprocess.run([str(x) for x in cmd],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,**kw)
    if cp.stdout:_append_install_log(cp.stdout)
    return cp

def log(msg):
    line=f'[{now()}] {msg}';print(line,flush=True);_append_install_log(line)

def read_json(p):
    with open(_win_extended(p),'r',encoding='utf-8-sig') as f: return json.load(f)

def write_json(p,d):
    p=pathlib.Path(p); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def _split_pythonpath(raw):
    out=[]
    for x in str(raw or '').split(os.pathsep):
        x=x.strip().strip('"')
        if not x: continue
        try:p=str(pathlib.Path(x).expanduser().resolve())
        except Exception:p=x
        if p not in out: out.append(p)
    return out

def _existing_unique_paths(paths):
    out=[]
    for x in paths:
        if not x: continue
        try:
            p=pathlib.Path(x).expanduser().resolve()
            if not p.exists(): continue
            k=os.path.normcase(str(p))
        except Exception:
            continue
        if not any(os.path.normcase(y)==k for y in out): out.append(str(p))
    return out

def discover_legacy_site_packages(localapp):
    """Find reusable package roots without trusting the legacy venv launcher itself.

    A Windows virtual environment can lose pyvenv.cfg while its Lib/site-packages
    remains perfectly usable from a compatible base interpreter. V31.0.1 treats
    the launcher and the package cache as two separate authorities: the bootstrap
    must execute successfully, while package roots are admitted only after a real
    import probe under the selected interpreter.
    """
    hexa=pathlib.Path(localapp)/'HEXA'
    roots=[]
    for name in ('VideoBuilderV31','VideoBuilderV27','VideoBuilderV26','VideoBuilderV25','VideoBuilderV24','VideoBuilderV23','VideoBuilderV20','VideoBuilderV17','VideoBuilderV16','VideoBuilderV12','VideoBuilderV8','VideoBuilderV3'):
        base=hexa/name
        candidates=[
            base/'runtime'/'.venv'/'Lib'/'site-packages',
            base/'runtime'/'.venv'/'lib'/'site-packages',
            base/'runtime'/'Lib'/'site-packages',
            base/'runtime'/'lib'/'site-packages',
            base/'vendor',
            base/'vendor_overlay',
        ]
        roots.extend(candidates)
    return _existing_unique_paths(roots)

def ensure_pip(py):
    c=run([py,'-m','pip','--version'],timeout=60)
    if c.returncode==0:return
    log('PIP BOOTSTRAP: pip unavailable on selected Python; attempting ensurepip --upgrade')
    c=run([py,'-m','ensurepip','--upgrade'],timeout=300)
    if c.returncode!=0:
        raise RuntimeError('Selected Python is executable but pip/ensurepip are unavailable; cannot repair missing V31 dependencies.\n'+c.stdout[-4000:])

def _pythonpath_value(engine_py, roots):
    vals=[]
    if engine_py: vals.append(str(pathlib.Path(engine_py).resolve()))
    vals += _existing_unique_paths(roots)
    return os.pathsep.join(vals)

def _module_probe(py, roots, module, engine_py=None, timeout=90):
    # Probe with the exact frozen import roots that the CEP launcher will use.
    # This prevents a false PASS when a dependency is visible only through the
    # installer's inherited PYTHONPATH and then disappears during engine launch.
    env=os.environ.copy(); env['PYTHONPATH']=_pythonpath_value(engine_py,roots)
    capability={
        'numpy':'assert hasattr(m,"array") and hasattr(m,"ndarray")',
        'PIL':'from PIL import Image; assert hasattr(Image,"open")',
        'cv2':'assert hasattr(m,"imread") and hasattr(m,"VideoCapture")',
        'faster_whisper':'from faster_whisper import WhisperModel; assert WhisperModel is not None',
        'arabic_reshaper':'assert hasattr(m,"reshape")',
        'bidi':'from bidi.algorithm import get_display; assert callable(get_display)',
    }.get(module,'assert m is not None')
    code=(
        'import importlib; '
        f'm=importlib.import_module({module!r}); '
        +capability+'; '
        +'print("VERSION="+str(getattr(m,"__version__","OK"))); '
        +'print("ORIGIN="+str(getattr(m,"__file__","") or "")); '
        +'print("CAPABILITY=PASS")'
    )
    c=run([py,'-c',code],env=env,timeout=timeout)
    desc=c.stdout.strip()
    return c.returncode==0,desc

def import_probe(py, vendor, module, extra_roots=None):
    roots=[vendor]+list(extra_roots or [])
    return _module_probe(py,roots,module)

def pip_target(py,vendor,spec):
    vendor.mkdir(parents=True,exist_ok=True)
    ensure_pip(py)
    c=run([py,'-m','pip','install','--disable-pip-version-check','--no-input','--upgrade','--target',str(vendor),spec],timeout=1800)
    if c.returncode!=0: raise RuntimeError(f'pip install failed for {spec}:\n{c.stdout[-5000:]}')

def discover_media_tool_candidates(localapp, tool):
    exe=(tool+'.exe') if os.name=='nt' else tool
    out=[];seen=set()
    def add(x):
        if not x:return
        try:p=pathlib.Path(x).resolve()
        except Exception:return
        if not p.is_file():return
        k=os.path.normcase(str(p))
        if k in seen:return
        seen.add(k);out.append(p)
    add(shutil.which(exe)); add(shutil.which(tool))
    root=localapp/'HEXA'
    if root.exists():
        for pat in (f'VideoBuilderV*/**/{tool}.exe',f'VideoBuilderV*/**/{tool}'):
            try:
                for p in root.glob(pat):add(p)
            except Exception:pass
    return out


def discover_ffmpeg(localapp):
    c=discover_media_tool_candidates(localapp,'ffmpeg')
    return c[0] if c else None


def discover_ffprobe(localapp, ffmpeg_path=None):
    candidates=[]
    if ffmpeg_path:
        candidates.append(pathlib.Path(ffmpeg_path).with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe'))
    candidates += discover_media_tool_candidates(localapp,'ffprobe')
    seen=set()
    for p in candidates:
        try:q=pathlib.Path(p).resolve()
        except Exception:continue
        k=os.path.normcase(str(q))
        if k in seen:continue
        seen.add(k)
        if q.is_file():return q
    return None

def discover_whisper_models(localapp, home):
    roots=[
        localapp/'HEXA'/'VideoBuilderV8',localapp/'HEXA'/'VideoBuilderV12',localapp/'HEXA'/'VideoBuilderV16',localapp/'HEXA'/'VideoBuilderV17',localapp/'HEXA'/'VideoBuilderV20',localapp/'HEXA'/'VideoBuilderV23',localapp/'HEXA'/'VideoBuilderV24',localapp/'HEXA'/'VideoBuilderV25',localapp/'HEXA'/'VideoBuilderV26',localapp/'HEXA'/'VideoBuilderV27',localapp/'HEXA'/'VideoBuilderV31',
        home/'.cache'/'huggingface'/'hub', home/'.cache'/'whisper'
    ]
    found=[]; seen=set()
    for root in roots:
        if not root.exists(): continue
        try:
            for p in root.rglob('model.bin'):
                if p.stat().st_size<5_000_000: continue
                d=p.parent.resolve()
                # CTranslate2 faster-whisper directories contain model.bin and config.json.
                if (d/'config.json').is_file() and str(d) not in seen:
                    found.append(d);seen.add(str(d))
        except Exception: pass
    return found

def download_whisper_model(py,vendor,model_dir,extra_roots=None,install_target=None):
    ok,_=import_probe(py,vendor,'huggingface_hub',extra_roots)
    if not ok:pip_target(py,install_target or vendor,'huggingface-hub>=0.24,<1')
    env=os.environ.copy();env['PYTHONPATH']=_pythonpath_value(None,[vendor]+list(extra_roots or []))
    code=("from huggingface_hub import snapshot_download; "
          f"p=snapshot_download('Systran/faster-whisper-small',local_dir=r'''{str(model_dir)}''',local_dir_use_symlinks=False);print(p)")
    c=run([py,'-c',code],env=env,timeout=7200)
    if c.returncode!=0: raise RuntimeError('Whisper model download failed:\n'+c.stdout[-5000:])

def make_silence_wav(path):
    with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*8000)

def whisper_probe(py,vendor,model_path,device,compute,extra_roots=None):
    env=os.environ.copy();env['PYTHONPATH']=_pythonpath_value(None,[vendor]+list(extra_roots or []))
    with tempfile.TemporaryDirectory() as td:
        wav=pathlib.Path(td)/'silence.wav';make_silence_wav(wav)
        code=f'''from faster_whisper import WhisperModel\ntry:\n m=WhisperModel(r"""{model_path}""",device="{device}",compute_type="{compute}",local_files_only=True,cpu_threads=2)\nexcept TypeError:\n m=WhisperModel(r"""{model_path}""",device="{device}",compute_type="{compute}",cpu_threads=2)\nlist(m.transcribe(r"""{wav}""",language="ar",beam_size=1,vad_filter=False)[0]);print("INFERENCE_PASS")\n'''
        c=run([py,'-c',code],env=env,timeout=300)
        return c.returncode==0 and 'INFERENCE_PASS' in c.stdout,c.stdout[-3000:]

def discover_premiere_mp4_preset(home:pathlib.Path):
    """Reuse an installed Premiere/AME .epr preset; never download export presets during BUILD.

    Premiere Pro 2022 validates the selected candidate again with
    Sequence.getExportFileExtension() before export. System preset filenames can be
    opaque, so the scanner scores both path/name and a bounded text sample.
    """
    roots=[]
    pf=os.environ.get('PROGRAMFILES'); pf86=os.environ.get('PROGRAMFILES(X86)')
    for base in [pf,pf86]:
        if not base: continue
        ad=pathlib.Path(base)/'Adobe'
        roots += [
            ad/'Adobe Premiere Pro 2022'/'MediaIO'/'systempresets',
            ad/'Adobe Media Encoder 2022'/'MediaIO'/'systempresets',
        ]
    roots += [
        home/'Documents'/'Adobe'/'Adobe Media Encoder'/'22.0'/'Presets',
        home/'Documents'/'Adobe'/'Adobe Premiere Pro'/'22.0'/'Profile-CreativeCloud-'/'Presets',
        home/'AppData'/'Roaming'/'Adobe'/'Common'/'AME'/'22.0'/'Presets',
    ]
    # Last-resort user preset roots across adjacent installed versions. These are small.
    roots += [home/'Documents'/'Adobe'/'Adobe Media Encoder',home/'AppData'/'Roaming'/'Adobe'/'Common'/'AME']
    seen=set(); scored=[]
    for root in roots:
        try:
            if not root.exists(): continue
            for ep in root.rglob('*.epr'):
                try:
                    rp=ep.resolve(); key=str(rp).lower()
                    if key in seen: continue
                    seen.add(key)
                    txt=(ep.name+' '+str(ep.parent)).lower()
                    try:
                        raw=ep.read_bytes()[:400_000]
                        sample=raw.decode('utf-8','ignore').lower()
                        if len(sample)<64: sample=raw.decode('utf-16','ignore').lower()
                        txt+=' '+sample
                    except Exception: pass
                    score=0
                    if 'h.264' in txt or 'h264' in txt or 'avc' in txt: score+=500
                    if 'match source' in txt: score+=130
                    if 'high bitrate' in txt or 'highbitrate' in txt: score+=100
                    if 'high quality' in txt and '1080' in txt: score+=90
                    if '1080' in txt: score+=35
                    if 'youtube' in txt and '1080' in txt: score+=25
                    if 'hevc' in txt or 'h.265' in txt or 'h265' in txt: score-=400
                    if score>0: scored.append((score,rp))
                except Exception: pass
        except Exception: pass
    scored.sort(key=lambda x:(-x[0],str(x[1]).lower()))
    return scored[0][1] if scored else None

def clean_extensions(cep_root):
    removed=[]
    if not cep_root.exists(): return removed
    for d in list(cep_root.iterdir()):
        if not d.is_dir():continue
        manifest=d/'CSXS'/'manifest.xml'; owned=d.name.lower().startswith('com.hexaterminal.videobuilder')
        if manifest.is_file():
            try:owned=owned or 'com.hexaterminal.videobuilder' in manifest.read_text(encoding='utf-8-sig',errors='ignore').lower()
            except Exception:pass
        if owned:
            shutil.rmtree(d);removed.append(str(d))
    return removed


def hardware_probe(runtime_root):
    info={'cpu_count':os.cpu_count() or 1}
    try:
        if os.name=='nt':
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('sullAvailExtendedVirtual',ctypes.c_ulonglong)]
            st=MEMORYSTATUSEX();st.dwLength=ctypes.sizeof(MEMORYSTATUSEX);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            info.update({'ram_total_gb':round(st.ullTotalPhys/1024**3,2),'ram_available_gb':round(st.ullAvailPhys/1024**3,2),'memory_load_percent':int(st.dwMemoryLoad),'pagefile_available_gb':round(st.ullAvailPageFile/1024**3,2)})
        else:
            pages=os.sysconf('SC_PHYS_PAGES');ps=os.sysconf('SC_PAGE_SIZE');av=os.sysconf('SC_AVPHYS_PAGES')
            info.update({'ram_total_gb':round(pages*ps/1024**3,2),'ram_available_gb':round(av*ps/1024**3,2)})
    except Exception as e: info['memory_probe_error']=str(e)
    try:
        du=shutil.disk_usage(runtime_root);info['disk_free_gb']=round(du.free/1024**3,2);info['disk_total_gb']=round(du.total/1024**3,2)
    except Exception as e:info['disk_probe_error']=str(e)
    ns=shutil.which('nvidia-smi')
    if ns:
        try:
            cp=run([ns,'--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'],timeout=30)
            info['nvidia_smi']=cp.stdout.strip().splitlines() if cp.returncode==0 else []
        except Exception as e: info['gpu_probe_error']=str(e)
    info['low_memory_mode']=bool(info.get('ram_total_gb',99)<12 or info.get('ram_available_gb',99)<3)
    info['heavy_worker_parallelism']=1
    return info

def main():
    if os.name!='nt':
        log('WARNING: installer is designed for Windows/Premiere 2022. Running portability checks only in this environment.')
    localapp=pathlib.Path(os.environ.get('LOCALAPPDATA',pathlib.Path.home()/'.local/share'))
    appdata=pathlib.Path(os.environ.get('APPDATA',pathlib.Path.home()/'.config'))
    home=pathlib.Path.home()
    runtime=localapp/'HEXA'/'VideoBuilderV31'
    prior_v20=localapp/'HEXA'/'VideoBuilderV20'
    prior_v23=localapp/'HEXA'/'VideoBuilderV23'
    prior_v24=localapp/'HEXA'/'VideoBuilderV24'
    prior_v25=localapp/'HEXA'/'VideoBuilderV25'
    prior_v26=localapp/'HEXA'/'VideoBuilderV26'
    prior_v27=localapp/'HEXA'/'VideoBuilderV27'
    # Reuse already-proven heavy Python/model/build caches from V20 instead of
    # downloading or recomputing them. V31 owns its registry/logs/extension plus a
    # small vendor overlay used only when an exact-runtime dependency is genuinely missing.
    vendor=(prior_v20/'vendor') if (prior_v20/'vendor').is_dir() else runtime/'vendor'
    vendor_overlay=runtime/'vendor_overlay'
    inherited_pythonpath_roots=_existing_unique_paths(_split_pythonpath(os.environ.get('PYTHONPATH','')))
    legacy_site_package_candidates=discover_legacy_site_packages(localapp)
    selected_legacy_dependency_roots=[]
    # Valid prior models are discovered by physical model.bin+config.json probes.
    # New downloads always belong to V31 so an empty legacy models directory can never hijack setup.
    models=runtime/'models'
    build_cache_root=(prior_v20/'builds') if (prior_v20/'builds').is_dir() else runtime/'builds'
    logs=runtime/'install_logs'; logs.mkdir(parents=True,exist_ok=True)
    global INSTALL_LOG_FILE
    INSTALL_LOG_FILE=logs/('INSTALL_V31_'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    marker=os.environ.get('HEXA_V31_INSTALL_LOG_MARKER')
    if marker:
        try:pathlib.Path(marker).write_text(str(INSTALL_LOG_FILE),encoding='utf-8')
        except Exception:pass
    log('INSTALL LOG: '+str(INSTALL_LOG_FILE))
    transcript=[]
    py=pathlib.Path(sys.executable).resolve(); log(f'Python base runtime: {py}')
    log('PYTHON EXECUTION PROBE: PASS (bootstrap selected an interpreter that actually executed)')
    log('LEGACY PACKAGE ROOT CANDIDATES: '+json.dumps(legacy_site_package_candidates,ensure_ascii=False))
    # Package preflight MUST complete before any installed extension is removed.
    # This specifically prevents the V31.0.1 MAX_PATH failure from deleting V28 first.
    critical_relpaths=[
        pathlib.Path('CSXS')/'manifest.xml',
        pathlib.Path('index.html'),
        pathlib.Path('js')/'main.js',
        pathlib.Path('jsx')/'host.jsx',
        pathlib.Path('resources')/'DEPENDENCY_MANIFEST_V20.json',
        pathlib.Path('resources')/'HEXA_LEGACY_REGRESSION_MATRIX_V20.json',
        pathlib.Path('resources')/'HEXA_REFERENCE_QA_PROFILE_V20.json',
        pathlib.Path('resources')/'HEXA_EDITING_RULES_V20.json',
        pathlib.Path('resources')/'HEXA_MOTION_VOCABULARY_V31.json',
        pathlib.Path('resources')/'HEXA_USER_PRESET_AUTHORITY_V31.json',
        pathlib.Path('resources')/'HEXA_USER_MOTION_RULES_AUTHORITY.pdf',
        pathlib.Path('resources')/'presets.prfpset',
        pathlib.Path('resources')/'presets_source.rar',
        pathlib.Path('py')/'hexa_v31'/'preset_authority.py',
        pathlib.Path('py')/'hexa_v31'/'preset_story_planner.py',
        pathlib.Path('py')/'hexa_v31'/'scene_grammar.py',
        pathlib.Path('py')/'hexa_v31'/'composition_solver.py',
        pathlib.Path('py')/'hexa_v31'/'composition_qa.py',
        pathlib.Path('py')/'hexa_v31'/'design_director.py',
        pathlib.Path('py')/'hexa_v31'/'matting.py',
        pathlib.Path('py')/'hexa_v31'/'premiere.py',
        pathlib.Path('py')/'hexa_v31'/'scene_media.py',
        pathlib.Path('py')/'hexa_v31'/'visual_cards.py',
        pathlib.Path('py')/'hexa_v31'/'visual_density.py',
        pathlib.Path('py')/'hexa_v31'/'preset_qa.py',
        pathlib.Path('py')/'hexa_v31'/'__init__.py',
        pathlib.Path('py')/'hexa_v31'/'pipeline.py',
    ]
    missing=[str(rel) for rel in critical_relpaths if not _file_exists(EXT_SRC/rel)]
    if missing:
        raise RuntimeError('V31 package preflight failed before destructive install. Missing/unreadable source files: '+json.dumps(missing))
    frontend_relpaths=(pathlib.Path('index.html'),pathlib.Path('js')/'main.js',pathlib.Path('jsx')/'host.jsx')
    frontend_text='\n'.join((EXT_SRC/rel).read_text(encoding='utf-8') for rel in frontend_relpaths)
    if '31.0.9' in frontend_text:
        raise RuntimeError('Stale V31.0.9 release authority remains in the shipping CEP frontend/host payload.')
    if any(VERSION not in (EXT_SRC/rel).read_text(encoding='utf-8') for rel in frontend_relpaths):
        raise RuntimeError('V31 CEP frontend/host identity does not match installer VERSION='+VERSION)
    # Latest user-supplied rules/presets are a hard binary authority. Refuse installation
    # if the packaged bytes differ from the authority registry used to compile V31 motion.
    auth=read_json(EXT_SRC/'resources'/'HEXA_USER_PRESET_AUTHORITY_V31.json')
    expected=auth.get('source_files') or {}
    authority_files={
        'rules_pdf_sha256':EXT_SRC/'resources'/'HEXA_USER_MOTION_RULES_AUTHORITY.pdf',
        'prfpset_sha256':EXT_SRC/'resources'/'presets.prfpset',
        'samples_rar_sha256':EXT_SRC/'resources'/'presets_source.rar',
    }
    bad=[]
    for key,path in authority_files.items():
        h=hashlib.sha256()
        with open(_win_extended(path),'rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        actual=h.hexdigest();want=str(expected.get(key) or '')
        if actual.lower()!=want.lower():bad.append({'file':str(path),'actual':actual,'expected':want})
    if bad:raise RuntimeError('V31.0.25 user motion authority hash mismatch: '+json.dumps(bad))
    log('USER PRESET/RULE AUTHORITY HASHES: PASS')

    log('PHASE 0/8 - Package preflight + Windows long-path-safe staging')
    stage_root=runtime/'install_stage'
    stage=stage_root/BUNDLE
    _rmtree_long(stage_root)
    stage_root.mkdir(parents=True,exist_ok=True)
    _copytree_long(EXT_SRC,stage)
    stage_missing=[str(rel) for rel in critical_relpaths if not (stage/rel).is_file()]
    if stage_missing:
        raise RuntimeError('V31 staged extension verification failed before destructive install: '+json.dumps(stage_missing))
    source_max=max(len(os.path.abspath(str(EXT_SRC/rel))) for rel in critical_relpaths)
    log(f'PACKAGE PREFLIGHT: PASS | critical_files={len(critical_relpaths)} source_max_path_chars={source_max}')
    log('SHORT-PATH STAGE: PASS -> '+str(stage))

    dep=read_json(stage/'resources'/'DEPENDENCY_MANIFEST_V20.json')
    cep=appdata/'Adobe'/'CEP'/'extensions';cep.mkdir(parents=True,exist_ok=True)
    log('PHASE 1/8 - Clean previous HEXA Video Builder CEP extensions')
    removed=clean_extensions(cep)
    for r in removed:log('REMOVED EXTENSION: '+r)
    log(f'Old HEXA extension count removed: {len(removed)}')
    log('PHASE 2/8 - Install V31 extension from verified short-path stage')
    target=cep/BUNDLE
    if target.exists():shutil.rmtree(target)
    shutil.copytree(stage,target)
    deployed_missing=[str(rel) for rel in critical_relpaths if not (target/rel).is_file()]
    if deployed_missing:
        raise RuntimeError('V31 deployed extension verification failed: '+json.dumps(deployed_missing))
    log('EXTENSION DEPLOY READBACK: PASS')
    if os.name=='nt':
        for csxs in ('CSXS.9','CSXS.10','CSXS.11','CSXS.12'):
            c=run(['reg','add',fr'HKCU\Software\Adobe\{csxs}','/v','PlayerDebugMode','/t','REG_SZ','/d','1','/f'],timeout=20)
            if c.returncode!=0:log(f'WARNING registry PlayerDebugMode {csxs}: {c.stdout.strip()}')
    log('PHASE 3/8 - Hardware preflight + dependency inventory / reuse-first resolution')
    hardware=hardware_probe(runtime)
    log('HARDWARE: '+json.dumps(hardware,ensure_ascii=False))
    if hardware.get('disk_free_gb',99)<4.0:raise RuntimeError('Insufficient free disk space for V31 runtime/build cache (<4 GB).')
    package_status={}
    for item in dep['python_packages']:
        mod=item['import']
        active_extra=[vendor_overlay]+selected_legacy_dependency_roots+inherited_pythonpath_roots
        ok,desc=import_probe(str(py),vendor,mod,active_extra)
        reuse_root=None
        if not ok:
            # Do not execute a broken legacy venv. Reuse its package cache only when
            # this exact selected interpreter can physically import the module from it.
            for candidate in legacy_site_package_candidates:
                if any(os.path.normcase(candidate)==os.path.normcase(x) for x in selected_legacy_dependency_roots):
                    continue
                trial_extra=[vendor_overlay]+selected_legacy_dependency_roots+[candidate]+inherited_pythonpath_roots
                ok2,desc2=import_probe(str(py),vendor,mod,trial_extra)
                if ok2:
                    selected_legacy_dependency_roots.append(candidate)
                    reuse_root=candidate;ok=True;desc=desc2
                    log(f'LEGACY DEPENDENCY ROOT ADMITTED: {candidate} via module {mod}')
                    break
        package_status[mod]={'found':ok,'probe':desc,'reuse_root':reuse_root}
        if ok:
            log(f'DEPENDENCY REUSE: {mod} -> {desc.replace(chr(10)," | ")}')
        elif item.get('required') or item.get('strongly_recommended'):
            log(f'DEPENDENCY MISSING: {mod}; installing only this missing component into the V31 vendor overlay')
            try:pip_target(str(py),vendor_overlay,item['pip'])
            except Exception as e:
                if item.get('required'):raise
                log(f'WARNING optional dependency {mod} could not be installed: {e}')
            active_extra=[vendor_overlay]+selected_legacy_dependency_roots+inherited_pythonpath_roots
            ok2,desc2=import_probe(str(py),vendor,mod,active_extra)
            package_status[mod]={'found':ok2,'probe':desc2,'reuse_root':None,'installed_to_overlay':True}
            if item.get('required') and not ok2:
                raise RuntimeError(f'Required dependency still unavailable after install: {mod}\n{desc2}')
    log('SELECTED LEGACY DEPENDENCY ROOTS: '+json.dumps(selected_legacy_dependency_roots,ensure_ascii=False))
    log('PHASE 4/8 - FFmpeg media runtime physical probe')
    ff=None
    for cand in discover_media_tool_candidates(localapp,'ffmpeg'):
        c=run([str(cand),'-version'],timeout=20)
        if c.returncode==0:
            ff=cand;break
        log(f'WARNING: skipping non-executable FFmpeg candidate: {cand}')
    if not ff:raise RuntimeError('No executable ffmpeg found in PATH or prior HEXA runtimes. Install/restore FFmpeg then rerun Setup.')
    fp=None
    ffprobe_candidates=[]
    companion=ff.with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')
    if companion.is_file():ffprobe_candidates.append(companion)
    ffprobe_candidates += discover_media_tool_candidates(localapp,'ffprobe')
    seen_fp=set()
    for cand in ffprobe_candidates:
        k=os.path.normcase(str(cand))
        if k in seen_fp:continue
        seen_fp.add(k)
        cfp=run([str(cand),'-version'],timeout=20)
        if cfp.returncode==0:
            fp=cand;break
        log(f'WARNING: skipping non-executable ffprobe candidate: {cand}')
    media_probe_backend='FFPROBE_JSON' if fp else 'FFMPEG_STDERR_FALLBACK'
    if fp:log(f'FFPROBE READY: {fp}')
    else:log('FFPROBE OPTIONAL: not available. Supported FFmpeg stderr media-probe fallback is enabled; installation continues.')
    log(f'FFMPEG READY: {ff}')
    log(f'MEDIA PROBE BACKEND: {media_probe_backend}')
    log('PHASE 5/8 - Word-alignment model inventory')
    model_candidates=discover_whisper_models(localapp,home)
    fw_ok=package_status.get('faster_whisper',{}).get('found',False)
    model_path=model_candidates[0] if model_candidates else None
    if fw_ok and not model_path:
        log('No reusable faster-whisper CTranslate2 model found; downloading the missing model once during Setup.')
        model_path=models/'faster-whisper-small';model_path.mkdir(parents=True,exist_ok=True)
        try:download_whisper_model(str(py),vendor,model_path,[vendor_overlay]+selected_legacy_dependency_roots+inherited_pythonpath_roots,install_target=vendor_overlay)
        except Exception as e:
            log('WARNING: word-level model preparation failed; V31 can use the strict scene-boundary acoustic fallback only for compatible packages. '+str(e))
            model_path=None
    elif model_path:log('MODEL REUSE: '+str(model_path))
    log('PHASE 6/8 - Real inference backend probe')
    whisper_device='cpu';whisper_compute='int8';whisper_ready=False
    if fw_ok and model_path:
        # GPU is READY only after actual model inference. File/device presence is not enough.
        gpu_ok,gpu_log=whisper_probe(str(py),vendor,str(model_path),'cuda','float16',[vendor_overlay]+selected_legacy_dependency_roots+inherited_pythonpath_roots)
        if gpu_ok:
            whisper_device='cuda';whisper_compute='float16';whisper_ready=True;log('WHISPER CUDA REAL INFERENCE: PASS')
        else:
            log('WHISPER CUDA REAL INFERENCE: FAIL -> CPU fallback (expected on systems missing CUDA runtime DLLs)')
            cpu_ok,cpu_log=whisper_probe(str(py),vendor,str(model_path),'cpu','int8',[vendor_overlay]+selected_legacy_dependency_roots+inherited_pythonpath_roots)
            if cpu_ok:whisper_ready=True;log('WHISPER CPU INT8 REAL INFERENCE: PASS')
            else:log('WARNING: Whisper real inference failed. '+cpu_log[-1000:])
    log('PHASE 7/8 - Write central V31 runtime registry')
    log('PREMIERE EXPORT POLICY: DISABLED. V31 engine assembles and certifies MP4 before Premiere project assembly.')
    python_import_roots=_existing_unique_paths([vendor_overlay,vendor]+selected_legacy_dependency_roots+inherited_pythonpath_roots)
    import_contract_payload={'python_exe':str(py),'roots':python_import_roots}
    import_contract_sha=hashlib.sha256(json.dumps(import_contract_payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    log('PYTHON IMPORT CONTRACT ROOTS: '+json.dumps(python_import_roots,ensure_ascii=False))
    log('PYTHON IMPORT CONTRACT SHA256: '+import_contract_sha)
    cfg={
      'schema':'HEXA_V31_RUNTIME_CONFIG','version':'1.2','created_at':now(),'python_exe':str(py),'vendor_dir':str(vendor),'vendor_overlay_dir':str(vendor_overlay),'python_import_roots':python_import_roots,'python_import_contract_sha256':import_contract_sha,'installer_inherited_pythonpath_roots':inherited_pythonpath_roots,'legacy_site_package_candidates':legacy_site_package_candidates,'selected_legacy_dependency_roots':selected_legacy_dependency_roots,
      'ffmpeg_path':str(ff),'ffprobe_path':str(fp) if fp else None,'media_probe_backend':media_probe_backend,'allow_whisper':bool(whisper_ready),'whisper_model_path':str(model_path) if model_path else None,
      'whisper_model_candidates':[str(x) for x in model_candidates]+([str(model_path)] if model_path else []),'whisper_device':whisper_device,'whisper_compute_type':whisper_compute,
      'cpu_threads':max(1,min(4,os.cpu_count() or 2)),'downloads_during_build':False,'old_extensions_removed':removed,'dependency_status':package_status,'hardware':hardware,'heavy_worker_parallelism':1,
      'premiere_export_preset_path':None,
      'build_cache_root':str(build_cache_root),'shared_vendor_reused_from_v20':bool((prior_v20/'vendor').is_dir()),'shared_models_reused_from_v20':bool((prior_v20/'models').is_dir()),'shared_models_reused_from_v23':bool((prior_v23/'models').is_dir()),'shared_models_reused_from_v24':bool((prior_v24/'models').is_dir()),'shared_models_reused_from_v25':bool((prior_v25/'models').is_dir()),'shared_models_reused_from_v26':bool((prior_v26/'models').is_dir()),
      'runtime_policy':'EXECUTABLE_BOOTSTRAP_REQUIRED; REUSE_ONLY_EXACTLY_PROBED_PACKAGE_ROOTS; INSTALL_ONLY_MISSING; NEVER_DOWNLOAD_DURING_BUILD'
    }
    write_json(runtime/'runtime_config.json',cfg)
    runtime_lock={
      'schema':'HEXA_V31_RUNTIME_LOCK','version':VERSION,'created_at':now(),'bundle_id':BUNDLE,
      'python_exe':str(py),'extension_root':str(target),'runtime_config':str(runtime/'runtime_config.json'),'python_import_contract_sha256':import_contract_sha,
      'policy':'PANEL_MUST_MATCH_INSTALLER_CERTIFIED_RUNTIME_AND_EXTENSION'
    }
    write_json(runtime/'runtime_lock.json',runtime_lock)
    log('RUNTIME LOCK: '+str(runtime/'runtime_lock.json'))
    log('PHASE 8/8 - Cold readback + engine import + runtime self-test')
    reread=read_json(runtime/'runtime_config.json')
    if reread.get('python_exe')!=str(py):raise RuntimeError('runtime_config cold readback mismatch')
    # Validate every required dependency under the exact environment used by the CEP launcher.
    # If a required module was only accidentally visible during inventory, repair into a V31 overlay.
    exact_fail=[]
    for item in dep['python_packages']:
        ok,desc=_module_probe(str(py),python_import_roots,item['import'],target/'py')
        package_status.setdefault(item['import'],{})['exact_runtime_probe']=desc
        if ok:
            log(f'EXACT RUNTIME IMPORT PASS: {item["import"]} -> {desc.replace(chr(10)," | ")}')
        elif item.get('required'):
            exact_fail.append(item)
        else:
            log(f'WARNING EXACT RUNTIME IMPORT DEGRADED: {item["import"]} -> {desc[-1000:]}')
    if exact_fail:
        log('EXACT RUNTIME IMPORT REPAIR: installing only missing required modules into V31 vendor overlay')
        for item in exact_fail:
            pip_target(str(py),vendor_overlay,item['pip'])
        python_import_roots=_existing_unique_paths([vendor_overlay,vendor]+selected_legacy_dependency_roots+inherited_pythonpath_roots)
        import_contract_payload={'python_exe':str(py),'roots':python_import_roots}
        import_contract_sha=hashlib.sha256(json.dumps(import_contract_payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
        cfg['python_import_roots']=python_import_roots;cfg['python_import_contract_sha256']=import_contract_sha
        runtime_lock['python_import_contract_sha256']=import_contract_sha
        write_json(runtime/'runtime_config.json',cfg);write_json(runtime/'runtime_lock.json',runtime_lock)
        for item in exact_fail:
            ok,desc=_module_probe(str(py),python_import_roots,item['import'],target/'py')
            package_status.setdefault(item['import'],{})['exact_runtime_repair_probe']=desc
            if not ok:raise RuntimeError(f'Required dependency unavailable in exact V31 runtime after overlay repair: {item["import"]}\n{desc}')
            log(f'EXACT RUNTIME IMPORT REPAIR PASS: {item["import"]} -> {desc.replace(chr(10)," | ")}')
    cfg['dependency_status']=package_status
    write_json(runtime/'runtime_config.json',cfg)
    env=os.environ.copy();env['PYTHONPATH']=_pythonpath_value(target/'py',python_import_roots);env['PATH']=str(ff.parent)+os.pathsep+env.get('PATH','');env['HEXA_V31_RUNTIME_CONFIG']=str(runtime/'runtime_config.json')
    c=run([str(py),'-c','from hexa_v31 import VERSION; from hexa_v31.pipeline import build; print(VERSION)'],env=env,timeout=90)
    if c.returncode!=0 or VERSION not in c.stdout:raise RuntimeError('V31 engine import smoke test failed under exact frozen runtime import contract:\n'+c.stdout)
    selftest=runtime/'RUNTIME_SELFTEST_V31.json'
    c=run([str(py),str(ROOT/'tools'/'selftest_v31.py'),'--extension-root',str(target),'--out',str(selftest)],env=env,timeout=180)
    if c.returncode!=0 or 'HEXA_V31_RUNTIME_SELFTEST_PASS' not in c.stdout:raise RuntimeError('V31 runtime self-test failed:\n'+c.stdout[-5000:])
    report={'status':'PASS','version':VERSION,'timestamp':now(),'target_extension':str(target),'runtime_config':str(runtime/'runtime_config.json'),'runtime_lock':str(runtime/'runtime_lock.json'),'python_exe':str(py),'runtime_selftest':str(selftest),'install_log':str(INSTALL_LOG_FILE),'hardware':hardware,'removed_old_extensions':removed,'whisper_word_alignment_ready':whisper_ready,'whisper_backend':{'device':whisper_device,'compute_type':whisper_compute,'model_path':str(model_path) if model_path else None},'ffmpeg':str(ff),'ffprobe':str(fp) if fp else None,'media_probe_backend':media_probe_backend,'premiere_export_policy':'ENGINE_FINAL_MP4_PREBUILT__PREMIERE_PROJECT_ONLY','dependencies':package_status,'python_import_roots':python_import_roots,'python_import_contract_sha256':import_contract_sha,'selected_legacy_dependency_roots':selected_legacy_dependency_roots,'bootstrap_python_execution_probe':'PASS'}
    write_json(runtime/'INSTALL_REPORT_V31.json',report)
    log('HEXA V31 INSTALLATION PASS')
    if not whisper_ready:log('NOTICE: word-level Whisper backend DEGRADED. Current scene-start-only contracts can still use acoustic fallback; internal-trigger packages will require Setup/Repair.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except SystemExit:raise
    except Exception as e:
        tb=traceback.format_exc()
        msg='HEXA V31 INSTALLATION FAIL: '+str(e)
        print('\n'+msg,file=sys.stderr)
        print(tb,file=sys.stderr)
        _append_install_log(msg)
        _append_install_log(tb)
        raise SystemExit(2)

