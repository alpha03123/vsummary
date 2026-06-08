@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "FRONTEND=%ROOT%\src\frontend"
set "ENV_NAME=vsummary"
set "CONDA_BAT=%CONDA_EXE%"
set "ENV_PATH="
set "PYTHON="

if not defined CONDA_BAT (
    if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
)
if not defined CONDA_BAT (
    if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\anaconda3\condabin\conda.bat"
)
if not defined CONDA_BAT (
    if exist "E:\Anaconda3\condabin\conda.bat" set "CONDA_BAT=E:\Anaconda3\condabin\conda.bat"
)

if not defined CONDA_BAT (
    echo [error] conda not found.
    echo Please install Miniconda or Anaconda first - see README.md.
    pause
    exit /b 1
)

for /f "tokens=1,*" %%A in ('call "%CONDA_BAT%" env list ^| findstr /R /C:"^[* ]*%ENV_NAME% "') do (
    if /I "%%A"=="*" (
        set "ENV_PATH=%%B"
    ) else if /I "%%A"=="%ENV_NAME%" (
        set "ENV_PATH=%%B"
    )
)

if not defined ENV_PATH (
    echo [error] Conda environment "%ENV_NAME%" not found.
    echo Please run: conda env create -f environment.yml
    pause
    exit /b 1
)

set "PYTHON=%ENV_PATH%\python.exe"
if not exist "%PYTHON%" (
    echo [error] Python executable not found in "%ENV_PATH%".
    echo Please recreate the Conda environment: conda env create -f environment.yml
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [error] npm not found. Install Node.js 18+ first - see README.md.
    pause
    exit /b 1
)

start "vsummary-backend" cmd /k set "PATH=%ENV_PATH%;%ENV_PATH%\Library\bin;%ENV_PATH%\Scripts;%PATH%" ^&^& cd /d "%ROOT%\src" ^&^& "%PYTHON%" -m backend.api.server --host 127.0.0.1 --port 8001
start "vsummary-frontend" cmd /k cd /d "%FRONTEND%" ^&^& npm run dev

echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:4173
