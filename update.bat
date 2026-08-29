@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

set "PYTHON=%ROOT%\runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" "%ROOT%\updater\update.py" --root "%ROOT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="3" (
    call "%ROOT%\updater\apply-pending-delta.bat"
    set "EXIT_CODE=%ERRORLEVEL%"
)
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
