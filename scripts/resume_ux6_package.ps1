param([switch]$FastLocalInstaller)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-6'
$m=Get-Content -LiteralPath (Join-Path $qaRoot 'package-build.json') -Raw|ConvertFrom-Json
$work=[IO.Path]::GetFullPath($m.work)
$source=[IO.Path]::GetFullPath($m.source)
$data=[IO.Path]::GetFullPath($m.data)
if($work -notmatch '^C:\\SmartiAI-ux6-build-[a-f0-9]{32}$' -or $source -ne (Join-Path $work 'source') -or -not $data.StartsWith(($qaRoot+'\package-data-'),[StringComparison]::OrdinalIgnoreCase)){throw 'Owned recovery paths required'}
$env:SMARTI_BUILD_WORK_DIR=$work;$env:SMARTI_DATA_DIR=$data;$env:CODEX_HOME=Join-Path $data 'codex-account'
$env:PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring';$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $data 'webview-profile'
$env:CARGO_TARGET_DIR=Join-Path $taskRoot 'desktop\src-tauri\target'
foreach($key in @('OPENAI_API_KEY','CODEX_API_KEY','CODEX_ACCESS_TOKEN','SMARTI_CORE_BINARY','SMARTI_PROJECT_ROOT','SMARTI_PYTHON','NODE_TLS_REJECT_UNAUTHORIZED')){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
$env:NODE_USE_SYSTEM_CA='1'
if($FastLocalInstaller){
 # Override derived QA config only. Production source/default LZMA is unchanged.
 $realNpm=(Get-Command npm.cmd).Source
 $shim=Join-Path $work 'qa-cli';New-Item -ItemType Directory -Force -Path $shim|Out-Null
 $configPath=Join-Path $source 'desktop\src-tauri\tauri.release.conf.json'
 $patcher=Join-Path $shim 'qa-compression.ps1'
 @'
param([string]$Config)
$ErrorActionPreference='Stop'
$resolved=[IO.Path]::GetFullPath($Config)
if($resolved -notmatch '^C:\\SmartiAI-ux6-build-[a-f0-9]{32}\\source\\desktop\\src-tauri\\tauri.release.conf.json$'){throw 'Owned derived release config required'}
$c=Get-Content -LiteralPath $resolved -Raw|ConvertFrom-Json
$c.bundle.windows|Add-Member -NotePropertyName nsis -NotePropertyValue @{compression='zlib'} -Force
$c|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $resolved -Encoding utf8
'@|Set-Content -LiteralPath $patcher -Encoding utf8
 @"
@echo off
if "%~1"=="run" if "%~2"=="tauri" pwsh -NoProfile -File "$patcher" -Config "$configPath"
if errorlevel 1 exit /b %errorlevel%
call "$realNpm" %*
exit /b %errorlevel%
"@|Set-Content -LiteralPath (Join-Path $shim 'npm.cmd') -Encoding ascii
 $env:PATH=$shim+';'+$env:PATH
}
& (Join-Path $source 'scripts\build_tauri_release.ps1') -Version '0.87.0' -AllowUnsignedLocal -SkipCoreBuild -SkipRuntime
