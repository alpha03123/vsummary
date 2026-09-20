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
    for /f "delims=" %%I in ('where conda.bat 2^>nul') do set "CONDA_BAT=%%I"
)
if not defined CONDA_BAT (
    if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"
)
if not defined CONDA_BAT (
    if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\anaconda3\condabin\conda.bat"
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
    echo Please create one source environment first:
    echo   NVIDIA: conda env create -f environment.yml
    echo   AMD CPU/Vulkan: conda env create -f environment.cpu.yml
    pause
    exit /b 1
)

set "PYTHON=%ENV_PATH%\python.exe"
set "MYSQL_RUNTIME="
set "MYSQL_RUNTIME_SOURCE="
set "VSUMMARY_DATA=%LOCALAPPDATA%\VSummary"
set "HF_HOME=%VSUMMARY_DATA%\cache\huggingface"
set "HUGGINGFACE_HUB_CACHE=%VSUMMARY_DATA%\cache\huggingface\hub"

rem Source checkout: honor an explicit runtime first, then discover an installed MySQL.
if defined VSUMMARY_MYSQL_HOME (
    set "MYSQL_RUNTIME=%VSUMMARY_MYSQL_HOME%"
    set "MYSQL_RUNTIME_SOURCE=VSUMMARY_MYSQL_HOME"
) else (
    for /f "delims=" %%I in ('where mysqld.exe 2^>nul') do (
        if not defined MYSQL_RUNTIME (
            for %%J in ("%%~dpI..") do (
                if exist "%%~fJ\bin\mysqld.exe" if exist "%%~fJ\share" (
                    set "MYSQL_RUNTIME=%%~fJ"
                    set "MYSQL_RUNTIME_SOURCE=PATH"
                )
            )
        )
    )
    if not defined MYSQL_RUNTIME if defined ProgramFiles (
        for /d %%D in ("%ProgramFiles%\MySQL\MySQL Server *") do (
            if not defined MYSQL_RUNTIME if exist "%%~fD\bin\mysqld.exe" if exist "%%~fD\share" (
                set "MYSQL_RUNTIME=%%~fD"
                set "MYSQL_RUNTIME_SOURCE=%ProgramFiles%"
            )
        )
    )
)
if not exist "%PYTHON%" (
    echo [error] Python executable not found in "%ENV_PATH%".
    echo Please recreate the source environment selected for this machine.
    pause
    exit /b 1
)
if not defined MYSQL_RUNTIME (
    echo [error] MySQL runtime was not found in PATH or %%ProgramFiles%%\MySQL.
    echo Install MySQL 8.4 or set VSUMMARY_MYSQL_HOME to its installation directory.
    pause
    exit /b 1
)
if not exist "%MYSQL_RUNTIME%\bin\mysqld.exe" if defined VSUMMARY_MYSQL_HOME (
    echo [error] VSUMMARY_MYSQL_HOME does not contain bin\mysqld.exe: %MYSQL_RUNTIME%
    pause
    exit /b 1
)
if not exist "%MYSQL_RUNTIME%\bin\mysqld.exe" (
    echo [error] discovered MySQL runtime is incomplete: %MYSQL_RUNTIME%
    pause
    exit /b 1
)
if not exist "%MYSQL_RUNTIME%\share" (
    echo [error] MySQL runtime is missing its share directory: %MYSQL_RUNTIME%
    pause
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [error] npm not found. Install Node.js 18+ first - see README.md.
    pause
    exit /b 1
)

start "vsummary-backend" cmd /k set "PATH=%ENV_PATH%;%ENV_PATH%\Library\bin;%ENV_PATH%\Scripts;%PATH%" ^&^& cd /d "%ROOT%\src" ^&^& "%PYTHON%" -m backend.api.http.server --host 127.0.0.1 --port 8001 --managed-mysql-home "%MYSQL_RUNTIME%"
start "vsummary-frontend" cmd /k cd /d "%FRONTEND%" ^&^& npm run dev

echo MySQL runtime: %MYSQL_RUNTIME% ^(%MYSQL_RUNTIME_SOURCE%^)
echo Backend:  http://127.0.0.1:8001
echo Frontend: http://127.0.0.1:4173
