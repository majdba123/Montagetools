[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryRoot
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedFullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

try {
    $root = Get-NormalizedFullPath $RepositoryRoot
    Write-Output "CLEANUP_ROOT=$root"
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Repository root does not exist: $root"
    }

    $rootPrefix = $root + [System.IO.Path]::DirectorySeparatorChar
    $protectedTopLevel = @(
        '.git', 'extension', 'tests', 'tools', 'docs',
        'Final Packages', 'voice', 'audio', 'videos', 'references', 'Premiere Projects'
    )
    $literalAllowlist = @(
        'dist\staging',
        'dist\temp',
        'dist\_tmp',
        'dist\clean-extract',
        'dist\clean_extract',
        '.hexa_validate',
        '.tmp_release_validation',
        '.hexa_release_scratch'
    )
    $distDirectoryNamePatterns = @(
        '.latest-stage-*',
        '.latest-backup-*',
        'clean-extract-*',
        'clean_extract_*',
        'installer-staging-*',
        '_installer-staging-*'
    )

    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($relative in $literalAllowlist) {
        $candidates.Add((Join-Path $root $relative))
    }

    $dist = Join-Path $root 'dist'
    if (Test-Path -LiteralPath $dist -PathType Container) {
        foreach ($directory in Get-ChildItem -LiteralPath $dist -Directory -Force) {
            foreach ($pattern in $distDirectoryNamePatterns) {
                if ($directory.Name -like $pattern) {
                    $candidates.Add($directory.FullName)
                    break
                }
            }
        }
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    $isGitRepository = $null -ne $git -and (Test-Path -LiteralPath (Join-Path $root '.git'))
    foreach ($candidateValue in $candidates | Select-Object -Unique) {
        $candidate = Get-NormalizedFullPath $candidateValue
        if (-not $candidate.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing cleanup outside repository: $candidate"
        }

        $relative = $candidate.Substring($rootPrefix.Length).Replace('\', '/')
        $top = ($relative -split '/')[0]
        if ($protectedTopLevel -contains $top -or $relative -eq 'dist/latest' -or $relative.StartsWith('dist/latest/')) {
            throw "Refusing cleanup of protected path: $relative"
        }
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        if ($isGitRepository) {
            $tracked = & git -C $root ls-files -- $relative 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "Unable to verify Git ownership for cleanup path: $relative"
            }
            if ($tracked) {
                throw "Refusing cleanup because path contains Git-tracked files: $relative"
            }
        }

        Remove-Item -LiteralPath $candidate -Recurse -Force
        Write-Output "REMOVED_GENERATED_ARTIFACT=$relative"
    }

    Write-Output 'HEXA_GENERATED_ARTIFACT_CLEANUP_PASS'
    exit 0
}
catch {
    Write-Error $_
    exit 25
}
