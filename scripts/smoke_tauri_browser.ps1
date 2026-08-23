[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $repoRoot 'desktop'
$pythonCommand = Get-Command python -ErrorAction Stop
$cargoBin = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin'
if (-not (Get-Command cargo -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath (Join-Path $cargoBin 'cargo.exe'))) {
    $env:Path = "$cargoBin;$env:Path"
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { throw 'Cargo is required for the Smarti Browser smoke.' }

$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) ("smarti-browser-smoke-" + [Guid]::NewGuid().ToString('N'))
$resultPath = Join-Path $smokeRoot 'result.json'
$dataPath = Join-Path $smokeRoot 'data'
New-Item -ItemType Directory -Path $dataPath -Force | Out-Null

$previousProjectRoot = $env:SMARTI_PROJECT_ROOT
$previousPython = $env:SMARTI_PYTHON
$previousData = $env:SMARTI_DATA_DIR
$previousSmoke = $env:SMARTI_BROWSER_SMOKE_FILE
$env:SMARTI_PROJECT_ROOT = $repoRoot
$env:SMARTI_PYTHON = $pythonCommand.Source
$env:SMARTI_DATA_DIR = $dataPath
$env:SMARTI_BROWSER_SMOKE_FILE = $resultPath

Push-Location $desktopRoot
try {
    npm run tauri dev
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) { throw 'The Tauri browser smoke did not write a result.' }
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if (-not $result.ok) { throw "Smarti Browser foundation smoke failed: $($result | ConvertTo-Json -Depth 6 -Compress)" }
    $result | ConvertTo-Json -Depth 6
} finally {
    Pop-Location
    $env:SMARTI_PROJECT_ROOT = $previousProjectRoot
    $env:SMARTI_PYTHON = $previousPython
    $env:SMARTI_DATA_DIR = $previousData
    $env:SMARTI_BROWSER_SMOKE_FILE = $previousSmoke
    $resolvedSmokeRoot = [IO.Path]::GetFullPath($smokeRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedSmokeRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedSmokeRoot)) {
        Remove-Item -LiteralPath $resolvedSmokeRoot -Recurse -Force
    }
}
