<#
.SYNOPSIS
Build Smarti's Tauri installer and portable ZIP from an isolated source copy.
.EXAMPLE
pwsh -NoProfile -File .\scripts\build_and_package.ps1 -Version 0.88.0 -Label preview
.EXAMPLE
pwsh -NoProfile -File .\scripts\build_and_package.ps1 -PrepareOnly
#>
[CmdletBinding()]
param(
    [string]$Version = '',
    [string]$Label = '',
    [string]$OutputDirectory = '',
    [string]$WorkRoot = 'C:\SmartiAI-builds',
    [ValidateSet('lzma','zlib')][string]$InstallerCompression = 'lzma',
    [switch]$OfflineInstaller,
    [switch]$SignedUpdater,
    [switch]$SkipPackageSmoke,
    [switch]$PrepareOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRepo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if(-not $OutputDirectory){$OutputDirectory=Join-Path $taskRepo 'release'}
$taskWorkRoot=[IO.Path]::GetFullPath($WorkRoot)
if($taskWorkRoot -match '[^\x00-\x7f]' -or $taskWorkRoot.Length -gt 64){throw 'Use a short ASCII WorkRoot, e.g. C:\SmartiAI-builds'}
New-Item -ItemType Directory -Force -Path $taskWorkRoot|Out-Null
# Serialize builds sharing the Cargo/download cache. No prior build is reset.
$taskLock=$null
$taskSaved=@{}
try{
    try{$taskLock=[IO.File]::Open((Join-Path $taskWorkRoot '.package.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
    catch{throw 'Another build is using this WorkRoot, or it is not writable. Choose another WorkRoot or wait for that build.'}
    foreach($taskName in @('SMARTI_BUILD_WORK_DIR','SMARTI_BUILD_DOWNLOAD_CACHE','SMARTI_DATA_DIR','CODEX_HOME','PYTHON_KEYRING_BACKEND','WEBVIEW2_USER_DATA_FOLDER','CARGO_TARGET_DIR','NODE_USE_SYSTEM_CA','PYTHONUTF8','OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN','SMARTI_CORE_BINARY','SMARTI_PROJECT_ROOT','SMARTI_PYTHON','SMARTI_SUPERVISOR_SMOKE_FILE','SMARTI_BROWSER_SMOKE_FILE','NODE_TLS_REJECT_UNAUTHORIZED')){
        $taskSaved[$taskName]=[Environment]::GetEnvironmentVariable($taskName,'Process')
    }
    $env:PYTHONUTF8='1'
    $taskArgs=@((Join-Path $PSScriptRoot 'prepare_tauri_package.py'),'--work-root',$taskWorkRoot,'--output-directory',[IO.Path]::GetFullPath($OutputDirectory))
    if($Version){$taskArgs+=@('--version',$Version)}
    if($Label){$taskArgs+=@('--label',$Label)}
    $taskPrepared=& python @taskArgs
    if($LASTEXITCODE -ne 0){throw 'Source preparation failed; no package build was started'}
    $taskManifestPath=([string]$taskPrepared).Trim()
    $taskManifest=Get-Content -LiteralPath $taskManifestPath -Raw|ConvertFrom-Json
    $taskWork=[IO.Path]::GetFullPath($taskManifest.work)
    $taskSource=[IO.Path]::GetFullPath($taskManifest.source)
    if(-not $taskWork.StartsWith($taskWorkRoot.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -or $taskSource -ne (Join-Path $taskWork 'source')){throw 'Unexpected snapshot paths'}
    Write-Host "Frozen source/version: $taskManifestPath"
    Write-Host "Version: $($taskManifest.version)  Label: $($taskManifest.label)"
    if($PrepareOnly){Write-Host 'Source prepared only; no compilation, download or packaging performed';return}
    $env:SMARTI_BUILD_WORK_DIR=$taskWork
    $env:SMARTI_BUILD_DOWNLOAD_CACHE=Join-Path $taskWorkRoot 'download-cache'
    $env:SMARTI_DATA_DIR=$taskManifest.data
    $env:CODEX_HOME=Join-Path $taskManifest.data 'codex-account'
    $env:PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring'
    $env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $taskManifest.data 'webview-profile'
    $env:CARGO_TARGET_DIR=Join-Path $taskWorkRoot 'cargo-target'
    $env:NODE_USE_SYSTEM_CA='1'
    foreach($taskName in @('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN','SMARTI_CORE_BINARY','SMARTI_PROJECT_ROOT','SMARTI_PYTHON','SMARTI_SUPERVISOR_SMOKE_FILE','SMARTI_BROWSER_SMOKE_FILE','NODE_TLS_REJECT_UNAUTHORIZED')){
        [Environment]::SetEnvironmentVariable($taskName,$null,'Process')
    }
    $taskBuildArgs=@{Version=$taskManifest.version; InstallerCompression=$InstallerCompression; AllowUnsignedLocal=(-not $SignedUpdater); OfflineInstaller=[bool]$OfflineInstaller; SkipPackageSmoke=[bool]$SkipPackageSmoke}
    & (Join-Path $taskSource 'scripts\build_tauri_release.ps1') @taskBuildArgs
    if(-not $?){throw 'Build failed'}
    $taskFinishedSource=(& python (Join-Path $taskSource 'scripts\tauri_source_manifest.py')).Trim()
    if($LASTEXITCODE -ne 0 -or $taskFinishedSource -ne $taskManifest.source_sha256){throw 'Frozen source inputs changed during the build; package attribution requires review'}
    $taskReportPath=Join-Path $taskSource "release\SmartiAI-Agent-for-Windows-$($taskManifest.version)-manifest.json"
    $taskReport=Get-Content -LiteralPath $taskReportPath -Raw|ConvertFrom-Json
    if(-not $SkipPackageSmoke -and -not $taskReport.packageSmoke.passed){throw 'Package smoke evidence is missing'}
    New-Item -ItemType Directory -Path $taskManifest.output|Out-Null
    foreach($taskArtifact in $taskReport.artifacts){
        $taskFile=[IO.Path]::GetFullPath($taskArtifact.path)
        $taskRelease=[IO.Path]::GetFullPath((Join-Path $taskSource 'release'))
        if(-not $taskFile.StartsWith($taskRelease+'\',[StringComparison]::OrdinalIgnoreCase) -or (Get-FileHash -LiteralPath $taskFile -Algorithm SHA256).Hash -ne $taskArtifact.sha256){throw 'Package artifact path or hash mismatch'}
        $taskDestination=Join-Path $taskManifest.output ([IO.Path]::GetFileName($taskFile))
        Copy-Item -LiteralPath $taskFile -Destination $taskDestination
        if((Get-FileHash -LiteralPath $taskDestination -Algorithm SHA256).Hash -ne $taskArtifact.sha256){throw 'Copied package artifact hash mismatch'}
        $taskArtifact.path=$taskDestination
    }
    foreach($taskName in @('source_sha256','working_tree_source_sha256','version_files_changed','label')){
        $taskReport|Add-Member -NotePropertyName $taskName -NotePropertyValue $taskManifest.$taskName -Force
    }
    $taskReport|Add-Member -NotePropertyName installerCompression -NotePropertyValue $InstallerCompression -Force
    $taskReport|Add-Member -NotePropertyName offlineInstaller -NotePropertyValue ([bool]$OfflineInstaller) -Force
    $taskResult=Join-Path $taskManifest.output "SmartiAI-Agent-for-Windows-$($taskManifest.version)-manifest.json"
    $taskReport|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $taskResult -Encoding utf8
    Copy-Item -LiteralPath $taskManifestPath -Destination (Join-Path $taskManifest.output 'source-manifest.json')
    Write-Host "Installer, portable ZIP and build manifest: $taskResult"
    if($SkipPackageSmoke){Write-Host 'Package smoke checks were explicitly skipped; this build has no smoke acceptance evidence'}
}finally{
    foreach($taskName in $taskSaved.Keys){
        if($null -eq $taskSaved[$taskName]){Remove-Item -LiteralPath ('Env:'+$taskName) -ErrorAction SilentlyContinue}
        else{[Environment]::SetEnvironmentVariable($taskName,$taskSaved[$taskName],'Process')}
    }
    if($taskLock){$taskLock.Dispose()}
}
