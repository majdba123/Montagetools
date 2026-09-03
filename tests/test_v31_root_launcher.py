from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'bayer.bat'
CLEANUP = ROOT / 'tools' / 'cleanup_generated_release_artifacts.ps1'


def make_fixture(base: Path, *, latest: bool = True, installer: bool = True,
                 build_helper: bool = True, validation_package: bool = True) -> Path:
    repo = base / 'Repository With Spaces'
    (repo / 'tools').mkdir(parents=True)
    shutil.copy2(LAUNCHER, repo / 'bayer.bat')
    shutil.copy2(CLEANUP, repo / 'tools' / CLEANUP.name)

    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    (repo / 'source-marker.txt').write_text('source\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'source-marker.txt'], cwd=repo, check=True)
    subprocess.run(
        ['git', '-c', 'user.name=HEXA Test', '-c', 'user.email=test@hexa.invalid',
         'commit', '-q', '-m', 'fixture'],
        cwd=repo,
        check=True,
    )
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()

    def write_latest(source_commit: str):
        payload = repo / 'dist' / 'latest'
        (payload / 'extension' / 'py' / 'hexa_v31').mkdir(parents=True, exist_ok=True)
        (payload / 'tools').mkdir(parents=True, exist_ok=True)
        (payload / 'extension' / 'py' / 'hexa_v31' / '__init__.py').write_text('', encoding='utf-8')
        (payload / 'tools' / 'install_v31.py').write_text('# fixture\n', encoding='utf-8')
        if installer:
            (payload / 'INSTALL_HEXA_V31.bat').write_text(
                '@echo off\n'
                'if defined HEXA_TEST_INSTALL_MARKER >"%HEXA_TEST_INSTALL_MARKER%" echo LATEST_INSTALLER_INVOKED\n'
                'if defined HEXA_TEST_INSTALL_EXIT exit /b %HEXA_TEST_INSTALL_EXIT%\n'
                'exit /b 0\n',
                encoding='utf-8',
            )
        (payload / 'release_identity.json').write_text(
            json.dumps({'schema': 'HEXA_V31_RELEASE_IDENTITY', 'source_commit': source_commit}),
            encoding='utf-8',
        )

    validation = repo / 'Final Packages' / 'HEXA_FINAL_PACKAGE_V1.0.zip'
    if validation_package:
        validation.parent.mkdir(parents=True, exist_ok=True)
        validation.write_bytes(b'fixture-package')

    if build_helper:
        (repo / 'tools' / 'build_latest_release.ps1').write_text(
            """param([Parameter(Mandatory=$true)][string]$PackagePath)
$ErrorActionPreference='Stop'
if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) { throw 'validation package missing' }
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$commit=(& git -C $root rev-parse HEAD | Out-String).Trim()
$latest=Join-Path $root 'dist\\latest'
New-Item -ItemType Directory -Force -Path (Join-Path $latest 'extension\\py\\hexa_v31') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $latest 'tools') | Out-Null
Set-Content -LiteralPath (Join-Path $latest 'extension\\py\\hexa_v31\\__init__.py') -Value '' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $latest 'tools\\install_v31.py') -Value '# fixture' -Encoding UTF8
Set-Content -LiteralPath (Join-Path $latest 'INSTALL_HEXA_V31.bat') -Encoding ASCII -Value @(
'@echo off',
'if defined HEXA_TEST_INSTALL_MARKER >"%HEXA_TEST_INSTALL_MARKER%" echo LATEST_INSTALLER_INVOKED',
'if defined HEXA_TEST_INSTALL_EXIT exit /b %HEXA_TEST_INSTALL_EXIT%',
'exit /b 0'
)
@{schema='HEXA_V31_RELEASE_IDENTITY';source_commit=$commit} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $latest 'release_identity.json') -Encoding UTF8
Write-Output 'HEXA_DIST_LATEST_BUILD_PASS'
""",
            encoding='utf-8',
        )

    if latest:
        write_latest(commit)
    return repo


def run_launcher(repo: Path, cwd: Path, *, code: int = 0, validation_env: bool = True):
    marker = repo / 'latest installer marker.txt'
    env = os.environ.copy()
    env['HEXA_TEST_INSTALL_MARKER'] = str(marker)
    env['HEXA_TEST_INSTALL_EXIT'] = str(code)
    validation = repo / 'Final Packages' / 'HEXA_FINAL_PACKAGE_V1.0.zip'
    if validation_env and validation.is_file():
        env['HEXA_V31_VALIDATION_PACKAGE'] = str(validation)
    else:
        env.pop('HEXA_V31_VALIDATION_PACKAGE', None)
    command = f'cmd.exe /d /s /c call "{repo / "bayer.bat"}"'
    cp = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    return cp, marker


with tempfile.TemporaryDirectory(prefix='.hexa_launcher_test_', dir=ROOT) as raw:
    base = Path(raw)

    missing_latest = make_fixture(base / 'missing latest', latest=False)
    cp, marker = run_launcher(missing_latest, base)
    assert cp.returncode == 0, cp.stdout
    assert marker.is_file(), cp.stdout
    assert 'Rebuilding a validated release payload' in cp.stdout, cp.stdout
    assert 'HEXA INSTALL COMPLETE' in cp.stdout, cp.stdout

    missing_validation = make_fixture(base / 'missing validation', latest=False, validation_package=False)
    env = os.environ.copy()
    env['HEXA_V31_DISABLE_FILE_PICKER'] = '1'
    marker = missing_validation / 'latest installer marker.txt'
    env['HEXA_TEST_INSTALL_MARKER'] = str(marker)
    env['HEXA_TEST_INSTALL_EXIT'] = '0'
    command = f'cmd.exe /d /s /c call "{missing_validation / "bayer.bat"}"'
    cp = subprocess.run(
        command, cwd=base, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
    )
    assert cp.returncode == 30, cp.stdout
    assert 'interactive selection is disabled' in cp.stdout.lower(), cp.stdout

    missing_installer = make_fixture(base / 'missing installer', installer=False)
    cp, marker = run_launcher(missing_installer, base)
    assert cp.returncode == 0, cp.stdout
    assert marker.is_file(), cp.stdout
    assert 'Rebuilding a validated release payload' in cp.stdout, cp.stdout

    repo = make_fixture(base / 'success')
    protected = {
        repo / 'extension' / 'source.py': 'source',
        repo / 'tests' / 'test.txt': 'tests',
        repo / 'docs' / 'guide.txt': 'docs',
        repo / 'Final Packages' / 'package.zip': 'package',
        repo / 'voice' / 'voice.wav': 'voice',
        repo / 'dist' / 'latest' / 'keep.txt': 'latest',
    }
    for path, text in protected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    stale = [
        repo / 'dist' / 'staging' / 'old.txt',
        repo / 'dist' / 'temp' / 'old.txt',
        repo / 'dist' / '_tmp' / 'old.txt',
        repo / 'dist' / '.latest-stage-deadbeef' / 'old.txt',
        repo / '.hexa_validate' / 'old.txt',
    ]
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('generated', encoding='utf-8')

    source_marker = repo / 'source installer marker.txt'
    (repo / 'INSTALL_HEXA_V31.bat').write_text(
        f'@echo off\n>"{source_marker}" echo SOURCE_INSTALLER_INVOKED\nexit /b 0\n',
        encoding='utf-8',
    )

    other_cwd = base / 'Different Current Directory'
    other_cwd.mkdir()
    cp, marker = run_launcher(repo, other_cwd)
    assert cp.returncode == 0, cp.stdout
    assert marker.read_text(encoding='utf-8').strip() == 'LATEST_INSTALLER_INVOKED'
    assert 'HEXA INSTALL COMPLETE' in cp.stdout, cp.stdout
    assert not source_marker.exists(), 'launcher used repository-source installer'
    assert all(not path.parent.exists() for path in stale), 'allowlisted generated artifacts survived'
    for path, text in protected.items():
        assert path.read_text(encoding='utf-8') == text, f'protected path changed: {path}'
    assert (repo / 'dist' / 'latest').is_dir(), 'dist/latest was deleted'

    cp, marker = run_launcher(repo, other_cwd, code=37)
    assert cp.returncode == 37, (cp.returncode, cp.stdout)
    assert marker.is_file(), 'validated installer was not invoked for failure propagation test'
    assert 'HEXA INSTALL COMPLETE' not in cp.stdout, cp.stdout

    (repo / 'dist' / 'latest' / 'release_identity.json').write_text(
        json.dumps({'source_commit': '0' * 40}),
        encoding='utf-8',
    )
    cp, marker = run_launcher(repo, other_cwd)
    assert cp.returncode == 0, cp.stdout
    assert marker.is_file(), cp.stdout
    assert 'Rebuilding a validated release payload' in cp.stdout, cp.stdout
    rebuilt = json.loads((repo / 'dist' / 'latest' / 'release_identity.json').read_text(encoding='utf-8-sig'))
    expected = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    assert rebuilt['source_commit'] == expected, (rebuilt, expected)

print('V31_ROOT_LAUNCHER_PASS')
