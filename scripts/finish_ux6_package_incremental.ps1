# Continue the existing owned local build; never reinstall or redownload runtimes.
param([switch]$FinalizeOnly,[string]$SupervisorReceipt,[string]$BrowserReceipt)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-6'
$m=Get-Content -LiteralPath (Join-Path $qaRoot 'package-build.json') -Raw|ConvertFrom-Json
$work=[IO.Path]::GetFullPath($m.work);$source=[IO.Path]::GetFullPath($m.source)
if($work -notmatch '^C:\\SmartiAI-ux6-build-[a-f0-9]{32}$' -or $source -ne (Join-Path $work 'source')){throw 'Owned ASCII build required'}
if(-not ([IO.Path]::GetFullPath($m.data)).StartsWith($qaRoot+'\package-data-',[StringComparison]::OrdinalIgnoreCase)){throw 'Isolated package data required'}
$current=(& python (Join-Path $taskRoot 'scripts\verify_ux6_acceptance.py') --fingerprint).Trim()
if($LASTEXITCODE -ne 0 -or $current -ne $m.source_sha256){throw 'Current package snapshot required'}
$env:SMARTI_DATA_DIR=$m.data;$env:CODEX_HOME=Join-Path $m.data 'codex-account'
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $m.data 'webview-profile'
$env:PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring'
$env:SMARTI_BUILD_WORK_DIR=$work;$env:CARGO_TARGET_DIR=Join-Path $taskRoot 'desktop\src-tauri\target'
$env:PATH=(Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin')+';'+$env:PATH
foreach($key in @('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN','SMARTI_CORE_BINARY','SMARTI_PROJECT_ROOT','SMARTI_PYTHON','NODE_TLS_REJECT_UNAUTHORIZED')){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
$env:NODE_USE_SYSTEM_CA='1'
# Reuse the exact canonical smoke/signature/Qt checks without invoking its build.
$canonical=Join-Path $source 'scripts\build_tauri_release.ps1'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($canonical,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'Canonical script parse failed'}
foreach($name in @('Read-Json','Invoke-PackagedSmoke','Assert-No-Qt','Get-SignatureStatus')){
 $function=$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$false)|Where-Object Name -eq $name
 if(@($function).Count -ne 1){throw 'Canonical function missing'}
 . ([scriptblock]::Create($function.Extent.Text))
}
function Copy-Incremental([string]$From,[string]$To){
 $a=[IO.Path]::GetFullPath($From);$b=[IO.Path]::GetFullPath($To)
 if(-not $a.StartsWith($work+'\',[StringComparison]::OrdinalIgnoreCase) -or -not $b.StartsWith($work+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Only owned resource trees can be copied'}
 & robocopy.exe $a $b /E /R:1 /W:1 /COPY:DAT /DCOPY:DAT /NFL /NDL /NP /NJH /NJS
 if($LASTEXITCODE -ge 8){throw 'Incremental resource copy failed'}
}
$core=Join-Path $work 'dist\smarti-core';$runtime=Join-Path $work 'build\runtime'
$stage=Join-Path $source 'desktop\src-tauri\package-resources'
$release=Join-Path $source 'release'
if(-not $FinalizeOnly){
Assert-No-Qt $core;Assert-No-Qt $runtime
Copy-Incremental $core (Join-Path $stage 'smarti-core')
Copy-Incremental $runtime (Join-Path $stage 'runtime')
$release=Join-Path $source 'release';$prior=Join-Path $work ('prior-artifacts-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $prior -Force|Out-Null
foreach($name in @('SmartiAI-Agent-for-Windows-0.87.0-Setup.exe','SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip','SmartiAI-Agent-for-Windows-0.87.0-manifest.json')){
 $old=[IO.Path]::GetFullPath((Join-Path $release $name));$saved=[IO.Path]::GetFullPath((Join-Path $prior $name))
 if(-not $old.StartsWith($release+'\') -or -not $saved.StartsWith($prior+'\')){throw 'Artifact path escaped'}
 if(Test-Path -LiteralPath $old){Move-Item -LiteralPath $old -Destination $saved}
}
$config=Join-Path $source 'desktop\src-tauri\tauri.release.conf.json'
$c=Read-Json $config
if($c.bundle.createUpdaterArtifacts -or $c.bundle.windows.nsis.compression -ne 'zlib'){throw 'Existing unsigned QA config required'}
Push-Location (Join-Path $source 'desktop')
try{ & npm.cmd run tauri -- build --target x86_64-pc-windows-msvc --config $config --bundles nsis; if($LASTEXITCODE -ne 0){throw 'Current GUI package build failed'} }finally{Pop-Location}
}else{
 if($m.recipe_only_delta.changed_paths.Count -ne 1 -or $m.recipe_only_delta.changed_paths[0] -ne 'scripts/build_tauri_release.ps1'){throw 'Finalize-only requires a verified recipe-only delta'}
}
if($current -ne (& python (Join-Path $taskRoot 'scripts\verify_ux6_acceptance.py') --fingerprint).Trim()){throw 'Source changed during package build'}
$target=Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc\release'
$portable=Join-Path $work 'portable\SmartiAI'
if(-not $FinalizeOnly){
 Copy-Item -LiteralPath (Join-Path $target 'smarti-desktop.exe') -Destination (Join-Path $portable 'SmartiAI.exe') -Force
 Copy-Incremental $stage (Join-Path $portable 'package-resources')
}
$coreHash=(Get-FileHash -LiteralPath (Join-Path $core 'smarti-core.exe') -Algorithm SHA256).Hash
foreach($copy in @((Join-Path $stage 'smarti-core\smarti-core.exe'),(Join-Path $portable 'package-resources\smarti-core\smarti-core.exe'))){if((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ne $coreHash){throw 'Core copy is stale'}}
$run=[Guid]::NewGuid().ToString('N');$smokes=Join-Path $work 'package-smoke'
if($FinalizeOnly){
 $receipt=Read-Json $SupervisorReceipt
 if($receipt.compiled_source_sha256 -ne $m.compiled_executable_source_sha256 -or $receipt.executable_sha256 -ne (Get-FileHash -LiteralPath (Join-Path $portable 'SmartiAI.exe') -Algorithm SHA256).Hash -or $receipt.core_sha256 -ne $coreHash){throw 'Passed supervisor evidence does not match these exact binaries'}
 $proof=[IO.Path]::GetFullPath($receipt.artifact)
 if(-not $proof.StartsWith($smokes+'\') -or (Get-FileHash -LiteralPath $proof -Algorithm SHA256).Hash -ne $receipt.artifact_sha256){throw 'Supervisor proof outside owned build or changed'}
 $supervisor=Read-Json $proof
 if(-not $supervisor.ok){throw 'Supervisor evidence failed'}
}else{
 $supervisor=Invoke-PackagedSmoke -AppPath (Join-Path $portable 'SmartiAI.exe') -WorkingDirectory $portable -SmokeVariable SMARTI_SUPERVISOR_SMOKE_FILE -SmokeFile (Join-Path $smokes "supervisor-$run.json") -DataDirectory (Join-Path $smokes "supervisor-$run-data")
}
if($BrowserReceipt){
 $receipt=Read-Json $BrowserReceipt
 if($receipt.compiled_source_sha256 -ne $m.compiled_executable_source_sha256 -or $receipt.executable_sha256 -ne (Get-FileHash -LiteralPath (Join-Path $portable 'SmartiAI.exe') -Algorithm SHA256).Hash){throw 'Browser proof does not match this exact binary'}
 $proof=[IO.Path]::GetFullPath($receipt.artifact)
 if(-not $proof.StartsWith($smokes+'\') -or (Get-FileHash -LiteralPath $proof -Algorithm SHA256).Hash -ne $receipt.artifact_sha256){throw 'Browser proof changed or escaped'}
 $browser=Read-Json $proof
 if(-not $browser.ok){throw 'Browser proof failed'}
}else{
 $browser=Invoke-PackagedSmoke -AppPath (Join-Path $portable 'SmartiAI.exe') -WorkingDirectory $portable -SmokeVariable SMARTI_BROWSER_SMOKE_FILE -SmokeFile (Join-Path $smokes "browser-$run.json") -DataDirectory (Join-Path $smokes "browser-$run-data")
}
Write-Output 'Current packaged supervisor/browser smokes passed; preparing final archive'
$installerOut=Join-Path $release 'SmartiAI-Agent-for-Windows-0.87.0-Setup.exe'
Copy-Item -LiteralPath (Join-Path $target 'bundle\nsis\SmartiAI_0.87.0_x64-setup.exe') -Destination $installerOut
@{version='0.87.0';kind='portable';app='SmartiAI.exe';core='package-resources\smarti-core\smarti-core.exe';runtime='package-resources\runtime';builtAt=[DateTime]::UtcNow.ToString('o');source_sha256=$current}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $portable 'release_manifest.json') -Encoding utf8
$zip=Join-Path $release 'SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip'
Compress-Archive -Path (Join-Path $portable '*') -DestinationPath $zip -CompressionLevel Optimal
$report=@{version='0.87.0';builtAt=[DateTime]::UtcNow.ToString('o');source_sha256=$current;compiled_executable_source_sha256=$m.compiled_executable_source_sha256;recipe_only_delta=$m.recipe_only_delta;updaterSigned=$false;authenticode=(Get-SignatureStatus $installerOut);artifacts=@($installerOut,$zip)|ForEach-Object{@{path=$_;bytes=(Get-Item -LiteralPath $_).Length;sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()}};packageSmoke=@{requested=$true;passed=$true;supervisor=$supervisor;browser=$browser};incremental=@{core_sha256=$coreHash;runtime_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $runtime 'runtime_manifest.json') -Algorithm SHA256).Hash;scope='Current Core rebuilt in existing verified venv; runtime and lock unchanged; incremental resource copies; canonical package smokes before ZIP; unsigned NSIS zlib QA override only'};evidenceBoundary='No installer execution, clean Windows installation/upgrade/uninstall, signing or release proof.'}
$report|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $release 'SmartiAI-Agent-for-Windows-0.87.0-manifest.json') -Encoding utf8
Write-Output 'Current unsigned local package complete; no installer executed'
