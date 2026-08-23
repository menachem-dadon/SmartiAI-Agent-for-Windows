[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$desktopRoot = Join-Path $repoRoot 'desktop'
$coreEntrypoint = Join-Path $repoRoot 'smarti_core_service.py'

if (-not (Test-Path -LiteralPath $coreEntrypoint -PathType Leaf)) {
    throw "Smarti Core entrypoint is missing: $coreEntrypoint"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw 'Python was not found in PATH. Install Python 3.11+ or activate the project virtual environment.'
}

$cargoCommand = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $cargoCommand) {
    $userCargo = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin\cargo.exe'
    if (Test-Path -LiteralPath $userCargo -PathType Leaf) {
        $env:Path = "$(Split-Path -Parent $userCargo);$env:Path"
    } else {
        throw 'Rust/Cargo is missing. Install Rustup and the Microsoft C++ Build Tools required by Tauri 2, then run this command again.'
    }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw 'Node.js/npm is missing. Install the repository-supported Node.js release and run this command again.'
}

$env:SMARTI_PROJECT_ROOT = $repoRoot
$env:SMARTI_PYTHON = $pythonCommand.Source
$env:RUST_BACKTRACE = '1'

Push-Location $desktopRoot
try {
    if (-not $SkipInstall) {
        Write-Host 'Preparing locked frontend dependencies...'
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
    }
    Write-Host 'Starting SmartiAI Tauri and its supervised Python Core...'
    npm run tauri dev
    if ($LASTEXITCODE -ne 0) { throw "Tauri development app exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
