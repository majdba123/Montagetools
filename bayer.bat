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

call "%LATEST_INSTALLER%"
set "INSTALL_RC=%ERRORLEVEL%"
if not "%INSTALL_RC%"=="0" exit /b %INSTALL_RC%

echo HEXA INSTALL COMPLETE
exit /b 0
