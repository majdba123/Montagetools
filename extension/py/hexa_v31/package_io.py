from __future__ import annotations
import json, os, pathlib, re, shutil, zipfile
import numpy as np
from dataclasses import dataclass
from typing import Any
from PIL import Image
from .util import ensure_dir, path_is_within, read_json, sha256_file


class PackageError(RuntimeError): pass

@dataclass
class ScenePackage:
    zip_path: pathlib.Path
    extract_root: pathlib.Path
    manifest: dict
    plan: dict
    script: str
    scenes: list[dict]


def _safe_extract(zf: zipfile.ZipFile, target: pathlib.Path):
    root=target.resolve()
    for info in zf.infolist():
        name=info.filename.replace('\\','/')
        if name.startswith('/') or re.match(r'^[A-Za-z]:',name) or '..' in pathlib.PurePosixPath(name).parts:
            raise PackageError(f'Unsafe ZIP member: {info.filename}')
        dest=(target/pathlib.PurePosixPath(name)).resolve()
        if not path_is_within(dest,root): raise PackageError(f'ZIP traversal rejected: {name}')
    zf.extractall(target)


def open_and_validate(zip_path: str | os.PathLike, cache_root: str | os.PathLike, logger=None) -> ScenePackage:
    zp=pathlib.Path(zip_path).resolve()
    if not zp.is_file(): raise PackageError(f'Package not found: {zp}')
    pkg_sha=sha256_file(zp)
    out=ensure_dir(pathlib.Path(cache_root)/('package_'+pkg_sha[:20]))
    marker=out/'.validated'
    if not marker.exists():
        if out.exists():
            for c in out.iterdir():
                if c.name!='.validated': shutil.rmtree(c) if c.is_dir() else c.unlink()
        with zipfile.ZipFile(zp,'r') as zf: _safe_extract(zf,out)
    for f in ('manifest.json','scene_plan.json','canonical_script.txt'):
        if not (out/f).is_file(): raise PackageError(f'Missing root file: {f}')
    manifest=read_json(out/'manifest.json')
    plan=read_json(out/'scene_plan.json')
    script=(out/'canonical_script.txt').read_text(encoding='utf-8-sig')
    if manifest.get('package_schema')!='HEXA_V20_SCENE_PACKAGE': raise PackageError('Unsupported package_schema')
    version=str(manifest.get('package_version'))
    if version not in ('1.0','1.1'): raise PackageError('Unsupported package_version')
    if plan.get('schema_name')!='HEXA_V20_SCENE_PLAN': raise PackageError('Unsupported scene plan schema')
    if str(plan.get('schema_version'))!='1.0': raise PackageError('Unsupported scene plan version')
    if plan.get('canonical_script',{}).get('text') != script: raise PackageError('canonical_script.txt != scene_plan canonical_script.text')
    scenes=plan.get('scenes') or []
    n=int(manifest.get('scene_count',-1))
    if n != len(scenes) or int(plan.get('scene_count',-2)) != len(scenes): raise PackageError('Scene count mismatch')
    ids=[s.get('scene_id') for s in scenes]
    if len(set(ids))!=len(ids): raise PackageError('Duplicate scene IDs')
    orders=[int(s.get('order',0)) for s in scenes]
    if orders != list(range(1,len(scenes)+1)): raise PackageError('Scene order must be 1..N')
    # script spans and triggers
    for s in scenes:
        beats=s.get('semantic_beats', None)
        if beats is None: beats=[s['semantic_beat']] if s.get('semantic_beat') is not None else []
        if not isinstance(beats,list) or not all(isinstance(x,dict) for x in beats): raise PackageError(f"Invalid semantic beat: {s.get('scene_id')}")
        s['semantic_beats']=beats
        s['dominant_semantic_beat']=beats[0] if beats else None
        sp=s.get('script_span') or {}; a=int(sp.get('global_char_start',-1)); b=int(sp.get('global_char_end',-1)); txt=sp.get('text')
        if a<0 or b<a or script[a:b]!=txt: raise PackageError(f"Exact script slice failed: {s.get('scene_id')}")
        for u in s.get('units') or []:
            for key in ('appear_trigger','focus_trigger','exit_trigger'):
                t=u.get(key)
                if t is not None: _validate_trigger(t,script,a,b,s.get('scene_id'),key)
        for ev in s.get('visual_progression') or []:
            _validate_trigger(ev.get('trigger'),script,a,b,s.get('scene_id'),'visual_progression.trigger')
            known={u.get('unit_id') for u in s.get('units') or []}
            for target in ev.get('targets') or []:
                if target not in known: raise PackageError(f"Unknown progression target {target} in {s.get('scene_id')}")
        img=(out/s.get('image','')).resolve()
        if not path_is_within(img,out) or not img.is_file(): raise PackageError(f"Missing scene image: {s.get('scene_id')}")
        try:
            with Image.open(img) as im: im.verify()
        except Exception as e: raise PackageError(f"Unreadable PNG {s.get('scene_id')}: {e}")
    # exact hash validation
    hashes=manifest.get('sha256') or {}
    for rel,expected in hashes.items():
        p=(out/rel).resolve()
        if not path_is_within(p,out) or not p.is_file(): raise PackageError(f'Hash target missing/unsafe: {rel}')
        got=sha256_file(p)
        if got.lower()!=str(expected).lower(): raise PackageError(f'Hash mismatch: {rel}')
    if version=='1.1' and bool((manifest.get('capabilities') or manifest.get('optional_capabilities') or {}).get('object_hint_maps')):
        _validate_object_hints(out,manifest,scenes)
    marker.write_text(pkg_sha,encoding='ascii')
    if logger: logger.log('PASS','PACKAGE_VALIDATED',scene_count=len(scenes),package_sha256=pkg_sha,project_id=plan.get('project_id'))
    return ScenePackage(zp,out,manifest,plan,script,scenes)

