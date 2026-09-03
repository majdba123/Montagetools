@echo off
setlocal EnableExtensions

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
if errorlevel 1 exit /b %ERRORLEVEL%

call :CHECK_RELEASE
if not "%RELEASE_READY%"=="1" (
  echo ERROR: dist\latest is still not certified for SOURCE_COMMIT=%SOURCE_COMMIT% after rebuild.
  exit /b 27
)

:RELEASE_READY
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

:CHECK_RELEASE
set "RELEASE_READY=0"
set "RELEASE_COMMIT="
if not exist "%LATEST%\" exit /b 0
if not exist "%LATEST_INSTALLER%" exit /b 0
if not exist "%LATEST%\extension\py\hexa_v31\__init__.py" exit /b 0
if not exist "%LATEST%\tools\install_v31.py" exit /b 0
if not exist "%LATEST%\release_identity.json" exit /b 0
for /f "delims=" %%S in ('%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoLogo -NoProfile -NonInteractive -Command "(Get-Content -LiteralPath '%LATEST%\release_identity.json' -Raw | ConvertFrom-Json).source_commit"') do if not defined RELEASE_COMMIT set "RELEASE_COMMIT=%%S"
if /i "%SOURCE_COMMIT%"=="%RELEASE_COMMIT%" set "RELEASE_READY=1"
exit /b 0

:REBUILD_RELEASE
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
