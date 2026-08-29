from pathlib import Path
import importlib.util
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
INS_PATH=ROOT/'tools'/'install_v31.py'
INS=INS_PATH.read_text(encoding='utf-8')
JS=(ROOT/'extension'/'js'/'main.js').read_text(encoding='utf-8')
BAT=(ROOT/'INSTALL_HEXA_V31.bat').read_text(encoding='utf-8',errors='ignore')

def req(x,m):
    if not x: raise AssertionError(m)

# Bootstrap must select an interpreter by execution, not by file existence.
req('call :TRY_PY' in BAT,'bootstrap must execute-probe Python candidates')
req('SKIP_PYTHON_SOURCE' in BAT and 'SKIP_PYTHON_PATH' in BAT and 'SKIP_PYTHON_EXIT' in BAT,
    'bootstrap must skip and log broken Python candidates')
req('discover_legacy_site_packages' in INS and 'pyvenv.cfg' in INS,
    'installer must classify reusable site-packages independently of pyvenv.cfg')
req('where python.exe' in BAT and 'py -3 -c' in BAT,'bootstrap must fall back to PATH and Python launcher')
req('VideoBuilderV16' in BAT and 'VideoBuilderV8' in BAT,'bootstrap must probe additional legacy runtime families')
req('CURRENT_INSTALLER_LOG.txt' in BAT and 'del /q "%INSTALLMARKER%"' in BAT,
    'bootstrap diagnostics must clear stale installer log markers before launch')
req('if exist "%LOCALAPPDATA%\\HEXA\\VideoBuilderV12\\runtime\\.venv\\Scripts\\python.exe" set "PYEXE=' not in BAT,
    'old existence-only V12 selection regression returned')

# Exact runtime import contract.
req('installer_inherited_pythonpath_roots' in INS,'installer must freeze inherited import roots')
req('discover_legacy_site_packages' in INS,'installer must discover reusable package roots independently of venv launcher health')
req('selected_legacy_dependency_roots' in INS,'installer must store only package roots admitted by real imports')
req('LEGACY DEPENDENCY ROOT ADMITTED' in INS,'installer must log exact legacy-root admission')
req("'python_import_roots':python_import_roots" in INS,'runtime config must store final roots')
req("'python_import_contract_sha256':import_contract_sha" in INS,'runtime config must store import contract hash')
req('EXACT RUNTIME IMPORT PASS' in INS,'installer must exact-probe required dependencies')
req('EXACT RUNTIME IMPORT REPAIR' in INS,'installer must repair exact-runtime misses')
req("pip_target(str(py),vendor_overlay,item['pip'])" in INS,'repair must use V31-owned overlay')
req("env['PYTHONPATH']=_pythonpath_value(target/'py',python_import_roots)" in INS,'smoke test must use exact frozen roots')
req('runtimePythonPath(pyRoot)' in JS,'CEP must compose certified runtime python path')
req('runtime.python_import_roots.forEach(add)' in JS,'CEP must consume frozen roots')
req('Runtime Python import contract mismatch' in JS,'CEP must validate import contract')
req("str(target/'py')+os.pathsep+str(vendor)" not in INS,'old smoke path regression returned')

spec=importlib.util.spec_from_file_location('hexa_v31_installer_contract',INS_PATH)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

# Functional regression 1: a module available only from a dependency root must survive
# the exact engine PYTHONPATH composition. Omitting that root must fail.
with tempfile.TemporaryDirectory() as td:
    base=Path(td); dep=base/'dep_root'; engine=base/'engine_py'; dep.mkdir(); engine.mkdir()
    (dep/'hexa_probe_fixture_mod.py').write_text("__version__='fixture-1'\n",encoding='utf-8')
    ok,desc=mod._module_probe(sys.executable,[dep],'hexa_probe_fixture_mod',engine)
    req(ok,'frozen dependency root was not honored by exact runtime probe')
    req('VERSION=fixture-1' in desc,'fixture version missing from exact probe')
    bad,_=mod._module_probe(sys.executable,[],'hexa_probe_fixture_mod',engine)
    req(not bad,'probe unexpectedly succeeded without dependency root')

# Functional regression 2: missing pyvenv.cfg must not make the package cache unusable.
# This models the user's V12 failure: Scripts/python.exe is broken, but Lib/site-packages
# can still be reused by a separately executable compatible interpreter.
with tempfile.TemporaryDirectory() as td:
    localapp=Path(td)
    site=localapp/'HEXA'/'VideoBuilderV12'/'runtime'/'.venv'/'Lib'/'site-packages'
    site.mkdir(parents=True)
    # deliberately DO NOT create .venv/pyvenv.cfg
    (site/'hexa_broken_venv_cache_fixture.py').write_text("__version__='cache-ok'\n",encoding='utf-8')
    roots=mod.discover_legacy_site_packages(localapp)
    req(str(site.resolve()) in roots,'legacy site-packages was not discovered when pyvenv.cfg is absent')
    ok,desc=mod._module_probe(sys.executable,[site],'hexa_broken_venv_cache_fixture')
    req(ok and 'VERSION=cache-ok' in desc,'package cache from broken venv was not reusable through selected interpreter')


# V31.0.1: import success is not enough. A shadow module without the API the engine
# needs must fail the capability probe instead of being recorded as reusable.
with tempfile.TemporaryDirectory() as td3:
    td3=Path(td3); (td3/'numpy.py').write_text('__version__="fake"\n',encoding='utf-8')
    ok4,desc4=mod._module_probe(sys.executable,[td3],'numpy')
    assert not ok4,('CAPABILITY_FALSE_POSITIVE_GUARD',desc4)

print('V31_0_1_RUNTIME_IMPORT_PATH_CONTRACT_PASS')
