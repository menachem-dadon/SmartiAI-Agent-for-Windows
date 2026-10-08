[CmdletBinding()]
param([switch]$BuildOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$qaRoot = Join-Path $taskRoot '.codex-local\startup'
New-Item -ItemType Directory -Path $qaRoot -Force | Out-Null
$copyRoot = Join-Path ([IO.Path]::GetTempPath()) ('smarti-startup-' + [Guid]::NewGuid().ToString('N'))
$qaApp = Join-Path $copyRoot 'app'
$source = Join-Path $taskRoot 'desktop\src-tauri'
New-Item -ItemType Directory -Path $qaApp -Force | Out-Null
foreach ($part in @('src','icons','capabilities','build.rs','Cargo.lock','Cargo.toml')) {
    Copy-Item -LiteralPath (Join-Path $source $part) -Destination $qaApp -Recurse -Force
}
$front = Join-Path $copyRoot 'frontend'
New-Item -ItemType Directory -Path $front -Force | Out-Null
Copy-Item -Path (Join-Path $taskRoot 'desktop\dist\*') -Destination $front -Recurse -Force
$manifest = (Get-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Raw).Replace('name = "smarti_desktop_lib"','name = "smarti_startup_qa_lib"').Replace('[features]', "[features]`ncustom-protocol = [`"tauri/custom-protocol`"]")
$manifest += "`n[[bin]]`nname = `"smarti-startup-qa`"`npath = `"src/main.rs`"`n"
Set-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Value $manifest -Encoding utf8
Set-Content -LiteralPath (Join-Path $qaApp 'src\main.rs') -Value ((Get-Content -LiteralPath (Join-Path $source 'src\main.rs') -Raw).Replace('smarti_desktop_lib::run()', 'smarti_startup_qa_lib::run()')) -Encoding utf8
$config = Get-Content -LiteralPath (Join-Path $source 'tauri.conf.json') -Raw | ConvertFrom-Json
$config.identifier = 'ai.smarti.startupqa'
$config.app.windows[0].title = 'SmartiAI - Startup QA'
$config.build.frontendDist = '../frontend'
$config.bundle.active = $false
$config.bundle.PSObject.Properties.Remove('resources')
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $qaApp 'tauri.conf.json') -Encoding utf8
# Reuse dependency artifacts; the QA library/executable have their own names.
$target = Join-Path $source 'target'
$previousTarget = $env:CARGO_TARGET_DIR
try {
    $env:CARGO_TARGET_DIR = $target
    & cargo build --locked --manifest-path (Join-Path $qaApp 'Cargo.toml') --bin smarti-startup-qa --features custom-protocol
    if ($LASTEXITCODE -ne 0) { throw 'Startup QA build failed.' }
} finally { $env:CARGO_TARGET_DIR = $previousTarget }
$exe = Join-Path $target 'debug\smarti-startup-qa.exe'
@{ executable=$exe; python=(Get-Command python).Source; identifier=$config.identifier; frontend=$front; source=$qaApp; sha256=(Get-FileHash -LiteralPath $exe).Hash } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qaRoot 'native-build.json') -Encoding utf8
if (-not $BuildOnly) {
    & node (Join-Path $PSScriptRoot 'verify_startup_native.cjs')
    if ($LASTEXITCODE -ne 0) { throw 'Startup native verification failed; see .codex-local/startup/native-report.json.' }
}
