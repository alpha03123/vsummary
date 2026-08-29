$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\..\..\scripts\build_release.ps1")

Describe "Build-DeltaPackage" {
    It "returns only one delta object after invoking 7z" {
        $fixtureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("vsummary-delta-" + [guid]::NewGuid().ToString("N"))
        $previousRoot = Join-Path $fixtureRoot "previous"
        $currentRoot = Join-Path $fixtureRoot "current"
        $previousArchive = Join-Path $fixtureRoot "previous.7z"
        $appArchive = Join-Path $fixtureRoot "vsummary-app-v2.zip"
        $fullArchive = Join-Path $fixtureRoot "vsummary-full-cpu-v2.7z"
        $originalBuildRoot = $BuildRootPath
        $originalOutputRoot = $OutputRootPath
        $originalReleaseVersion = $Script:ReleaseVersion
        $originalManifestPath = $ManifestPath

        try {
            New-Item -ItemType Directory -Path (Join-Path $previousRoot "src") -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $currentRoot "src") -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $previousRoot "src\changed.txt") -Value "old" -NoNewline
            Set-Content -LiteralPath (Join-Path $previousRoot "src\deleted.txt") -Value "deleted" -NoNewline
            Set-Content -LiteralPath (Join-Path $currentRoot "src\changed.txt") -Value "new" -NoNewline
            Set-Content -LiteralPath (Join-Path $currentRoot "src\added.txt") -Value "added" -NoNewline
            & "C:\Program Files\7-Zip\7z.exe" a -t7z $previousArchive (Join-Path $previousRoot "*") | Out-Null
            Set-Content -LiteralPath $appArchive -Value "app" -NoNewline
            Set-Content -LiteralPath $fullArchive -Value "full" -NoNewline

            $BuildRootPath = Join-Path $fixtureRoot "_build"
            $OutputRootPath = $fixtureRoot
            $Script:ReleaseVersion = "v2"
            $Script:ManifestPath = Join-Path $fixtureRoot "vsummary-manifest.json"
            $variant = @{
                Kind = "cpu"
                PackageRoot = $currentRoot
                FullArchive = $fullArchive
                RequirementFiles = @("requirements.txt", "requirements.cpu.txt")
                PythonRequirement = ">=3.11,<3.12"
            }

            $result = @(Build-DeltaPackage -Variant $variant -PreviousArchive $previousArchive -PreviousVersion "v1" -SevenZipExe "C:\Program Files\7-Zip\7z.exe")

            $result.Count | Should Be 1
            ($result[0] -is [hashtable]) | Should Be $true
            $result[0].From | Should Be "v1"
            $result[0].To | Should Be "v2"
            (Test-Path -LiteralPath $result[0].Archive) | Should Be $true

            Write-ReleaseManifest -AppArchive $appArchive -Variants @($variant) -Deltas @($result[0])
            $manifest = Get-Content -LiteralPath $Script:ManifestPath -Raw | ConvertFrom-Json
            $manifest.deltas.cpu.v1.to | Should Be "v2"
        }
        finally {
            $BuildRootPath = $originalBuildRoot
            $OutputRootPath = $originalOutputRoot
            $Script:ReleaseVersion = $originalReleaseVersion
            $Script:ManifestPath = $originalManifestPath
            Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
