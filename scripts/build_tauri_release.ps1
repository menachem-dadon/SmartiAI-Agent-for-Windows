[CmdletBinding()]
param(
    [string]$Version = "0.87.0",
    [switch]$Clean,
    [switch]$SkipRuntime,
    [switch]$SkipCoreBuild,
    [switch]$OfflineInstaller,
    [switch]$AllowUnsignedLocal,
    [switch]$SkipPackageSmoke
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$desktop = Join-Path $repo "desktop"
$cargoDir = Join-Path $desktop "src-tauri"
$stage = Join-Path $cargoDir "package-resources"
$release = Join-Path $repo "release"
$work = if ($env:SMARTI_BUILD_WORK_DIR) { [System.IO.Path]::GetFullPath($env:SMARTI_BUILD_WORK_DIR) } else { "C:\SmartiAI-tauri-build" }
$venv = Join-Path $work ".venv-build"
$dist = Join-Path $work "dist"
$pyiWork = Join-Path $work "pyinstaller-work"
$runtime = Join-Path $work "build\runtime"
$targetTriple = "x86_64-pc-windows-msvc"
$cargoBin = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".cargo\bin"
if (Test-Path -LiteralPath (Join-Path $cargoBin "cargo.exe")) {
    $env:PATH = "$cargoBin;$env:PATH"
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments = @(), [string]$WorkingDirectory = "") {
    if ($WorkingDirectory) { Push-Location $WorkingDirectory }
    try { & $FilePath @Arguments; if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')" } }
    finally { if ($WorkingDirectory) { Pop-Location } }
}
function Reset-ScopedDirectory([string]$Path, [string]$AllowedRoot) {
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\') + '\'
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to reset path outside $resolvedRoot" }
    if (Test-Path -LiteralPath $resolvedPath) { Remove-Item -LiteralPath $resolvedPath -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $resolvedPath | Out-Null
}
function Read-Json([string]$Path) { Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Normalize-Version([string]$Value) { ([string]$Value).Trim().TrimStart([char[]]@('v','V')) }
function Assert-VersionSync {
    $common = Select-String -LiteralPath (Join-Path $repo "smarti\common.py") -Pattern '^APP_VERSION\s*=\s*["'']([^"'']+)' | Select-Object -First 1
    $values = @(
        (Normalize-Version $common.Matches[0].Groups[1].Value)
        (Normalize-Version (Read-Json (Join-Path $cargoDir "tauri.conf.json")).version)
        (Normalize-Version (Read-Json (Join-Path $desktop "package.json")).version)
        (Normalize-Version ((Select-String -LiteralPath (Join-Path $cargoDir "Cargo.toml") -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value))
    )
    foreach ($value in $values) { if ($value -ne (Normalize-Version $Version)) { throw "Version mismatch: requested $Version; found $($values -join ', ')" } }
}
function Assert-No-Qt([string]$Root) {
    $qt = @(Get-ChildItem -LiteralPath $Root -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^PyQt6|Qt6(WebEngine)?' })
    if ($qt.Count) { throw "Production Core contains Qt: $($qt[0].FullName)" }
}
function Copy-Tree([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}
function Get-SignatureStatus([string]$Path) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    [ordered]@{ status = [string]$signature.Status; signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "" } }
}

Assert-VersionSync
if (-not $AllowUnsignedLocal) {
    foreach ($name in @("TAURI_SIGNING_PRIVATE_KEY", "SMARTI_UPDATER_PUBLIC_KEY", "SMARTI_UPDATER_ENDPOINT")) {
        if (-not [Environment]::GetEnvironmentVariable($name)) { throw "$name is required for a production updater build. Use -AllowUnsignedLocal only for explicitly unsigned local evidence." }
    }
}
if ($Clean) {
    Reset-ScopedDirectory -Path $work -AllowedRoot (Split-Path -Parent $work)
    if (Test-Path -LiteralPath $release) { Remove-Item -LiteralPath $release -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $work, $dist, $release, $stage | Out-Null

$coreDist = Join-Path $dist "smarti-core"
if (-not $SkipCoreBuild) {
    $hostPython = if ($env:SMARTI_BUILD_PYTHON) { $env:SMARTI_BUILD_PYTHON } else { (Get-Command python).Source }
    if (-not (Test-Path -LiteralPath (Join-Path $venv "Scripts\python.exe"))) { Invoke-Checked $hostPython @("-m", "venv", $venv) }
    $python = Join-Path $venv "Scripts\python.exe"
    Invoke-Checked $python @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
    Invoke-Checked $python @("-m", "pip", "install", "-r", (Join-Path $repo "requirements-core.txt"), "-r", (Join-Path $repo "requirements-build.txt"))
    Invoke-Checked $python @("-m", "pip", "check")
    Invoke-Checked $python @("-c", "import smarti.core,sys; assert not any(x.startswith('PyQt6') for x in sys.modules); print('Qt-free Core import OK')") $repo
    Invoke-Checked $python @("-m", "PyInstaller", "--clean", "--noconfirm", "--workpath", $pyiWork, "--distpath", $dist, (Join-Path $repo "packaging\smarti-core.spec")) $repo
}
if (-not (Test-Path -LiteralPath (Join-Path $coreDist "smarti-core.exe"))) { throw "PyInstaller Core sidecar is missing." }
Assert-No-Qt $coreDist

if (-not $SkipRuntime) {
    Invoke-Checked "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $repo "scripts\prepare_runtime.ps1"), "-RuntimeDir", $runtime, "-CacheDir", (Join-Path $work "download-cache"), "-RequirementsPath", (Join-Path $repo "requirements-core.txt"))
} elseif (-not (Test-Path -LiteralPath (Join-Path $runtime "runtime_manifest.json"))) { throw "-SkipRuntime requested but no prepared runtime exists at $runtime" }
Assert-No-Qt $runtime

foreach ($name in @("smarti-core", "runtime")) {
    $target = Join-Path $stage $name
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
Copy-Tree $coreDist (Join-Path $stage "smarti-core")
Copy-Tree $runtime (Join-Path $stage "runtime")

Invoke-Checked "npm.cmd" @("ci") $desktop
$base = Read-Json (Join-Path $cargoDir "tauri.conf.json")
$config = [ordered]@{
    version = Normalize-Version $Version
    bundle = [ordered]@{
        targets = @("nsis")
        createUpdaterArtifacts = (-not $AllowUnsignedLocal)
        windows = [ordered]@{ webviewInstallMode = [ordered]@{ type = if ($OfflineInstaller) { "offlineInstaller" } else { "embedBootstrapper" } } }
    }
}
if (-not $AllowUnsignedLocal) {
    $config["plugins"] = [ordered]@{ updater = [ordered]@{ pubkey = $env:SMARTI_UPDATER_PUBLIC_KEY; endpoints = @($env:SMARTI_UPDATER_ENDPOINT); windows = [ordered]@{ installMode = "passive" } } }
}
$releaseConfig = Join-Path $cargoDir "tauri.release.conf.json"
$config | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $releaseConfig -Encoding UTF8
Invoke-Checked "npm.cmd" @("run", "tauri", "--", "build", "--target", $targetTriple, "--config", $releaseConfig, "--bundles", "nsis") $desktop

$target = Join-Path $cargoDir "target\$targetTriple\release"
$appExe = Join-Path $target "smarti-desktop.exe"
if (-not (Test-Path -LiteralPath $appExe)) { throw "Tauri executable is missing: $appExe" }
$installer = Get-ChildItem -LiteralPath (Join-Path $target "bundle\nsis") -Filter "*-setup.exe" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $installer) { throw "Tauri NSIS installer was not produced." }
$installerName = "SmartiAI-Agent-for-Windows-$(Normalize-Version $Version)-Setup.exe"
$installerOut = Join-Path $release $installerName
Copy-Item -LiteralPath $installer.FullName -Destination $installerOut -Force

$portableRoot = Join-Path $work "portable\SmartiAI"
Reset-ScopedDirectory -Path $portableRoot -AllowedRoot $work
Copy-Item -LiteralPath $appExe -Destination (Join-Path $portableRoot "SmartiAI.exe") -Force
Copy-Tree $stage (Join-Path $portableRoot "package-resources")
Copy-Item -LiteralPath (Join-Path $repo "LICENSE") -Destination $portableRoot -Force
$portableManifest = [ordered]@{ version = Normalize-Version $Version; kind = "portable"; app = "SmartiAI.exe"; core = "package-resources\smarti-core\smarti-core.exe"; runtime = "package-resources\runtime"; builtAt = (Get-Date).ToUniversalTime().ToString("o") }
$portableManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $portableRoot "release_manifest.json") -Encoding UTF8
$zipOut = Join-Path $release "SmartiAI-Agent-for-Windows-$(Normalize-Version $Version)-win-x64-portable.zip"
if (Test-Path -LiteralPath $zipOut) { Remove-Item -LiteralPath $zipOut -Force }
Compress-Archive -Path (Join-Path $portableRoot "*") -DestinationPath $zipOut -CompressionLevel Optimal

if (-not $SkipPackageSmoke) {
    $smokeDir = Join-Path $work "package-smoke"
    New-Item -ItemType Directory -Force -Path $smokeDir | Out-Null
    $smokeFile = Join-Path $smokeDir "supervisor.json"
    $oldSmoke = $env:SMARTI_SUPERVISOR_SMOKE_FILE; $oldData = $env:SMARTI_DATA_DIR
    try {
        $env:SMARTI_SUPERVISOR_SMOKE_FILE = $smokeFile
        $env:SMARTI_DATA_DIR = Join-Path $smokeDir "data"
        $process = Start-Process -FilePath (Join-Path $portableRoot "SmartiAI.exe") -WorkingDirectory $portableRoot -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit(90000)) { $process.Kill(); throw "Packaged supervisor smoke timed out." }
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeFile)) { throw "Packaged supervisor smoke failed with exit code $($process.ExitCode)." }
        $smoke = Read-Json $smokeFile
        if (-not $smoke.ok) { throw "Packaged supervisor smoke reported failure: $($smoke | ConvertTo-Json -Compress)" }
    } finally { $env:SMARTI_SUPERVISOR_SMOKE_FILE = $oldSmoke; $env:SMARTI_DATA_DIR = $oldData }
}

$artifacts = @($installerOut, $zipOut)
$updaterArtifacts = @(Get-ChildItem -LiteralPath (Join-Path $target "bundle\nsis") -File | Where-Object { $_.Name -match '\.(sig|zip)$' })
foreach ($item in $updaterArtifacts) { $destination = Join-Path $release $item.Name; Copy-Item -LiteralPath $item.FullName -Destination $destination -Force; $artifacts += $destination }
$report = [ordered]@{
    version = Normalize-Version $Version
    builtAt = (Get-Date).ToUniversalTime().ToString("o")
    updaterSigned = (-not $AllowUnsignedLocal)
    authenticode = Get-SignatureStatus $installerOut
    artifacts = @($artifacts | ForEach-Object { $file = Get-Item -LiteralPath $_; [ordered]@{ path = $file.FullName; bytes = $file.Length; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant() } })
    packageSmoke = (-not $SkipPackageSmoke)
    evidenceBoundary = "No clean Windows 10/11 VM, upgrade, uninstall or Authenticode claim is implied by this local build report."
}
$reportPath = Join-Path $release "SmartiAI-Agent-for-Windows-$(Normalize-Version $Version)-manifest.json"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host "Tauri release build complete: $reportPath"
