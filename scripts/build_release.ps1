param(
    [ValidateSet("cpu", "gpu", "all")]
    [string]$Target = "all",
    [string]$CpuEnvName = "vsummary-pack-cpu",
    [string]$GpuEnvName = "vsummary-pack-gpu",
    [string]$Version = "",
    [string]$ReleaseBaseUrl = "https://github.com/alpha03123/vsummary/releases/latest/download",
    [string]$OutputRoot = "temp\packs",
    [switch]$ForceRuntime,
    [switch]$RefreshEnv,
    [switch]$SkipFullPackage,
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
$PacksRootPath = if ([System.IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot } else { Join-Path $RepoRoot $OutputRoot }
$OutputRootPath = Join-Path $PacksRootPath (Get-Date -Format "yyyy-MM-dd")
$BuildRootPath = Join-Path $OutputRootPath "_build"
$ManifestPath = Join-Path $OutputRootPath "vsummary-manifest.json"

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

function Copy-DirectoryContents {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Source directory not found: $Source"
    }

    Ensure-Directory -Path $Destination
    Get-ChildItem -LiteralPath $Source -Force | Copy-Item -Destination $Destination -Recurse -Force
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

function Test-AppFile {
    param([string]$Path)

    $normalized = $Path.Replace("\", "/")
    if ($normalized.StartsWith("src/")) {
        return $true
    }
    if ($normalized.StartsWith("assets/")) {
        return $true
    }
    if ($normalized.StartsWith("updater/")) {
        return $true
    }
    return @(
        ".env.example",
        "LICENSE",
        "README.md",
        "update.bat",
        "config/settings.toml.example"
    ) -contains $normalized
}

function Copy-AppFiles {
    param([string]$DestinationRoot)

    $files = & git -C $RepoRoot ls-files
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: git -C $RepoRoot ls-files"
    }

    foreach ($file in $files) {
        if (-not $file -or -not (Test-AppFile -Path $file)) {
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

    Copy-UpdaterEntrypoints -DestinationRoot $DestinationRoot
}

function Copy-UpdaterEntrypoints {
    param([string]$DestinationRoot)

    $entrypoints = @(
        "update.bat",
        "updater\__init__.py",
        "updater\update.py"
    )
    foreach ($entrypoint in $entrypoints) {
        $source = Join-Path $RepoRoot $entrypoint
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Updater entrypoint not found: $entrypoint"
        }
        $destination = Join-Path $DestinationRoot $entrypoint
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

function Resolve-ReleaseVersion {
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        return $Version
    }

    $tag = & git -C $RepoRoot describe --tags --exact-match 2>$null
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($tag)) {
        return $tag.Trim()
    }

    $commit = & git -C $RepoRoot rev-parse --short HEAD
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($commit)) {
        throw "Unable to resolve release version. Pass -Version explicitly."
    }
    return "dev-$($commit.Trim())"
}

function Get-ContentSignature {
    param([string[]]$RelativePaths)

    $stream = [System.IO.MemoryStream]::new()
    try {
        foreach ($relativePath in $RelativePaths) {
            $normalized = $relativePath.Replace("\", "/")
            $path = Join-Path $RepoRoot $relativePath
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Signature input not found: $relativePath"
            }

            $nameBytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
            $stream.Write($nameBytes, 0, $nameBytes.Length)
            $stream.WriteByte(0)
            $contentBytes = [System.IO.File]::ReadAllBytes($path)
            $stream.Write($contentBytes, 0, $contentBytes.Length)
            $stream.WriteByte(0)
        }

        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $hash = $sha.ComputeHash($stream.ToArray())
        }
        finally {
            $sha.Dispose()
        }
        return -join ($hash | ForEach-Object { $_.ToString("x2") })
    }
    finally {
        $stream.Dispose()
    }
}

function Get-RuntimeId {
    param(
        [string]$Kind,
        [string[]]$DependencyFiles
    )

    $signature = Get-ContentSignature -RelativePaths $DependencyFiles
    return "runtime-$Kind-$($signature.Substring(0, 12))"
}

function Get-FileSha256 {
    param([string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-AssetUrl {
    param([string]$FileName)

    if ([string]::IsNullOrWhiteSpace($ReleaseBaseUrl)) {
        return $FileName
    }

    return $ReleaseBaseUrl.TrimEnd("/") + "/" + $FileName
}

function Compress-Directory {
    param(
        [string]$SourceRoot,
        [string]$ArchivePath,
        [string]$SevenZipExe
    )

    Ensure-Directory -Path (Split-Path -Parent $ArchivePath)
    Remove-PathIfExists -Path $ArchivePath
    $archiveType = if ([System.IO.Path]::GetExtension($ArchivePath).ToLowerInvariant() -eq ".zip") { "-tzip" } else { "-t7z" }
    Push-Location $SourceRoot
    try {
        Invoke-External -FilePath $SevenZipExe -Arguments @("a", $archiveType, $ArchivePath, ".") -WorkingDirectory $SourceRoot
    }
    finally {
        Pop-Location
    }
}

function Expand-ArchiveWith7Zip {
    param(
        [string]$ArchivePath,
        [string]$DestinationRoot,
        [string]$SevenZipExe
    )

    Remove-PathIfExists -Path $DestinationRoot
    Ensure-Directory -Path $DestinationRoot
    Invoke-External -FilePath $SevenZipExe -Arguments @("x", $ArchivePath, "-o$DestinationRoot", "-y")
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
    $cpuRuntimeId = Get-RuntimeId -Kind "cpu" -DependencyFiles @("scripts\package\environment.cpu.yml")
    $gpuRuntimeId = Get-RuntimeId -Kind "gpu" -DependencyFiles @("scripts\package\environment.gpu.yml")

    return @{
        cpu = @{
            Kind = "cpu"
            EnvName = $CpuEnvName
            EnvFile = Join-Path $PackageConfigDir "environment.cpu.yml"
            EnvRelativePath = "scripts\package\environment.cpu.yml"
            SettingsTemplate = Join-Path $PackageConfigDir "settings.cpu.toml"
            RuntimeId = $cpuRuntimeId
            RuntimeArchive = Join-Path $OutputRootPath "vsummary-$cpuRuntimeId.zip"
            PackageRoot = Join-Path $BuildRootPath "full\cpu\vsummary-cpu"
            BuildRoot = Join-Path $BuildRootPath "runtime\cpu"
            FullArchive = Join-Path $OutputRootPath "vsummary-full-cpu-$Script:ReleaseVersion.7z"
        }
        gpu = @{
            Kind = "gpu"
            EnvName = $GpuEnvName
            EnvFile = Join-Path $PackageConfigDir "environment.gpu.yml"
            EnvRelativePath = "scripts\package\environment.gpu.yml"
            SettingsTemplate = Join-Path $PackageConfigDir "settings.gpu.toml"
            RuntimeId = $gpuRuntimeId
            RuntimeArchive = Join-Path $OutputRootPath "vsummary-$gpuRuntimeId.zip"
            PackageRoot = Join-Path $BuildRootPath "full\gpu\vsummary-gpu"
            BuildRoot = Join-Path $BuildRootPath "runtime\gpu"
            FullArchive = Join-Path $OutputRootPath "vsummary-full-gpu-$Script:ReleaseVersion.7z"
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

function Test-CondaEnvironmentExists {
    param(
        [string]$CondaExe,
        [string]$EnvName
    )

    $envs = & $CondaExe env list --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $CondaExe env list --json"
    }
    $matches = @($envs.envs) | Where-Object { $_ -match "\\$EnvName$" }
    return $matches.Count -gt 0
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

function Repair-GpuProviderWheel {
    param(
        [string]$CondaExe,
        [hashtable]$Variant
    )

    if ($Variant.Kind -ne "gpu") {
        return
    }

    Invoke-External -FilePath $CondaExe -Arguments @(
        "run",
        "-n",
        $Variant.EnvName,
        "python",
        "-m",
        "pip",
        "install",
        "--force-reinstall",
        "--no-deps",
        "onnxruntime-gpu>=1.20,<2"
    )
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
        [hashtable]$Variant,
        [string]$RuntimeArchive
    )

    $archivePath = Join-Path $Variant.BuildRoot "runtime.zip"
    $runtimeRoot = Join-Path $Variant.BuildRoot "runtime"

    Ensure-Directory -Path $Variant.BuildRoot
    Remove-PathIfExists -Path $archivePath
    Remove-PathIfExists -Path $runtimeRoot

    Invoke-External -FilePath $CondaPackExe -Arguments @("-n", $Variant.EnvName, "-o", $archivePath, "--format", "zip", "--force", "--ignore-missing-files")
    Invoke-External -FilePath $SevenZipExe -Arguments @("x", $archivePath, "-o$runtimeRoot", "-y")
    Invoke-CondaUnpack -RuntimeRoot $runtimeRoot
    Compress-Directory -SourceRoot $runtimeRoot -ArchivePath $RuntimeArchive -SevenZipExe $SevenZipExe
}

function Invoke-CondaUnpack {
    param([string]$RuntimeRoot)

    $condaUnpack = Join-Path $RuntimeRoot "Scripts\conda-unpack.exe"
    if (-not (Test-Path -LiteralPath $condaUnpack)) {
        return
    }

    Push-Location $RuntimeRoot
    try {
        Invoke-External -FilePath $condaUnpack -Arguments @() -WorkingDirectory $RuntimeRoot
    }
    finally {
        Pop-Location
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
from backend.api.http.app import create_app

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
    require({"faster-whisper", "fastembed", "onnxruntime", "pandas", "yt-dlp", "chaoxing-downloader"})
    forbid({"fastembed-gpu", "onnxruntime-gpu"})
elif kind == "gpu":
    require({
        "faster-whisper",
        "fastembed-gpu",
        "onnxruntime-gpu",
        "pandas",
        "nvidia-cublas-cu12",
        "nvidia-cuda-nvrtc-cu12",
        "nvidia-cuda-runtime-cu12",
        "nvidia-cudnn-cu12",
        "nvidia-cufft-cu12",
        "nvidia-curand-cu12",
        "yt-dlp",
        "chaoxing-downloader",
    })
    forbid({"fastembed"})
    import onnxruntime as ort

    providers = set(ort.get_available_providers())
    if "CUDAExecutionProvider" not in providers:
        raise SystemExit(
            "gpu package CUDAExecutionProvider unavailable; providers: "
            + ", ".join(sorted(providers))
        )
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

function Build-AppPackage {
    param([string]$SevenZipExe)

    $appRoot = Join-Path $BuildRootPath "app\vsummary-app"
    Remove-PathIfExists -Path $appRoot
    Ensure-Directory -Path $appRoot

    Copy-AppFiles -DestinationRoot $appRoot
    Copy-DirectoryIfExists -Source $FrontendDistDir -Destination (Join-Path $appRoot "src\frontend\dist")
    Set-Content -LiteralPath (Join-Path $appRoot "start.bat") -Value (Render-StartScript) -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $appRoot "VERSION") -Value $Script:ReleaseVersion -Encoding ASCII
    Write-AppFilesManifest -AppRoot $appRoot

    $archivePath = Join-Path $OutputRootPath "vsummary-app-$Script:ReleaseVersion.zip"
    Compress-Directory -SourceRoot $appRoot -ArchivePath $archivePath -SevenZipExe $SevenZipExe
    return @{
        Root = $appRoot
        Archive = $archivePath
    }
}

function Write-AppFilesManifest {
    param([string]$AppRoot)

    $manifestPath = Join-Path $AppRoot "updater\app-files.json"
    Ensure-Directory -Path (Split-Path -Parent $manifestPath)
    $rootPath = (Resolve-Path -LiteralPath $AppRoot).Path
    $files = Get-ChildItem -LiteralPath $AppRoot -Recurse -File -Force |
        ForEach-Object {
            $_.FullName.Substring($rootPath.Length + 1).Replace("\", "/")
        } |
        Sort-Object

    $payload = [ordered]@{ files = @($files) }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

function Ensure-RuntimeArchive {
    param(
        [hashtable]$Variant,
        [string]$CondaExe,
        [string]$CondaPackExe,
        [string]$SevenZipExe
    )

    if ((Test-Path -LiteralPath $Variant.RuntimeArchive -PathType Leaf) -and -not $ForceRuntime) {
        Write-Host "Reusing runtime $($Variant.RuntimeId)"
        return
    }

    $envExists = Test-CondaEnvironmentExists -CondaExe $CondaExe -EnvName $Variant.EnvName
    if ($RefreshEnv -or -not $envExists) {
        Write-Host "Preparing environment $($Variant.EnvName) for $($Variant.RuntimeId)"
        Ensure-CondaEnvironment -CondaExe $CondaExe -Variant $Variant
        Repair-GpuProviderWheel -CondaExe $CondaExe -Variant $Variant
    }
    else {
        Write-Host "Using existing environment $($Variant.EnvName) for $($Variant.RuntimeId)"
    }

    Write-Host "Packing runtime $($Variant.RuntimeId)"
    Pack-CondaEnvironment -CondaPackExe $CondaPackExe -SevenZipExe $SevenZipExe -Variant $Variant -RuntimeArchive $Variant.RuntimeArchive
}

function Build-FullPackage {
    param(
        [hashtable]$Variant,
        [string]$AppRoot,
        [string]$SevenZipExe
    )

    Write-Host "Building full package $($Variant.Kind)"
    Remove-PathIfExists -Path $Variant.PackageRoot
    Ensure-Directory -Path $Variant.PackageRoot

    Copy-DirectoryContents -Source $AppRoot -Destination $Variant.PackageRoot
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "videos")
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "workspace")
    Ensure-Directory -Path (Join-Path $Variant.PackageRoot "data")

    Copy-Item -LiteralPath $Variant.SettingsTemplate -Destination (Join-Path $Variant.PackageRoot "config\settings.toml") -Force
    Set-Content -LiteralPath (Join-Path $Variant.PackageRoot "RUNTIME") -Value $Variant.RuntimeId -Encoding ASCII
    Write-InstalledState -PackageRoot $Variant.PackageRoot -Variant $Variant
    Write-UpdaterConfig -PackageRoot $Variant.PackageRoot
    Expand-ArchiveWith7Zip -ArchivePath $Variant.RuntimeArchive -DestinationRoot (Join-Path $Variant.PackageRoot "runtime") -SevenZipExe $SevenZipExe

    Write-Host "Checking packaged dependency contract"
    Test-PackagedDependencyContract -PackageRoot $Variant.PackageRoot -Kind $Variant.Kind

    Write-Host "Running packaged runtime smoke check"
    Test-PackagedRuntime -PackageRoot $Variant.PackageRoot

    Compress-Directory -SourceRoot $Variant.PackageRoot -ArchivePath $Variant.FullArchive -SevenZipExe $SevenZipExe
}

function Write-InstalledState {
    param(
        [string]$PackageRoot,
        [hashtable]$Variant
    )

    $appFilesManifest = Join-Path $PackageRoot "updater\app-files.json"
    $appFiles = @()
    if (Test-Path -LiteralPath $appFilesManifest -PathType Leaf) {
        $appFiles = @((Get-Content -LiteralPath $appFilesManifest -Raw -Encoding UTF8 | ConvertFrom-Json).files)
    }

    $payload = [ordered]@{
        variant = $Variant.Kind
        app_version = $Script:ReleaseVersion
        runtime_id = $Variant.RuntimeId
        app_files = $appFiles
    }
    $installedPath = Join-Path $PackageRoot "updater\installed.json"
    Ensure-Directory -Path (Split-Path -Parent $installedPath)
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $installedPath -Encoding UTF8
}

function Write-UpdaterConfig {
    param([string]$PackageRoot)

    $manifestUrl = if ([string]::IsNullOrWhiteSpace($ReleaseBaseUrl)) {
        ""
    }
    else {
        $ReleaseBaseUrl.TrimEnd("/") + "/vsummary-manifest.json"
    }
    $payload = [ordered]@{
        manifest_url = $manifestUrl
    }
    $configPath = Join-Path $PackageRoot "updater\config.json"
    Ensure-Directory -Path (Split-Path -Parent $configPath)
    $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding UTF8
}

function New-AssetManifestEntry {
    param(
        [string]$ArchivePath,
        [string]$Role,
        [string]$Variant = "",
        [string]$RuntimeId = ""
    )

    $item = Get-Item -LiteralPath $ArchivePath
    $entry = [ordered]@{
        name = $item.Name
        url = Get-AssetUrl -FileName $item.Name
        sha256 = Get-FileSha256 -Path $item.FullName
        size = $item.Length
    }
    if ($Role -eq "app") {
        $entry.version = $Script:ReleaseVersion
    }
    if ($Role -eq "runtime") {
        $entry.id = $RuntimeId
    }
    return $entry
}

function Write-ReleaseManifest {
    param(
        [string]$AppArchive,
        [hashtable[]]$Variants
    )

    $runtime = [ordered]@{}
    $full = [ordered]@{}

    foreach ($variant in $Variants) {
        $runtime[$variant.Kind] = New-AssetManifestEntry `
            -ArchivePath $variant.RuntimeArchive `
            -Role "runtime" `
            -Variant $variant.Kind `
            -RuntimeId $variant.RuntimeId

        if (Test-Path -LiteralPath $variant.FullArchive -PathType Leaf) {
            $full[$variant.Kind] = New-AssetManifestEntry `
                -ArchivePath $variant.FullArchive `
                -Role "full" `
                -Variant $variant.Kind
        }
    }

    $manifest = [ordered]@{
        schema_version = 1
        version = $Script:ReleaseVersion
        app = New-AssetManifestEntry -ArchivePath $AppArchive -Role "app"
        runtime = $runtime
        full = $full
    }

    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
}

$CondaExe = Get-CondaExe
$CondaPackExe = Require-Command -Name "conda-pack"
$SevenZipExe = Require-Command -Name "7z"
$Script:ReleaseVersion = Resolve-ReleaseVersion

Ensure-Directory -Path $OutputRootPath

try {
    Ensure-FrontendDist

    $appPackage = Build-AppPackage -SevenZipExe $SevenZipExe
    $variants = @(Resolve-Targets)

    foreach ($variant in $variants) {
        Ensure-RuntimeArchive -Variant $variant -CondaExe $CondaExe -CondaPackExe $CondaPackExe -SevenZipExe $SevenZipExe

        if (-not $SkipFullPackage) {
            Build-FullPackage -Variant $variant -AppRoot $appPackage.Root -SevenZipExe $SevenZipExe
        }
    }

    Write-ReleaseManifest -AppArchive $appPackage.Archive -Variants $variants
}
finally {
    if (-not $KeepFrontendDist) {
        Remove-PathIfExists -Path $FrontendDistDir
    }
    if ($CleanNodeModules) {
        Remove-PathIfExists -Path $FrontendNodeModulesDir
    }
    if (-not $KeepBuildArtifacts) {
        Remove-PathIfExists -Path $BuildRootPath
    }
}
