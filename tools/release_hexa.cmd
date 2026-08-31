@echo off
setlocal
cd /d "%~dp0.."
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "(Get-Content $env:LOCALAPPDATA\HEXA\VideoBuilderV31\runtime_config.json -Raw|ConvertFrom-Json).python_exe"`) do set "PYEXE=%%P"
if not defined PYEXE exit /b 2
"%PYEXE%" tools\release_supervisor.py --package HEXA_V11_REAL_PACKAGE.zip --voice HEXA_V11_REAL_VOICE.mp3 --adopt-pid 8452
exit /b %ERRORLEVEL%
