@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "FRONTEND=%ROOT%\src\frontend"

if not exist "%PYTHON%" (
    echo [error] .venv\Scripts\python.exe not found.
    echo Please set up the Python venv first - see README.md.
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [error] npm not found. Install Node.js 18+ first - see README.md.
    pause
    exit /b 1
)

start "vsummary-backend" cmd /k "cd /d "%ROOT%" && "%PYTHON%" -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8001 --app-dir src"
start "vsummary-frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:4173
