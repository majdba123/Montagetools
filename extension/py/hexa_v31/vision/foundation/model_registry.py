from __future__ import annotations
import hashlib,json,pathlib
from .errors import ModelIntegrityError

REGISTRY_SCHEMA='HEXA_FOUNDATION_VISION_MODEL_REGISTRY_1.0'

def load_registry(path):
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    if data.get('schema')!=REGISTRY_SCHEMA:raise ModelIntegrityError('Unsupported Foundation Vision registry schema')
    return data

def sha256_file(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def resolve_models(registry_path,models_root,profile='QUALITY'):
    registry=load_registry(registry_path); root=pathlib.Path(models_root)
    wanted='quality' if profile=='QUALITY' else 'low_memory'; resolved={}
    for item in registry['models']:
        if item.get('profile')!=wanted:continue
        local=root/item['local_path']; checkpoint=local/item.get('checkpoint_file','model.safetensors') if local.is_dir() else local; expected=item.get('checkpoint_sha256')
        status='MISSING'
        if checkpoint.is_file():status='INSTALLED' if (not expected or sha256_file(checkpoint)==expected) else 'CORRUPT'
        row=dict(item,absolute_path=str(local),checkpoint_path=str(checkpoint),installation_status=status)
        if status=='CORRUPT':raise ModelIntegrityError('Checkpoint SHA256 mismatch: '+str(local))
        resolved[item['backend']]=row
    return resolved

def fingerprint(registry_path,profile='QUALITY'):
    data=load_registry(registry_path)
    rows=[{k:m.get(k) for k in ('backend','model_id','revision','checkpoint_sha256','profile')} for m in data['models'] if m.get('profile')==('quality' if profile=='QUALITY' else 'low_memory')]
    payload={'models':rows,'sam2_source':data.get('sam2_source')}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
