@echo off
setlocal
cd /d "%~dp0.."
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "(Get-Content $env:LOCALAPPDATA\HEXA\VideoBuilderV31\runtime_config.json -Raw|ConvertFrom-Json).python_exe"`) do set "PYEXE=%%P"
if not defined PYEXE exit /b 2
if "%~1"=="" (set "PACKAGE=HEXA_V11_REAL_PACKAGE.zip") else (set "PACKAGE=%~1")
if "%~2"=="" (set "VOICE=HEXA_V11_REAL_VOICE.mp3") else (set "VOICE=%~2")
"%PYEXE%" tools\iterate_creative_v31.py --package "%PACKAGE%" --voice "%VOICE%"
exit /b %ERRORLEVEL%
