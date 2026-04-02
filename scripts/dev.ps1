$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root "src\\frontend"
$pythonExe = Join-Path $root ".venv\\Scripts\\python.exe"
$backendPort = 8001

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$backendCommand = "Set-Location '$root'; & '$pythonExe' -m uvicorn backend.api.app:app --host 127.0.0.1 --port $backendPort --reload --app-dir src"
$frontendCommand = "Set-Location '$frontendDir'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand | Out-Null
