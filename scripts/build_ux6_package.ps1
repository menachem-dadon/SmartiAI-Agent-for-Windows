param([switch]$Fresh)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-6'
if($Fresh){
 New-Item -ItemType Directory -Force -Path $qaRoot|Out-Null
 $previous=Join-Path $qaRoot 'package-build.json'
 if(Test-Path -LiteralPath $previous){Copy-Item -LiteralPath $previous -Destination (Join-Path $qaRoot ('package-build-prior-'+[Guid]::NewGuid().ToString('N')+'.json'))}
 & python (Join-Path $taskRoot 'scripts\prepare_ux6_package.py') --short-source
 if($LASTEXITCODE -ne 0){throw 'Fresh isolated source preparation failed'}
}
$manifest=Get-Content -LiteralPath (Join-Path $qaRoot 'package-build.json') -Raw|ConvertFrom-Json
$source=[IO.Path]::GetFullPath($manifest.source)
$data=[IO.Path]::GetFullPath($manifest.data)
$work=[IO.Path]::GetFullPath($manifest.work)
if($work -notmatch '^C:\\SmartiAI-ux6-build-[a-f0-9]{32}$' -or -not $data.StartsWith(($qaRoot+'\package-data-'),[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid isolated package paths'}
if($Fresh){
 if($source -ne (Join-Path $work 'source') -or @(Get-ChildItem -LiteralPath $work -Force).Count -ne 1){throw 'Fresh ASCII source checkout required'}
}elseif(-not $source.StartsWith(($qaRoot+'\package-source-'),[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $work)){throw 'Build work directory must be fresh and owned'}
New-Item -ItemType Directory -Force -Path $work,$data|Out-Null
$env:SMARTI_BUILD_WORK_DIR=$work
$env:SMARTI_DATA_DIR=$data
$env:CODEX_HOME=Join-Path $data 'codex-account'
$env:PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring'
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $data 'webview-profile'
$env:CARGO_TARGET_DIR=Join-Path $taskRoot 'desktop\src-tauri\target'
$env:NODE_USE_SYSTEM_CA='1'
foreach($key in @('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN','SMARTI_CORE_BINARY','SMARTI_PROJECT_ROOT','SMARTI_PYTHON','SMARTI_SUPERVISOR_SMOKE_FILE','SMARTI_BROWSER_SMOKE_FILE','NODE_TLS_REJECT_UNAUTHORIZED')){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
& (Join-Path $source 'scripts\build_tauri_release.ps1') -Version '0.87.0' -AllowUnsignedLocal
if(-not $?){throw 'Updated unsigned package build failed'}
$reportPath=Join-Path $source 'release\SmartiAI-Agent-for-Windows-0.87.0-manifest.json'
$report=Get-Content -LiteralPath $reportPath -Raw|ConvertFrom-Json
if(-not $report.packageSmoke.passed){throw 'Current package smoke evidence is missing'}
$current=(& python (Join-Path $taskRoot 'scripts\verify_ux6_acceptance.py') --fingerprint).Trim()
if($LASTEXITCODE -ne 0 -or $current -ne $manifest.source_sha256){throw 'Working source changed during the build; review the frozen snapshot separately'}
$report|Add-Member -NotePropertyName source_sha256 -NotePropertyValue $manifest.source_sha256 -Force
$report|Add-Member -NotePropertyName compiled_executable_source_sha256 -NotePropertyValue $manifest.source_sha256 -Force
$report|ConvertTo-Json -Depth 20|Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Host "Updated installer, ZIP and matching source proof: $reportPath"
