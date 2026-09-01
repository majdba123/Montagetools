from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools'/'install_v31.py'
s=p.read_text(encoding='utf-8')
assert 'def _windows_extended_path_string(s):' in s
assert 'def _win_extended(path):' in s
assert "log('PHASE 0/8 - Package preflight + Windows long-path-safe staging')" in s
assert '_copytree_long(EXT_SRC,stage)' in s
assert "dep=read_json(stage/'resources'/'DEPENDENCY_MANIFEST_V20.json')" in s
assert s.index("PHASE 0/8 - Package preflight") < s.index("PHASE 1/8 - Replace the known V31 CEP extension target")
assert s.index('_copytree_long(EXT_SRC,stage)') < s.index('removed=clean_extension_target(target)')
assert "if target.name!=BUNDLE or target.parent.name.lower()!='extensions':" in s
assert "if target.exists():raise RuntimeError('V31 target cleanup did not complete: '+str(target))" in s
assert "VERSION='31.0.25'" in s
assert "BUNDLE='com.hexaterminal.videobuilder.v31_0_1'" in s
print('V31_0_9_INSTALL_PATH_AND_STABLE_BUNDLE_PASS')

# Pure Windows namespace regression independent of the host OS.
import importlib.util
spec=importlib.util.spec_from_file_location('install_v31_hotfix',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m._windows_extended_path_string(r'C:\\Users\\X\\deep\\file.json').startswith('\\\\?\\C:')
assert m._windows_extended_path_string(r'\\\\server\\share\\file.json').startswith('\\\\?\\UNC\\')
