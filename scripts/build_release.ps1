param(
    [ValidateSet("cpu", "gpu", "all")]
    [string]$Target = "all",
    [string]$CpuEnvName = "vsummary-pack-cpu",
    [string]$GpuEnvName = "vsummary-pack-gpu",
    [string]$OutputRoot = "temp\packs",
    [switch]$KeepFrontendDist,
    [switch]$CleanNodeModules,
    [switch]$KeepBuildArtifacts
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PackageConfigDir = Join-Path $RepoRoot "scripts\package"
$FrontendDir = Join-Path $RepoRoot "src\frontend"
$FrontendDistDir = Join-Path $FrontendDir "dist"
$FrontendNodeModulesDir = Join-Path $FrontendDir "node_modules"
$OutputRootPath = if ([System.IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot } else { Join-Path $RepoRoot $OutputRoot }

function Remove-PathIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Ensure-Directory {
    param([string]$Path)

    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Copy-DirectoryIfExists {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }

    Ensure-Directory -Path (Split-Path -Parent $Destination)
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Copy-GitTrackedFiles {
    param([string]$DestinationRoot)

    $files = & git -C $RepoRoot ls-files
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: git -C $RepoRoot ls-files"
    }

    foreach ($file in $files) {
        if (-not $file) {
            continue
        }

        $source = Join-Path $RepoRoot $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            continue
        }

        $destination = Join-Path $DestinationRoot $file
        Ensure-Directory -Path (Split-Path -Parent $destination)
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

function Require-Command {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        if ($Name -eq "7z") {
            $sevenZipExe = "C:\Program Files\7-Zip\7z.exe"
            if (Test-Path -LiteralPath $sevenZipExe) {
                return $sevenZipExe
            }
        }
        throw "Missing command: $Name"
    }
    return $command.Source
}

function Get-CondaExe {
    $candidates = @(
        $env:CONDA_EXE,
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "E:\Anaconda3\Scripts\conda.exe"
    ) | Where-Object { $_ }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "conda.exe not found."
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory = $RepoRoot
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        $joined = ($Arguments -join " ")
        throw "Command failed: $FilePath $joined"
    }
}

function Get-VariantTable {
    return @{
        cpu = @{
            Kind = "cpu"
            EnvName = $CpuEnvName
            EnvFile = Join-Path $PackageConfigDir "environment.cpu.yml"
            SettingsTemplate = Join-Path $PackageConfigDir "settings.cpu.toml"
            PackageRoot = Join-Path $OutputRootPath "vsummary-cpu"
            BuildRoot = Join-Path $OutputRootPath "_build\cpu"
        }
        gpu = @{
            Kind = "gpu"
            EnvName = $GpuEnvName
            EnvFile = Join-Path $PackageConfigDir "environment.gpu.yml"
            SettingsTemplate = Join-Path $PackageConfigDir "settings.gpu.toml"
            PackageRoot = Join-Path $OutputRootPath "vsummary-gpu"
            BuildRoot = Join-Path $OutputRootPath "_build\gpu"
        }
    }
}

function Resolve-Targets {
    $table = Get-VariantTable
    switch ($Target) {
        "cpu" { return @($table.cpu) }
        "gpu" { return @($table.gpu) }
        default { return @($table.cpu, $table.gpu) }
    }
}

function Get-EnvironmentNameFromFile {
    param([string]$EnvFile)

    $nameLine = Select-String -Path $EnvFile -Pattern '^name:\s*(.+)$' | Select-Object -First 1
    if ($null -eq $nameLine) {
        throw "Environment file missing name: $EnvFile"
    }
    return $nameLine.Matches[0].Groups[1].Value.Trim()
}

function Ensure-CondaEnvironment {
    param(
        [string]$CondaExe,
        [hashtable]$Variant
    )

    $envFileName = Get-EnvironmentNameFromFile -EnvFile $Variant.EnvFile
    $envs = & $CondaExe env list --json | ConvertFrom-Json
    $exists = @($envs.envs) | Where-Object { $_ -match "\\$($Variant.EnvName)$" }

    if ($exists.Count -gt 0 -and $Variant.EnvName -eq $envFileName) {
        Invoke-External -FilePath $CondaExe -Arguments @("env", "update", "-n", $Variant.EnvName, "-f", $Variant.EnvFile, "--prune")
        return
    }

    if ($exists.Count -eq 0 -and $Variant.EnvName -eq $envFileName) {
        Invoke-External -FilePath $CondaExe -Arguments @("env", "create", "-f", $Variant.EnvFile)
        return
    }

    if ($exists.Count -eq 0) {
        Invoke-External -FilePath $CondaExe -Arguments @("create", "-n", $Variant.EnvName, "python=3.11", "-y")
    }

    Invoke-External -FilePath $CondaExe -Arguments @("env", "update", "-n", $Variant.EnvName, "-f", $Variant.EnvFile, "--prune")
}

function Ensure-FrontendDist {
    $null = Require-Command -Name "npm"

    if (-not (Test-Path -LiteralPath (Join-Path $FrontendNodeModulesDir "vite"))) {
        Push-Location $FrontendDir
        try {
            Invoke-External -FilePath "npm" -Arguments @("ci") -WorkingDirectory $FrontendDir
        }
        finally {
            Pop-Location
        }
    }

    Push-Location $FrontendDir
    try {
        Invoke-External -FilePath "npm" -Arguments @("run", "build") -WorkingDirectory $FrontendDir
    }
    finally {
        Pop-Location
    }
}

function Render-StartScript {
    return Get-Content -LiteralPath (Join-Path $PackageConfigDir "start.bat.tpl") -Raw -Encoding UTF8
}

function Pack-CondaEnvironment {
    param(
        [string]$CondaPackExe,
        [string]$SevenZipExe,
        [hashtable]$Variant
    )

    $archivePath = Join-Path $Variant.BuildRoot "runtime.zip"
    $runtimeRoot = Join-Path $Variant.BuildRoot "runtime"

    Ensure-Directory -Path $Variant.BuildRoot
    Remove-PathIfExists -Path $archivePath
    Remove-PathIfExists -Path $runtimeRoot

    Invoke-External -FilePath $CondaPackExe -Arguments @("-n", $Variant.EnvName, "-o", $archivePath, "--format", "zip", "--force", "--ignore-missing-files")
    Invoke-External -FilePath $SevenZipExe -Arguments @("x", $archivePath, "-o$runtimeRoot", "-y")

    $condaUnpack = Join-Path $runtimeRoot "Scripts\conda-unpack.exe"
    if (Test-Path -LiteralPath $condaUnpack) {
        Push-Location $runtimeRoot
        try {
            Invoke-External -FilePath $condaUnpack -Arguments @() -WorkingDirectory $runtimeRoot
        }
        finally {
            Pop-Location
        }
    }
}

function Test-PackagedRuntime {
    param([string]$PackageRoot)

    $runtimePython = Join-Path $PackageRoot "runtime\python.exe"
    $smokeScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("vsummary-packaged-runtime-smoke-" + [System.Guid]::NewGuid().ToString("N") + ".py")
    $script = @'
from pathlib import Path
import os
import sys

root = Path(sys.argv[1])
os.chdir(root)
os.environ["HF_HOME"] = str(root / "data" / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(root / "data" / "huggingface" / "hub")
sys.path.insert(0, str(root / "src"))
from backend.api.app import create_app

class DummyContainer:
    def __init__(self, root_dir):
        self.root_dir = root_dir

app = create_app(container=DummyContainer(root))
print(app.title)
'@

    Set-Content -LiteralPath $smokeScriptPath -Value $script -Encoding UTF8
    try {
        Invoke-External -FilePath $runtimePython -Arguments @($smokeScriptPath, $PackageRoot)
    }
    finally {
        Remove-PathIfExists -Path $smokeScriptPath
    }
}

function Test-PackagedDependencyContract {
    param(
        [string]$PackageRoot,
        [string]$Kind
    )

    $runtimePython = Join-Path $PackageRoot "runtime\python.exe"
    $contractScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("vsummary-package-dependency-contract-" + [System.Guid]::NewGuid().ToString("N") + ".py")
    $script = @'
from importlib.metadata import distributions
import sys

kind = sys.argv[1]
packages = {dist.metadata["Name"].lower() for dist in distributions() if dist.metadata.get("Name")}
legacy_forbidden = {
    "torch",
    "sherpa-onnx",
    "playwright",
    "sentence-transformers",
    "llama-index-embeddings-huggingface",
}

def require(names):
    missing = sorted(name for name in names if name not in packages)
    if missing:
        raise SystemExit(f"{kind} package missing required dependencies: {', '.join(missing)}")

def forbid(names):
    conflicts = sorted(name for name in names if name in packages)
    if conflicts:
        raise SystemExit(f"{kind} package contains forbidden dependencies: {', '.join(conflicts)}")

forbid(legacy_forbidden)
if kind == "cpu":
    require({"faster-whisper", "fastembed", "onnxruntime", "yt-dlp", "chaoxing-downloader"})
    forbid({"fastembed-gpu", "onnxruntime-gpu"})
elif kind == "gpu":
    require({"faster-whisper", "fastembed-gpu", "onnxruntime-gpu", "yt-dlp", "chaoxing-downloader"})
    forbid({"fastembed"})
else:
    raise SystemExit(f"unsupported package kind: {kind}")

print(f"{kind} dependency contract ok")
'@

    Set-Content -LiteralPath $contractScriptPath -Value $script -Encoding UTF8
    try {
        Invoke-External -FilePath $runtimePython -Arguments @($contractScriptPath, $Kind)
    }
    finally {
        Remove-PathIfExists -Path $contractScriptPath
    }
}

function Build-Package {
    param(
        [hashtable]$Variant,
        [string]$CondaExe,
        [string]$CondaPackExe,
        [string]$SevenZipExe
    )

    Write-Host "Preparing environment $($Variant.EnvName)"
    Ensure-CondaEnvironment -CondaExe $CondaExe -Variant $Variant

    Write-Host "Packing environment $($Variant.EnvName)"
    Pack-CondaEnvironment -CondaPackExe $CondaPackExe -SevenZipExe $SevenZipExe -Variant $Variant

    Remove-PathIfExists -Path $Variant.PackageRoot
    Ensure-Directory -Path $Variant.PackageRoot
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "videos")
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "workspace")
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "data")

    Copy-GitTrackedFiles -DestinationRoot $Variant.PackageRoot
    Copy-Item -LiteralPath $Variant.SettingsTemplate -Destination (Join-Path $Variant.PackageRoot "config\settings.toml") -Force
    Copy-DirectoryIfExists -Source $FrontendDistDir -Destination (Join-Path $Variant.PackageRoot "src\frontend\dist")

    Copy-DirectoryIfExists -Source (Join-Path $Variant.BuildRoot "runtime") -Destination (Join-Path $Variant.PackageRoot "runtime")
    Set-Content -LiteralPath (Join-Path $Variant.PackageRoot "start.bat") -Value (Render-StartScript) -Encoding ASCII

    Write-Host "Checking packaged dependency contract"
    Test-PackagedDependencyContract -PackageRoot $Variant.PackageRoot -Kind $Variant.Kind

    Write-Host "Running packaged runtime smoke check"
    Test-PackagedRuntime -PackageRoot $Variant.PackageRoot
}

$CondaExe = Get-CondaExe
$CondaPackExe = Require-Command -Name "conda-pack"
$SevenZipExe = Require-Command -Name "7z"

Ensure-Directory -Path $OutputRootPath

try {
    Ensure-FrontendDist

    foreach ($variant in Resolve-Targets) {
        Build-Package -Variant $variant -CondaExe $CondaExe -CondaPackExe $CondaPackExe -SevenZipExe $SevenZipExe
    }
}
finally {
    if (-not $KeepFrontendDist) {
        Remove-PathIfExists -Path $FrontendDistDir
    }
    if ($CleanNodeModules) {
        Remove-PathIfExists -Path $FrontendNodeModulesDir
    }
    if (-not $KeepBuildArtifacts) {
        Remove-PathIfExists -Path (Join-Path $OutputRootPath "_build")
    }
}
