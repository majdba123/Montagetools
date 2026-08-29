from __future__ import annotations
import json, os, pathlib, sys, time, traceback, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from .util import ensure_dir, write_json, write_text


@dataclass
class BuildPaths:
    root: pathlib.Path
    logs: pathlib.Path
    scenes: pathlib.Path
    cache: pathlib.Path
    outputs: pathlib.Path
    checkpoints: pathlib.Path


class BuildLogger:
    def __init__(self, root: str | os.PathLike, build_id: str | None = None, echo: bool = True):
        self.root = ensure_dir(root)
        self.build_id = build_id or datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        self.echo = echo
        self.master = self.root / 'master.log'
        self.events = self.root / 'events.jsonl'
        self.summary = self.root / 'build_summary.json'
        self.current = {'phase': 'INIT', 'scene_id': None, 'unit_id': None}
        self._counts = {'DEBUG':0,'INFO':0,'PASS':0,'WARNING':0,'ERROR':0}
        self.log('INFO','BUILD_LOG_OPEN', build_id=self.build_id)

    def _ts(self):
        return datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')

    def log(self, severity: str, event: str, message: str = '', **data: Any):
        severity = severity.upper()
        self._counts[severity] = self._counts.get(severity,0)+1
        rec = {
            'timestamp': self._ts(), 'build_id': self.build_id, 'severity': severity,
            'phase': self.current.get('phase'), 'scene_id': self.current.get('scene_id'),
            'unit_id': self.current.get('unit_id'), 'event': event, 'message': message,
            **data,
        }
        with open(self.events,'a',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(rec,ensure_ascii=False,separators=(',',':'))+'\n')
        human = f"[{rec['timestamp']}] {severity:<7} {rec['phase'] or '-':<22} {rec['scene_id'] or '-':<12} {event}"
        if message: human += ' - ' + message
        compact=[]
        for k,v in data.items():
            if k in ('traceback',): continue
            sv=str(v)
            if len(sv)>180: sv=sv[:177]+'...'
            compact.append(f'{k}={sv}')
        if compact: human += ' | ' + ' '.join(compact)
        with open(self.master,'a',encoding='utf-8',newline='\n') as f: f.write(human+'\n')
        if self.echo:
            print(human, flush=True)
        return rec

    def phase(self, name: str, **data):
        self.current.update({'phase':name,'scene_id':None,'unit_id':None})
        self.log('INFO','PHASE_START', **data)

    def scene(self, scene_id: str):
        self.current.update({'scene_id':scene_id,'unit_id':None})
        self.log('INFO','SCENE_START')

    def unit(self, unit_id: str | None):
        self.current['unit_id']=unit_id

    def checkpoint(self, path: os.PathLike | str, **data):
        rec = {'build_id':self.build_id,'timestamp':self._ts(),**self.current,**data}
        write_json(path,rec)
        self.log('DEBUG','CHECKPOINT_WRITTEN',path=str(path))

    def exception(self, event: str, exc: BaseException, **data):
        tb=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))
        return self.log('ERROR',event,str(exc),exception_type=type(exc).__name__,traceback=tb,**data)

    def finalize(self, status: str, **extra):
        data={'build_id':self.build_id,'status':status,'completed_at':self._ts(),'counts':self._counts,**extra}
        write_json(self.summary,data)
        self.log('PASS' if status=='PASS' else ('INFO' if 'PENDING' in str(status).upper() else 'ERROR'),'BUILD_FINALIZED',status=status)
        return data


def new_build_paths(base: os.PathLike | str, project_key: str, build_id: str | None=None) -> BuildPaths:
    root=ensure_dir(pathlib.Path(base)/project_key/(build_id or datetime.now().strftime('%Y%m%d-%H%M%S')))
    return BuildPaths(root=root, logs=ensure_dir(root/'logs'), scenes=ensure_dir(root/'scenes'), cache=ensure_dir(root/'cache'), outputs=ensure_dir(root/'outputs'), checkpoints=ensure_dir(root/'checkpoints'))
