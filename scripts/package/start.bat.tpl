@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"
if not exist "%ROOT%\.env" copy /y "%ROOT%\.env.example" "%ROOT%\.env" >nul
set "HF_HOME=%ROOT%\data\huggingface"
set "HUGGINGFACE_HUB_CACHE=%ROOT%\data\huggingface\hub"
set "PATH=%ROOT%\runtime;%ROOT%\runtime\Library\bin;%ROOT%\runtime\Scripts;%PATH%"
set "NVIDIA_BIN_ROOT=%ROOT%\runtime\Lib\site-packages\nvidia"
if exist "%NVIDIA_BIN_ROOT%" for /d %%D in ("%NVIDIA_BIN_ROOT%\*") do if exist "%%~fD\bin" set "PATH=%%~fD\bin;!PATH!"
set "PYTHONPATH=%ROOT%\src"

start "" http://127.0.0.1:4173
call "%ROOT%\runtime\python.exe" -m backend.api.server --host 127.0.0.1 --port 4173
if errorlevel 1 pause
