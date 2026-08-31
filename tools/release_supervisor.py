from __future__ import annotations
import argparse,datetime,hashlib,json,os,pathlib,subprocess,sys,time

ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='31.0.25'
def now():return datetime.datetime.now().astimezone().isoformat(timespec='seconds')
def atomic_json(path,data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');os.replace(tmp,path)
def fingerprint():
    h=hashlib.sha256()
    for base in (ROOT/'extension'/'py'/'hexa_v31',ROOT/'extension'/'resources',ROOT/'extension'/'CSXS'):
        for p in sorted(x for x in base.rglob('*') if x.is_file()):h.update(str(p.relative_to(ROOT)).encode());h.update(p.read_bytes())
    return h.hexdigest()
def alive(pid):
    if not pid:return False
    try:os.kill(int(pid),0);return True
    except OSError:return False
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--voice',required=True);ap.add_argument('--adopt-pid',type=int);a=ap.parse_args()
    release=ROOT/'release';release.mkdir(exist_ok=True);logs=release/'logs';logs.mkdir(exist_ok=True);state_path=release/'release_state.json';lock=release/'release_supervisor.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    except FileExistsError:print('STATUS=BLOCKED_BY_CODE\nFAILED_STAGE=BOOTSTRAP\nFAILURE=release supervisor lock exists\nEXIT_CODE=2');return 2
    state={'overall_status':'RUNNING','version':VERSION,'source_fingerprint':fingerprint(),'package':str(pathlib.Path(a.package).resolve()),'voice':str(pathlib.Path(a.voice).resolve()),'stages':[],'pid':os.getpid()};atomic_json(state_path,state)
    env=os.environ.copy();cfg=pathlib.Path(env.get('LOCALAPPDATA',''))/'HEXA'/'VideoBuilderV31'/'runtime_config.json'
    if cfg.is_file():
        rc=json.loads(cfg.read_text(encoding='utf-8'));roots=[str(ROOT/'extension'/'py')]+list(rc.get('python_import_roots') or []);env['PYTHONPATH']=os.pathsep.join(roots);env['HEXA_FFMPEG']=str(rc.get('ffmpeg_path') or '')
    def stage(name,cmd):
        log=logs/f'{len(state["stages"])+1:02d}_{name.lower()}.log';row={'name':name,'status':'RUNNING','started_at':now(),'command':cmd,'log_path':str(log)};state['stages'].append(row);atomic_json(state_path,state);t=time.time()
        with log.open('w',encoding='utf-8') as f:cp=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,text=True)
        row.update(status='PASS' if cp.returncode==0 else 'FAIL',exit_code=cp.returncode,completed_at=now(),duration_seconds=round(time.time()-t,3));atomic_json(state_path,state)
        if cp.returncode:raise RuntimeError(f'{name} failed; see {log}')
    try:
        if a.adopt_pid and alive(a.adopt_pid):
            while alive(a.adopt_pid):time.sleep(15)
        stage('REAL_CERTIFICATION',[sys.executable,str(ROOT/'tools'/'certify_v11_real_inputs.py'),'--package',a.package,'--voice',a.voice])
        stage('FULL_SUITE',[sys.executable,str(ROOT/'tests'/'run_v31_test_suite.py')])
        stage('REAL_RENDER_BUILD',[sys.executable,'-m','hexa_v31.cli','build','--package',a.package,'--voice',a.voice,'--work-root',str(release/'build')])
        state['overall_status']='READY_TO_INSTALL';state['completed_at']=now();atomic_json(release/'certification_report.json',state);atomic_json(state_path,state);print(f'STATUS=READY_TO_INSTALL\nARTIFACT={release}\nSHA256=PENDING_PACKAGE_STAGE\nREPORT={release / "certification_report.json"}\nEXIT_CODE=0');return 0
    except Exception as e:
        state['overall_status']='BLOCKED_BY_CODE';state['failure']=str(e);state['completed_at']=now();atomic_json(release/'release_failure_report.json',state);atomic_json(state_path,state);failed=next((x for x in reversed(state['stages']) if x['status']=='FAIL'),{'name':'SUPERVISOR','log_path':str(logs)});print(f'STATUS=BLOCKED_BY_CODE\nFAILED_STAGE={failed["name"]}\nFAILURE={e}\nLOG={failed["log_path"]}\nREPORT={release / "release_failure_report.json"}\nEXIT_CODE=1');return 1
    finally:
        try:lock.unlink()
        except OSError:pass
if __name__=='__main__':raise SystemExit(main())
