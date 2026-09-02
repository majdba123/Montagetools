import importlib.util, json, pathlib, tempfile

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

print('V31_FOUNDATION_PROVISIONING_POLICY_PASS')
