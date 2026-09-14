import importlib.util, json, pathlib, tempfile
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('foundation_provisioner',ROOT/'tools'/'provision_foundation_vision.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def fake_nvidia(_cmd,timeout=0):return 'NVIDIA GeForce 930MX, 2048, 5.0\n'
hardware=module.detect_hardware(fake_nvidia)
assert hardware['nvidia_present'] and hardware['profile']=='LOW_MEMORY'
assert module.CUDA_INDEX.endswith('/cu118') and module.CPU_INDEX.endswith('/cpu')
assert all('sam2==' not in item for item in module.PACKAGES)

registry=json.loads((ROOT/'extension'/'resources'/'HEXA_FOUNDATION_VISION_MODELS_V31.json').read_text(encoding='utf-8'))
source=registry['sam2_source']
assert source['repository']=='https://github.com/facebookresearch/sam2'
assert len(source['commit'])==40 and len(source['archive_sha256'])==64
low=[item for item in registry['models'] if item['profile']=='low_memory']
assert {item['backend'] for item in low}=={'florence2','sam2'}
assert all(len(item['revision'])==40 and len(item['checkpoint_sha256'])==64 for item in low)

with patch.object(module.venv,'EnvBuilder'), patch.object(module,'run',return_value='') as runner:
    module._install_stack(pathlib.Path('unused-test-venv'),False)
    commands=[call.args[0] for call in runner.call_args_list]
    torch_index=next(i for i,cmd in enumerate(commands) if '--index-url' in cmd)
    assert any('numpy==1.26.4' in cmd and 'Pillow==11.1.0' in cmd for cmd in commands[:torch_index])

with tempfile.TemporaryDirectory() as directory:
    cache=pathlib.Path(directory)/'cache'
    checkout=cache/'sam2-sparse'
    (checkout/'.git').mkdir(parents=True)
    calls=[]
    def record_run(cmd, **kwargs):
        calls.append([str(x) for x in cmd])
        if cmd[-2:]==['rev-parse','HEAD']:return source['commit']+'\n'
        return ''
    with patch.object(module,'run',side_effect=record_run):
        result=module._install_official_sam2('python',{},source,pathlib.Path(directory)/'stage',cache)
    installs=[cmd for cmd in calls if 'install' in cmd]
    assert len(installs)==1, calls
    assert installs[0][:4]==['python','-m','pip','install']
    assert '--no-deps' in installs[0] and '--no-build-isolation' in installs[0]
    assert installs[0][-1]==str(checkout)
    assert result['install_source']=='OFFICIAL_PINNED_GIT_COMMIT'

print('V31_FOUNDATION_PROVISIONING_POLICY_PASS')
