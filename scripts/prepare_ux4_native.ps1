param([switch]$BuildOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$qaRoot = Join-Path $taskRoot '.codex-local\ux-4'
$qaApp = Join-Path $qaRoot 'native-app'
$qaData = Join-Path $qaRoot ('native-data-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $taskRoot 'desktop\src-tauri'
New-Item -ItemType Directory -Path $qaApp -Force | Out-Null
foreach ($part in @('src','icons','capabilities','build.rs','Cargo.lock','Cargo.toml')) {
    Copy-Item -LiteralPath (Join-Path $source $part) -Destination $qaApp -Recurse -Force
}
$cargo = Get-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Raw
$cargo += "`n[[bin]]`nname = `"ux4-native`"`npath = `"src/main.rs`"`n"
Set-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Value $cargo -Encoding utf8
$config = Get-Content -LiteralPath (Join-Path $source 'tauri.conf.json') -Raw | ConvertFrom-Json
$config.identifier = 'ai.smarti.ux4native'
$config.app.windows[0] | Add-Member -NotePropertyName visible -NotePropertyValue $false -Force
$config.bundle.active = $false
$config.bundle.PSObject.Properties.Remove('resources')
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $qaApp 'tauri.conf.json') -Encoding utf8
$env:CARGO_TARGET_DIR = Join-Path $source 'target'
$cargoBin = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin\cargo.exe'
& $cargoBin build --manifest-path (Join-Path $qaApp 'Cargo.toml') --bin ux4-native
if ($LASTEXITCODE -ne 0) { throw 'QA native build failed.' }
if ($BuildOnly) { return }
if (-not (Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue)) { throw 'The product Vite server must be running on 1420.' }
New-Item -ItemType Directory -Path $qaData -Force | Out-Null
$qaPython = Join-Path $qaRoot 'qa-python'
New-Item -ItemType Directory -Path $qaPython -Force | Out-Null
@'
import keyring
from keyring.backend import KeyringBackend
class Ux4MemoryKeyring(KeyringBackend):
    priority = 1
    def __init__(self): self.values = {}
    def get_password(self, service, username): return self.values.get((service, username))
    def set_password(self, service, username, value): self.values[(service, username)] = value
    def delete_password(self, service, username): self.values.pop((service, username), None)
keyring.set_keyring(Ux4MemoryKeyring())
'@ | Set-Content -LiteralPath (Join-Path $qaPython 'sitecustomize.py') -Encoding utf8
$env:SMARTI_PROJECT_ROOT = $taskRoot
$env:SMARTI_PYTHON = (Get-Command python).Source
$env:SMARTI_DATA_DIR = $qaData
$env:PYTHONPATH = $qaPython
$env:SMARTI_DETERMINISTIC_PRODUCT_SMOKE = '1'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=19446'
$process = Start-Process -FilePath (Join-Path $env:CARGO_TARGET_DIR 'debug\ux4-native.exe') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qaRoot 'native.stdout') -RedirectStandardError (Join-Path $qaRoot 'native.stderr') -PassThru
@{ pid=$process.Id; data=$qaData; executable=(Join-Path $env:CARGO_TARGET_DIR 'debug\ux4-native.exe'); identifier='ai.smarti.ux4native'; cdp='http://127.0.0.1:19446' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qaRoot 'native-launch.json') -Encoding utf8
Write-Output "QA native process $($process.Id), separate data at $qaData"
