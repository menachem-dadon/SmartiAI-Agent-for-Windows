param([ValidateSet('built','dev')][string]$Mode='built',[switch]$LiveProviders)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-6'
$launchPath=Join-Path $qaRoot ('native-'+$Mode+'-launch.json')
$launch=Get-Content -LiteralPath $launchPath -Raw|ConvertFrom-Json
$exe=Join-Path $taskRoot ('desktop\src-tauri\target\debug\ux6-'+$Mode+'.exe')
$data=[IO.Path]::GetFullPath($launch.data)
if($launch.identifier -ne ('ai.smarti.ux6'+$Mode) -or $launch.executable -ne $exe -or -not $data.StartsWith(($qaRoot+'\native-data-'),[StringComparison]::OrdinalIgnoreCase)){throw 'QA identity mismatch'}
if(Get-Process -Name ('ux6-'+$Mode) -ErrorAction SilentlyContinue){throw 'Quit owned QA app gracefully before relaunch'}
$port=if($Mode -eq 'built'){19467}else{19466}
if(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue){throw 'Owned QA port is occupied'}
$env:SMARTI_PROJECT_ROOT=$taskRoot;$env:SMARTI_PYTHON=(Get-Command python).Source
$env:SMARTI_DATA_DIR=$data;$env:PYTHONPATH=Join-Path $qaRoot 'qa-python'
if(-not(Test-Path -LiteralPath (Join-Path $env:PYTHONPATH 'sitecustomize.py'))){throw 'Keyring isolation missing'}
$env:CODEX_HOME=Join-Path $data 'codex-account'
foreach($key in @('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN')){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $data 'webview-profile'
$env:SMARTI_DETERMINISTIC_PRODUCT_SMOKE=if($LiveProviders){$null}else{'1'}
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port='+$port
$p=Start-Process -FilePath $exe -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qaRoot ($Mode+'-relaunch.stdout')) -RedirectStandardError (Join-Path $qaRoot ($Mode+'-relaunch.stderr')) -PassThru
$launch.pid=$p.Id;$launch.launchUtc=[DateTime]::UtcNow.ToString('o')
$launch|Add-Member -NotePropertyName deterministic -NotePropertyValue (-not $LiveProviders) -Force
$launch|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $launchPath -Encoding utf8
Write-Output ('Isolated '+$Mode+' relaunched; deterministic model: '+(-not $LiveProviders))
