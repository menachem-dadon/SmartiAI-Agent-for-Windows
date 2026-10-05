param([switch]$BuildOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$qaRoot = Join-Path $taskRoot '.codex-local\ux-5'
$qaApp = Join-Path $qaRoot 'native-app'
$qaData = Join-Path $qaRoot ('native-data-' + [Guid]::NewGuid().ToString('N'))
$source = Join-Path $taskRoot 'desktop\src-tauri'
New-Item -ItemType Directory -Path $qaApp -Force | Out-Null
foreach ($part in @('src','icons','capabilities','build.rs','Cargo.lock','Cargo.toml')) {
    Copy-Item -LiteralPath (Join-Path $source $part) -Destination $qaApp -Recurse -Force
}
$cargo = Get-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Raw
$cargo = $cargo.Replace('name = "smarti_desktop_lib"', 'name = "smarti_ux5_lib"')
Set-Content -LiteralPath (Join-Path $qaApp 'src\main.rs') -Value ((Get-Content -LiteralPath (Join-Path $source 'src\main.rs') -Raw).Replace('smarti_desktop_lib::run()', 'smarti_ux5_lib::run()')) -Encoding utf8
$cargo += "`n[[bin]]`nname = `"ux5-native`"`npath = `"src/main.rs`"`n"
Set-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Value $cargo -Encoding utf8
$config = Get-Content -LiteralPath (Join-Path $source 'tauri.conf.json') -Raw | ConvertFrom-Json
$config.identifier = 'ai.smarti.ux5native'
$config.build.devUrl = 'http://127.0.0.1:1439'
$config.app.windows[0] | Add-Member -NotePropertyName visible -NotePropertyValue $false -Force
$config.bundle.active = $false
$config.bundle.PSObject.Properties.Remove('resources')
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $qaApp 'tauri.conf.json') -Encoding utf8
$env:CARGO_TARGET_DIR = Join-Path $source 'target'
$cargoBin = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin\cargo.exe'
& $cargoBin build --manifest-path (Join-Path $qaApp 'Cargo.toml') --bin ux5-native
if ($LASTEXITCODE -ne 0) { throw 'QA native build failed.' }
if ($BuildOnly) { return }
if (netstat -ano | Select-String ':19457\s+\S+\s+LISTENING') { throw 'The QA CDP port is already owned by another process.' }
if (-not (Get-NetTCPConnection -LocalPort 1439 -State Listen -ErrorAction SilentlyContinue)) { throw 'The product Vite server must be running on 1439.' }
New-Item -ItemType Directory -Path $qaData -Force | Out-Null
$qaWorkspace = Join-Path $qaData 'workspace'
New-Item -ItemType Directory -Path $qaWorkspace -Force | Out-Null
@{ api_mode='local'; selected_local_model='ux5-local'; updates_auto_check=$false; default_output_dir=$qaWorkspace; allowed_write_dirs=@($qaWorkspace); ui_preferences=@{theme_mode='light'; settings_show_advanced=$true; workspace_start_maximized=$true} } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $qaData 'smarti_settings.json') -Encoding utf8
$qaPython = Join-Path $qaRoot 'qa-python'
New-Item -ItemType Directory -Path $qaPython -Force | Out-Null
@'
import keyring
from keyring.backend import KeyringBackend
class Ux5MemoryKeyring(KeyringBackend):
    priority = 1
    def __init__(self): self.values = {}
    def get_password(self, service, username): return self.values.get((service, username))
    def set_password(self, service, username, value): self.values[(service, username)] = value
    def delete_password(self, service, username): self.values.pop((service, username), None)
keyring.set_keyring(Ux5MemoryKeyring())
'@ | Set-Content -LiteralPath (Join-Path $qaPython 'sitecustomize.py') -Encoding utf8
$env:SMARTI_PROJECT_ROOT = $taskRoot
$env:SMARTI_PYTHON = (Get-Command python).Source
$env:SMARTI_DATA_DIR = $qaData
$env:PYTHONPATH = $qaPython
$env:SMARTI_DETERMINISTIC_PRODUCT_SMOKE = '1'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=19457'
$process = Start-Process -FilePath (Join-Path $env:CARGO_TARGET_DIR 'debug\ux5-native.exe') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qaRoot 'native.stdout') -RedirectStandardError (Join-Path $qaRoot 'native.stderr') -PassThru
@{ pid=$process.Id; data=$qaData; executable=(Join-Path $env:CARGO_TARGET_DIR 'debug\ux5-native.exe'); identifier='ai.smarti.ux5native'; cdp='http://127.0.0.1:19457' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $qaRoot 'native-launch.json') -Encoding utf8
Write-Output "QA native process $($process.Id), separate data at $qaData"
