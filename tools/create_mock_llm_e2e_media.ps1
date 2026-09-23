#Requires -PSEdition Core
#Requires -Version 7.0
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$SubtitlePath = (Join-Path $PSScriptRoot '..\tests\fixtures\e2e\pr-e2e.srt')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$output = [IO.Path]::GetFullPath($OutputPath)
$subtitle = [IO.Path]::GetFullPath($SubtitlePath)
if (-not (Test-Path -LiteralPath $subtitle -PathType Leaf)) {
    throw "E2E subtitle fixture does not exist: $subtitle"
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $output) | Out-Null
& ffmpeg -y -f lavfi -i 'color=c=0x164E63:s=640x360:d=6:r=25' -f lavfi -i 'anullsrc=r=48000:cl=mono' -i $subtitle -shortest -map 0:v:0 -map 1:a:0 -map 2:0 -c:v libx264 -pix_fmt yuv420p -c:a aac -c:s mov_text -metadata:s:s:0 language=zho -movflags +faststart $output
if ($LASTEXITCODE -ne 0) {
    throw "ffmpeg failed while creating CI E2E media."
}
