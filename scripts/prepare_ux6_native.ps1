param([ValidateSet('dev','built','voice','voicefinal')][string]$Mode='built',[switch]$BuildOnly,[switch]$ReuseProfile,[ValidateSet(1446,1448)][int]$DevPort=1446)
$ErrorActionPreference='Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-6'
$sourceHash=(& python (Join-Path $PSScriptRoot 'verify_ux6_acceptance.py') --fingerprint).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot fingerprint source'}
$qaApp=Join-Path $qaRoot ('native-app-'+$Mode)
$launchPath=Join-Path $qaRoot ('native-'+$Mode+'-launch.json')
$source=Join-Path $taskRoot 'desktop\src-tauri'
$bin='ux6-'+$Mode
$exe=Join-Path $source ('target\debug\'+$bin+'.exe')
if(Get-Process -Name $bin -ErrorAction SilentlyContinue){throw 'Quit the owned QA app before replacing its executable.'}
$cdpPort=if($Mode -eq 'dev'){19466}elseif($Mode -eq 'voice'){19468}elseif($Mode -eq 'voicefinal'){19469}else{19467}
if(Get-NetTCPConnection -LocalPort $cdpPort -State Listen -ErrorAction SilentlyContinue){throw 'QA CDP port already owned.'}
New-Item -ItemType Directory -Path $qaApp -Force|Out-Null
foreach($part in @('src','icons','capabilities','build.rs','Cargo.lock','Cargo.toml')){Copy-Item -LiteralPath (Join-Path $source $part) -Destination $qaApp -Recurse -Force}
$lib='smarti_ux6_'+$Mode+'_lib'
$cargo=(Get-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Raw).Replace('name = "smarti_desktop_lib"',('name = "'+$lib+'"')).Replace('[features]',"[features]`ncustom-protocol = [`"tauri/custom-protocol`"]")
$cargo+="`n[[bin]]`nname = `"$bin`"`npath = `"src/main.rs`"`n"
Set-Content -LiteralPath (Join-Path $qaApp 'Cargo.toml') -Value $cargo -Encoding utf8
Set-Content -LiteralPath (Join-Path $qaApp 'src\main.rs') -Value ((Get-Content -LiteralPath (Join-Path $source 'src\main.rs') -Raw).Replace('smarti_desktop_lib::run()',($lib+'::run()'))) -Encoding utf8
$config=Get-Content -LiteralPath (Join-Path $source 'tauri.conf.json') -Raw|ConvertFrom-Json
$config.identifier='ai.smarti.ux6'+$Mode
$config.build.devUrl='http://127.0.0.1:'+$DevPort
if($Mode -ne 'dev'){
 $front=Join-Path $qaRoot ('frontend-'+[Guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $front|Out-Null
 Copy-Item -Path (Join-Path $taskRoot 'desktop\dist\*') -Destination $front -Recurse -Force
 # Absolute Windows paths can deserialize as a file URL instead of embedded
 # assets. Use a relative directory, as the production Tauri config does.
 $config.build.frontendDist='../'+[IO.Path]::GetFileName($front)
}
$config.app.windows[0]|Add-Member -NotePropertyName visible -NotePropertyValue $false -Force
$config.app.windows[0].title='SmartiAI - UX6 QA '+$Mode
$config.bundle.active=$false;$config.bundle.PSObject.Properties.Remove('resources')
$config|ConvertTo-Json -Depth 30|Set-Content -LiteralPath (Join-Path $qaApp 'tauri.conf.json') -Encoding utf8
$env:CARGO_TARGET_DIR=Join-Path $source 'target'
$cargoBin=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cargo\bin\cargo.exe'
$argsBuild=@('build','--locked','--manifest-path',(Join-Path $qaApp 'Cargo.toml'),'--bin',$bin)
if($Mode -ne 'dev'){$argsBuild+=@('--features','custom-protocol')}
& $cargoBin @argsBuild
if($LASTEXITCODE -ne 0){throw 'QA Tauri build failed.'}
if($sourceHash -ne (& python (Join-Path $PSScriptRoot 'verify_ux6_acceptance.py') --fingerprint).Trim()){throw 'Source changed during QA build; do not launch stale trial'}
if($BuildOnly){return}
if($ReuseProfile){
 $previous=Get-Content -LiteralPath $launchPath -Raw|ConvertFrom-Json
 $qaData=[IO.Path]::GetFullPath($previous.data)
 if(-not $qaData.StartsWith(($qaRoot+'\native-data-'),[StringComparison]::OrdinalIgnoreCase)){throw 'Invalid QA profile.'}
}else{
 $qaData=Join-Path $qaRoot ('native-data-'+$Mode+'-'+[Guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $qaData -Force|Out-Null
 $workspace=Join-Path $qaData 'workspace';New-Item -ItemType Directory -Path $workspace|Out-Null
 @{api_mode='local';selected_local_model='ux6-local';updates_auto_check=$false;default_output_dir=$workspace;allowed_write_dirs=@($workspace);ui_preferences=@{theme_mode='light';settings_show_advanced=$true;workspace_sidebar_collapsed=$false}}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $qaData 'smarti_settings.json') -Encoding utf8
}
$qaPython=Join-Path $qaRoot 'qa-python';New-Item -ItemType Directory -Path $qaPython -Force|Out-Null
@'
import keyring
from keyring.backend import KeyringBackend
class Ux6Keyring(KeyringBackend):
    priority=1
    def __init__(self): self.values={}
    def get_password(self, service, username): return self.values.get((service,username))
    def set_password(self, service, username, value): self.values[(service,username)]=value
    def delete_password(self, service, username): self.values.pop((service,username),None)
keyring.set_keyring(Ux6Keyring())
'@|Set-Content -LiteralPath (Join-Path $qaPython 'sitecustomize.py') -Encoding utf8
$env:SMARTI_PROJECT_ROOT=$taskRoot;$env:SMARTI_PYTHON=(Get-Command python).Source
$env:SMARTI_DATA_DIR=$qaData;$env:PYTHONPATH=$qaPython
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $qaData 'webview-profile'
$env:CODEX_HOME=Join-Path $qaData 'codex-account'
foreach($key in @('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN')){[Environment]::SetEnvironmentVariable($key,$null,'Process')}
New-Item -ItemType Directory -Path $env:CODEX_HOME -Force|Out-Null
$env:SMARTI_DETERMINISTIC_PRODUCT_SMOKE='1'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port='+$cdpPort
& $env:SMARTI_PYTHON (Join-Path $taskRoot 'scripts\seed_ux6_native.py') $qaData
if($LASTEXITCODE -ne 0){throw 'QA seed failed.'}
$watch=[Diagnostics.Stopwatch]::StartNew()
$p=Start-Process -FilePath $exe -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qaRoot ('native-'+$Mode+'.stdout')) -RedirectStandardError (Join-Path $qaRoot ('native-'+$Mode+'.stderr')) -PassThru
@{pid=$p.Id;data=$qaData;executable=$exe;identifier=$config.identifier;cdp=('http://127.0.0.1:'+$cdpPort);mode=$Mode;deterministic=$true;devUrl=$config.build.devUrl;frontend=$config.build.frontendDist;source_sha256=$sourceHash;sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash;launchUtc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $launchPath -Encoding utf8
Write-Output ('QA '+$Mode+' process '+$p.Id+'; isolated data '+$qaData)
