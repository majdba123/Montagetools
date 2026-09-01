[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackagePath
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\', '/')
$dist = Join-Path $root 'dist'
$latest = Join-Path $dist 'latest'
$stage = Join-Path $dist ('.latest-stage-' + [guid]::NewGuid().ToString('N'))
$backup = Join-Path $dist ('.latest-backup-' + [guid]::NewGuid().ToString('N'))
$template = Join-Path $root 'tools\release\INSTALL_HEXA_V31.bat'
$runtimeConfig = Join-Path $env:LOCALAPPDATA 'HEXA\VideoBuilderV31\runtime_config.json'

function Invoke-Checked([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory, [hashtable]$Environment) {
    $previous = @{}
    foreach ($key in $Environment.Keys) {
        $previous[$key] = [System.Environment]::GetEnvironmentVariable($key, 'Process')
        [System.Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
    }
    Push-Location $WorkingDirectory
    try {
        $output = (& $Executable @Arguments 2>&1 | Out-String)
        $code = $LASTEXITCODE
        if ($code -ne 0) { throw "Command failed ($code): $Executable $($Arguments -join ' ')`n$output" }
        return $output
    }
    finally {
        Pop-Location
        foreach ($key in $Environment.Keys) {
            [System.Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $template -PathType Leaf)) { throw "Installer template missing: $template" }
    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) { throw "V1.0 validation package missing: $PackagePath" }
    if (-not (Test-Path -LiteralPath $runtimeConfig -PathType Leaf)) { throw "Runtime config missing: $runtimeConfig" }

    New-Item -ItemType Directory -Force -Path (Join-Path $stage 'tools') | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'extension') -Destination (Join-Path $stage 'extension') -Recurse
    Copy-Item -LiteralPath (Join-Path $root 'tools\install_v31.py') -Destination (Join-Path $stage 'tools\install_v31.py')
    Copy-Item -LiteralPath (Join-Path $root 'tools\selftest_v31.py') -Destination (Join-Path $stage 'tools\selftest_v31.py')
    Copy-Item -LiteralPath (Join-Path $root 'tools\provision_foundation_vision.py') -Destination (Join-Path $stage 'tools\provision_foundation_vision.py')
    Copy-Item -LiteralPath $template -Destination (Join-Path $stage 'INSTALL_HEXA_V31.bat')
    Copy-Item -LiteralPath (Join-Path $root 'README_FIRST.txt') -Destination (Join-Path $stage 'README_FIRST.txt')
    Get-ChildItem -LiteralPath $stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stage -Recurse -File -Filter '*.pyc' | Remove-Item -Force

    $cfg = Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json
    $python = [string]$cfg.python_exe
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Configured Python missing: $python" }
    $pythonRoots = @((Join-Path $stage 'extension\py')) + @($cfg.python_import_roots)
    $environment = @{
        'PYTHONPATH' = ($pythonRoots -join [System.IO.Path]::PathSeparator)
        'PYTHONDONTWRITEBYTECODE' = '1'
        'HEXA_V31_RUNTIME_CONFIG' = $runtimeConfig
        'HEXA_FFMPEG' = [string]$cfg.ffmpeg_path
    }
    if ($cfg.ffprobe_path) { $environment['HEXA_FFPROBE'] = [string]$cfg.ffprobe_path }

    $origin = Invoke-Checked $python @('-c', "import pathlib,hexa_v31; p=pathlib.Path(hexa_v31.__file__).resolve(); root=pathlib.Path.cwd().resolve(); assert root in p.parents,(root,p); print(p)") $stage $environment
    if (-not $origin.Trim().StartsWith($stage, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Staged import escaped the release payload' }
    [void](Invoke-Checked $python @('-m','hexa_v31.cli','--help') $stage $environment)
    [void](Invoke-Checked $python @('-m','hexa_v31.cli','validate-package','--package',([System.IO.Path]::GetFullPath($PackagePath))) $stage $environment)
    $selftestReport = Join-Path $stage 'runtime_selftest.json'
    [void](Invoke-Checked $python @('tools\selftest_v31.py','--extension-root','extension','--out',$selftestReport) $stage $environment)
    $report = Get-Content -LiteralPath $selftestReport -Raw | ConvertFrom-Json
    if ($report.status -ne 'PASS') { throw 'Staged runtime selftest did not pass' }
    Remove-Item -LiteralPath $selftestReport -Force

    foreach ($required in @('extension\CSXS\manifest.xml','extension\jsx\host.jsx','extension\resources\HEXA_USER_PRESET_AUTHORITY_V31.json','extension\resources\HEXA_FOUNDATION_VISION_MODELS_V31.json','extension\resources\THIRD_PARTY_LICENSES_V31.json','tools\install_v31.py','tools\provision_foundation_vision.py','INSTALL_HEXA_V31.bat')) {
        if (-not (Test-Path -LiteralPath (Join-Path $stage $required) -PathType Leaf)) { throw "Validated payload missing: $required" }
    }

    $hadLatest = Test-Path -LiteralPath $latest
    try {
        if ($hadLatest) { Move-Item -LiteralPath $latest -Destination $backup }
        Move-Item -LiteralPath $stage -Destination $latest
    }
    catch {
        if ((Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $latest)) { Move-Item -LiteralPath $backup -Destination $latest }
        throw
    }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
    & (Join-Path $root 'tools\cleanup_generated_release_artifacts.ps1') -RepositoryRoot $root
    if ($LASTEXITCODE -ne 0) { throw 'Post-build generated-artifact cleanup failed' }
    Write-Output 'HEXA_DIST_LATEST_BUILD_PASS'
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
