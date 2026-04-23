$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvScripts = Join-Path $root ".venv\Scripts"

if (-not (Test-Path (Join-Path $venvScripts "python.exe"))) {
    throw "Python executable not found: $(Join-Path $venvScripts 'python.exe')"
}

function Get-WorkingRipgrepDir {
    $pathEntries = @($env:Path -split ";" | Where-Object { $_ })
    foreach ($entry in $pathEntries) {
        if ($entry -like "*WindowsApps*") {
            continue
        }
        $candidate = Join-Path $entry "rg.exe"
        if (Test-Path $candidate) {
            return $entry
        }
    }

    $codexCandidates = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Packages") -Directory -Filter "OpenAI.Codex_*" -ErrorAction SilentlyContinue
    foreach ($candidateRoot in $codexCandidates) {
        $candidate = Join-Path $candidateRoot.FullName "LocalCache\Local\OpenAI\Codex\bin\rg.exe"
        if (Test-Path $candidate) {
            return Split-Path -Parent $candidate
        }
    }

    foreach ($entry in $pathEntries) {
        if ($entry -notlike "*VS Code*\\bin") {
            continue
        }
        $codeRoot = Split-Path -Parent $entry
        $candidate = Get-ChildItem $codeRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName "resources\app\node_modules\@vscode\ripgrep\bin\rg.exe" } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($candidate) {
            return Split-Path -Parent $candidate
        }
    }

    return $null
}

$pathEntries = [System.Collections.Generic.List[string]]::new()
$pathEntries.Add($venvScripts)

$rgDir = Get-WorkingRipgrepDir
if ($rgDir) {
    $pathEntries.Add($rgDir)
}

foreach ($entry in ($env:Path -split ";" | Where-Object { $_ })) {
    if ($pathEntries.Contains($entry)) {
        continue
    }
    $pathEntries.Add($entry)
}

$env:Path = ($pathEntries -join ";")
Set-Location $root

Write-Host "Project root: $root"
Write-Host "Python: $(Get-Command python | Select-Object -ExpandProperty Source)"
if ($rgDir) {
    Write-Host "rg: $(Get-Command rg | Select-Object -ExpandProperty Source)"
} else {
    Write-Warning "No working rg.exe found outside WindowsApps."
}
