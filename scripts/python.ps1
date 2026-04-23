$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

& $pythonExe @args
exit $LASTEXITCODE
