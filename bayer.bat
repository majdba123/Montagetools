@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_ROOT=%~dp0"
for %%I in ("%REPO_ROOT%.") do set "REPO_ROOT=%%~fI"
set "LATEST=%REPO_ROOT%\dist\latest"
set "LATEST_INSTALLER=%LATEST%\INSTALL_HEXA_V31.bat"
set "CLEANUP_HELPER=%REPO_ROOT%\tools\cleanup_generated_release_artifacts.ps1"
set "BUILD_HELPER=%REPO_ROOT%\tools\build_latest_release.ps1"

set "SOURCE_COMMIT="
for /f "delims=" %%S in ('git -C "%REPO_ROOT%" rev-parse HEAD 2^>nul') do if not defined SOURCE_COMMIT set "SOURCE_COMMIT=%%S"
if not defined SOURCE_COMMIT (
  echo ERROR: Cannot resolve the authoritative source commit.
  exit /b 26
)

call :CHECK_RELEASE
if "%RELEASE_READY%"=="1" goto RELEASE_READY

echo INFO: dist\latest is missing, incomplete, or stale for SOURCE_COMMIT=%SOURCE_COMMIT%.
echo INFO: Rebuilding a validated release payload from the current branch...
call :REBUILD_RELEASE
if not exist "%BUILD_HELPER%" (
  echo ERROR: Release build helper is missing: "%BUILD_HELPER%"
  exit /b 28
)

echo INFO: Building release from source/runtime contracts. Project package selection remains inside Premiere.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%BUILD_HELPER%"
set "BUILD_RC=%ERRORLEVEL%"
if not "%BUILD_RC%"=="0" (
  echo ERROR: Validated dist\latest rebuild failed with exit code %BUILD_RC%.
  exit /b %BUILD_RC%
)
exit /b 0