def _validate_object_hints(root, manifest, scenes):
    """Validate V1.1 semantic ROIs; maps never become alpha mattes."""
    path=root/'object_hints.npz'
    if not path.is_file(): raise PackageError('V1.1 object_hints.npz missing')
    hashes=manifest.get('sha256') or {}
    if 'object_hints.npz' not in hashes: raise PackageError('V1.1 object_hints.npz hash missing')
    try:
        with np.load(path,allow_pickle=False) as maps:
            expected={str(s.get('scene_id')) for s in scenes}
            if set(maps.files)!=expected: raise PackageError('V1.1 object hint scene keys mismatch')
            for scene in scenes:
                sid=str(scene['scene_id']); a=maps[sid]
                if a.ndim!=2 or a.dtype!=np.uint8 or tuple(a.shape)!=(288,512): raise PackageError(f'Invalid object hint map: {sid}')
                hint_spec=scene.get('extraction_hints') or {}
                hints=scene.get('object_hints') or hint_spec.get('objects') or []
                if (scene.get('map_size') or hint_spec.get('map_size'))!=[512,288]: raise PackageError(f'Invalid object hint map_size: {sid}')
                if hint_spec.get('map_key') not in (None,sid): raise PackageError(f'Invalid object hint map_key: {sid}')
                labels=[int(x.get('label',-1)) for x in hints]; ids=[str(x.get('object_id') or x.get('id') or '') for x in hints]
                if len(labels)!=len(set(labels)) or len(ids)!=len(set(ids)) or any(not x for x in ids): raise PackageError(f'Duplicate object hint identity: {sid}')
                if any(str(x.get('extraction_policy') or x.get('policy') or '').upper() not in {'MOVABLE','CONNECTED','ATOMIC'} for x in hints): raise PackageError(f'Invalid object hint policy: {sid}')
                defined=set(labels); present=set(int(x) for x in np.unique(a) if int(x))
                if present!=defined or 0 in defined: raise PackageError(f'Undefined object hint label: {sid}')
                scene['_object_hint_map_path']=str(path); scene['_object_hint_objects']=[dict(x,object_id=x.get('object_id') or x.get('id'),extraction_policy=x.get('extraction_policy') or x.get('policy')) for x in hints]
    except PackageError: raise
    except Exception as e: raise PackageError(f'Invalid object_hints.npz: {e}')


def _validate_trigger(t: dict|None, script: str, scene_a: int, scene_b: int, scene_id: str, label: str):
    if not isinstance(t,dict): raise PackageError(f'Missing trigger object: {scene_id}/{label}')
    a=int(t.get('global_char_start',-1)); b=int(t.get('global_char_end',-1)); phrase=t.get('phrase')
    if a<scene_a or b>scene_b or a<0 or b<a: raise PackageError(f'Trigger outside scene: {scene_id}/{label}')
    if script[a:b]!=phrase: raise PackageError(f'Trigger literal mismatch: {scene_id}/{label}')
    local=script[scene_a:scene_b]
    occ=int(t.get('occurrence_in_scene',1))
    starts=[]; pos=0
    while True:
        i=local.find(phrase,pos)
        if i<0: break
        starts.append(i); pos=i+max(1,len(phrase))
    if occ<1 or occ>len(starts) or scene_a+starts[occ-1]!=a: raise PackageError(f'Trigger occurrence mismatch: {scene_id}/{label}')
