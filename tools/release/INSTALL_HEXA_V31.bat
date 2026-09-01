@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

title HEXA Video Builder V31.0.25 Installer
cls
echo ============================================================
echo HEXA VIDEO BUILDER V31.0.25 INSTALLER
echo ============================================================
echo Initializing installer. Please keep this window open...
echo.

set "VERSION=31.0.25"
set "ROOT=%~dp0"
set "INSTALLER=%ROOT%tools\install_v31.py"
set "LOGDIR=%LOCALAPPDATA%\HEXA\VideoBuilderV31\install_logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
set "BOOTLOG=%LOGDIR%\BOOTSTRAP_LATEST.log"
set "INSTALLMARKER=%LOGDIR%\CURRENT_INSTALLER_LOG.txt"
if exist "%INSTALLMARKER%" del /q "%INSTALLMARKER%" >nul 2>&1
>"%BOOTLOG%" echo HEXA VIDEO BUILDER V31.0.25 INSTALL BOOTSTRAP
>>"%BOOTLOG%" echo ROOT=%ROOT%
>>"%BOOTLOG%" echo INSTALLER=%INSTALLER%
>>"%BOOTLOG%" echo STARTED=%DATE% %TIME%

set "HEXA_V31_INSTALL_LOG_MARKER=%INSTALLMARKER%"
set "RC=0"
set "PYEXE="
set "PYSOURCE="
set "PYPROBE_EXE="

if not exist "%INSTALLER%" (
  >>"%BOOTLOG%" echo FATAL=INSTALLER_NOT_FOUND
  set "RC=105"
  goto FAIL
)

rem Prefer existing HEXA runtimes, then fall back to normal Windows Python discovery.
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV31\runtime\.venv\Scripts\python.exe" "HEXA_V31"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV27\runtime\.venv\Scripts\python.exe" "HEXA_V27"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV26\runtime\.venv\Scripts\python.exe" "HEXA_V26"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV25\runtime\.venv\Scripts\python.exe" "HEXA_V25"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV24\runtime\.venv\Scripts\python.exe" "HEXA_V24"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV23\runtime\.venv\Scripts\python.exe" "HEXA_V23"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV20\runtime\.venv\Scripts\python.exe" "HEXA_V20"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV17\runtime\.venv\Scripts\python.exe" "HEXA_V17"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV16\runtime\.venv\Scripts\python.exe" "HEXA_V16"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV12\runtime\.venv\Scripts\python.exe" "HEXA_V12"
call :TRY_PY "%LOCALAPPDATA%\HEXA\VideoBuilderV8\runtime\.venv\Scripts\python.exe" "HEXA_V8"

if not defined PYEXE (
  for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYEXE call :TRY_PY "%%~fP" "PATH"
)

if not defined PYEXE (
  for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYEXE call :TRY_PY "%%P" "PY_LAUNCHER"
)

if not defined PYEXE (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do if not defined PYEXE call :TRY_PY "%%~fD\python.exe" "LOCALAPPDATA_PROGRAMS"
)
if not defined PYEXE (
  for /d %%D in ("%ProgramFiles%\Python*") do if not defined PYEXE call :TRY_PY "%%~fD\python.exe" "PROGRAMFILES"
)
if not defined PYEXE if exist "%ProgramFiles(x86)%" (
  for /d %%D in ("%ProgramFiles(x86)%\Python*") do if not defined PYEXE call :TRY_PY "%%~fD\python.exe" "PROGRAMFILES_X86"
)

if not defined PYEXE (
  >>"%BOOTLOG%" echo FATAL=NO_EXECUTABLE_PYTHON_RUNTIME
  set "RC=106"
  goto FAIL
)

>>"%BOOTLOG%" echo PYTHON=%PYEXE%
>>"%BOOTLOG%" echo PYTHON_SOURCE=%PYSOURCE%

echo Python runtime: %PYEXE%
echo Installing HEXA V31.0.25. Progress will appear below.
echo This can take several minutes while dependencies and media tools are checked.
echo ------------------------------------------------------------
echo.

"%PYEXE%" "%INSTALLER%"
set "RC=%ERRORLEVEL%"
>>"%BOOTLOG%" echo PYTHON_EXIT_CODE=%RC%

if not "%RC%"=="0" goto FAIL

cls
echo ============================================================
echo HEXA VIDEO BUILDER V31.0.25
echo INSTALLATION COMPLETED SUCCESSFULLY
echo ============================================================
echo.
echo Open Adobe Premiere Pro 2022 now.
echo.
echo Build the same test Scene Package and export the MP4 for human review.
echo.
echo Press any key to close...
pause >nul
exit /b 0

:TRY_PY
if defined PYEXE exit /b 0
set "CAND=%~1"
set "CSOURCE=%~2"
if not defined CAND exit /b 0
if not exist "%CAND%" exit /b 0
set "PROBEFILE=%TEMP%\hexa_v31_pyprobe_%RANDOM%_%RANDOM%.txt"
"%CAND%" -c "import sys;print(sys.executable);print(sys.version.split()[0])" >"%PROBEFILE%" 2>&1
set "PRC=!ERRORLEVEL!"
if not "!PRC!"=="0" (
  >>"%BOOTLOG%" echo SKIP_PYTHON_SOURCE=!CSOURCE!
  >>"%BOOTLOG%" echo SKIP_PYTHON_PATH=!CAND!
  >>"%BOOTLOG%" echo SKIP_PYTHON_EXIT=!PRC!
  type "!PROBEFILE!" >>"%BOOTLOG%"
  del /q "!PROBEFILE!" >nul 2>&1
  exit /b 0
)
set "PYEXE=!CAND!"
set "PYSOURCE=!CSOURCE!"
for /f "usebackq delims=" %%Q in ("!PROBEFILE!") do if not defined PYPROBE_EXE set "PYPROBE_EXE=%%Q"
>>"%BOOTLOG%" echo ACCEPT_PYTHON_SOURCE=!PYSOURCE!
>>"%BOOTLOG%" echo ACCEPT_PYTHON_PATH=!PYEXE!
>>"%BOOTLOG%" echo ACCEPT_PYTHON_REPORTED_EXE=!PYPROBE_EXE!
del /q "!PROBEFILE!" >nul 2>&1
exit /b 0

:FAIL
echo.
echo ============================================================
echo HEXA VIDEO BUILDER V31.0.25 INSTALLATION FAILED
echo ============================================================
echo Exit code: %RC%
echo Bootstrap log: %BOOTLOG%
if exist "%INSTALLMARKER%" (
  set /p LASTLOG=<"%INSTALLMARKER%"
  if defined LASTLOG echo Installer log:  !LASTLOG!
)
echo.
echo The success message was not printed because installation did not complete.
echo # Press any key to close...
pause >nul
exit /b %RC%
