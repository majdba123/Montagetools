@echo off
setlocal EnableExtensions

set "REPO_ROOT=%~dp0"
for %%I in ("%REPO_ROOT%.") do set "REPO_ROOT=%%~fI"
set "LATEST=%REPO_ROOT%\dist\latest"
set "LATEST_INSTALLER=%LATEST%\INSTALL_HEXA_V31.bat"
set "CLEANUP_HELPER=%REPO_ROOT%\tools\cleanup_generated_release_artifacts.ps1"

if not exist "%LATEST%\" (
  echo ERROR: Validated payload directory is missing: "%LATEST%"
  exit /b 20
)
if not exist "%LATEST_INSTALLER%" (
  echo ERROR: Validated installer is missing: "%LATEST_INSTALLER%"
  exit /b 21
)
if not exist "%LATEST%\extension\py\hexa_v31\__init__.py" (
  echo ERROR: Validated Python payload is incomplete under dist\latest.
  exit /b 22
)
if not exist "%LATEST%\tools\install_v31.py" (
  echo ERROR: Validated installer payload is incomplete under dist\latest.
  exit /b 23
)
if not exist "%LATEST%\release_identity.json" (
  echo ERROR: Validated payload has no release identity. Rebuild dist\latest from the current certified source.
  exit /b 25
)
set "SOURCE_COMMIT="
set "RELEASE_COMMIT="
for /f "delims=" %%S in ('git -C "%REPO_ROOT%" rev-parse HEAD 2^>nul') do if not defined SOURCE_COMMIT set "SOURCE_COMMIT=%%S"
for /f "delims=" %%S in ('%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo -NoProfile -NonInteractive -Command "(Get-Content -LiteralPath '%LATEST%\release_identity.json' -Raw | ConvertFrom-Json).source_commit"') do if not defined RELEASE_COMMIT set "RELEASE_COMMIT=%%S"
if not defined SOURCE_COMMIT (
  echo ERROR: Cannot resolve the authoritative source commit.
  exit /b 26
)
if /i not "%SOURCE_COMMIT%"=="%RELEASE_COMMIT%" (
  echo ERROR: dist\latest is stale. SOURCE_COMMIT=%SOURCE_COMMIT% RELEASE_COMMIT=%RELEASE_COMMIT%
  echo Rebuild the validated release payload before installing.
  exit /b 27
)
echo SOURCE_COMMIT=%SOURCE_COMMIT%
if not exist "%CLEANUP_HELPER%" (
  echo ERROR: Safe cleanup helper is missing: "%CLEANUP_HELPER%"
  exit /b 24
)

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%CLEANUP_HELPER%" -RepositoryRoot "%REPO_ROOT%"
set "CLEANUP_RC=%ERRORLEVEL%"
if not "%CLEANUP_RC%"=="0" (
  echo ERROR: Safe generated-artifact cleanup failed with exit code %CLEANUP_RC%.
  exit /b %CLEANUP_RC%
)

rem Run the interactive payload in its own command processor so EXIT /B and
rem installer subroutine frames cannot return into or replay this launcher.
"%ComSpec%" /d /s /c ""%LATEST_INSTALLER%""
set "INSTALL_RC=%ERRORLEVEL%"
if not "%INSTALL_RC%"=="0" exit /b %INSTALL_RC%

echo HEXA INSTALL COMPLETE
exit /b 0
