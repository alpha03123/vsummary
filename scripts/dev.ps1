$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$frontendNodeModules = Join-Path $root 'frontend\node_modules'

if (-not (Test-Path $python)) {
    throw 'Missing .venv\Scripts\python.exe. Create the project virtual environment first.'
}

if (-not (Test-Path $frontendNodeModules)) {
    throw 'Missing frontend\node_modules. Run npm install in the frontend directory first.'
}

$backend = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'presentation.api:app', '--app-dir', 'src', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $root `
    -PassThru

$frontend = Start-Process -FilePath 'npm.cmd' `
    -ArgumentList 'run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173' `
    -WorkingDirectory (Join-Path $root 'frontend') `
    -PassThru

Write-Host ''
Write-Host 'Backend  : http://127.0.0.1:8000'
Write-Host 'Frontend : http://127.0.0.1:4173'
Write-Host ''
Write-Host 'Press Ctrl+C to stop both processes.'

try {
    Wait-Process -Id $backend.Id, $frontend.Id
}
finally {
    foreach ($process in @($backend, $frontend)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}
