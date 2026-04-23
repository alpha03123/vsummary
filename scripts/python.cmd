@echo off
setlocal

set "ROOT=%~dp0.."
set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Python executable not found: %PYTHON_EXE% 1>&2
  exit /b 1
)

"%PYTHON_EXE%" %*
exit /b %ERRORLEVEL%
