[CmdletBinding()]
param([ValidateSet("PreInstall", "PostInstall")][string]$Mode = "PreInstall")

$ErrorActionPreference = "Stop"
$dataRoot = Join-Path $env:APPDATA "SmartiAI"
$migrationRoot = Join-Path $dataRoot "migration"
New-Item -ItemType Directory -Force -Path $migrationRoot | Out-Null

if ($Mode -eq "PostInstall") {
    Set-Content -LiteralPath (Join-Path $migrationRoot "tauri-installed.txt") -Value (Get-Date).ToUniversalTime().ToString("o") -Encoding UTF8
    exit 0
}

$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{2F7748B6-3D46-4E9C-B187-0F5C2E9F38E1}_is1"
$entry = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
if (-not $entry) { exit 0 }

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backup = Join-Path $migrationRoot "backups\$stamp\legacy-inno-install"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$install = [System.IO.Path]::GetFullPath([string]$entry.InstallLocation)
$allowedNames = @(
    "smarti_settings.json", "smarti_usage.json", "smarti_memory.json",
    "smarti_memory.md", "smarti_chats.json", "mcp_config.json",
    "custom_tools", "mcp_tools", "skills", "browser_session_data"
)
foreach ($name in $allowedNames) {
    $source = Join-Path $install $name
    if (-not (Test-Path -LiteralPath $source)) { continue }
    Copy-Item -LiteralPath $source -Destination (Join-Path $backup $name) -Recurse -Force
}
@{
    detectedAt = (Get-Date).ToUniversalTime().ToString("o")
    installLocation = $install
    uninstallString = [string]$entry.UninstallString
    backup = $backup
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $migrationRoot "legacy-inno-install.json") -Encoding UTF8

$uninstaller = [string]$entry.UninstallString
if ($uninstaller.StartsWith('"')) {
    $closing = $uninstaller.IndexOf('"', 1)
    $uninstaller = $uninstaller.Substring(1, $closing - 1)
}
if ($uninstaller -and (Test-Path -LiteralPath $uninstaller)) {
    $process = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) { throw "Legacy uninstaller failed with exit code $($process.ExitCode)." }
}
