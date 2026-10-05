$ErrorActionPreference = 'Stop'
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$qaRoot=Join-Path $taskRoot '.codex-local\ux-4'
$launchPath=Join-Path $qaRoot 'native-launch.json'
$launch=Get-Content -Raw -LiteralPath $launchPath | ConvertFrom-Json
$data=[IO.Path]::GetFullPath($launch.data)
$expectedExecutable=Join-Path $taskRoot 'desktop\src-tauri\target\debug\ux4-native.exe'
if($launch.identifier -ne 'ai.smarti.ux4native' -or $launch.executable -ne $expectedExecutable -or -not $data.StartsWith((Join-Path $qaRoot 'native-data-'),[StringComparison]::OrdinalIgnoreCase)) {throw 'QA relaunch identity mismatch'}
$previous=Get-Process -Id $launch.pid -ErrorAction SilentlyContinue
if($previous){
  if($previous.Path -ne $expectedExecutable){throw 'Previous QA process identity mismatch'}
  Wait-Process -Id $previous.Id -Timeout 15 -ErrorAction Stop
}
$env:SMARTI_PROJECT_ROOT=$taskRoot
$env:SMARTI_PYTHON=(Get-Command python).Source
$env:SMARTI_DATA_DIR=$data
$env:PYTHONPATH=Join-Path $qaRoot 'qa-python'
if(-not(Test-Path -LiteralPath (Join-Path $env:PYTHONPATH 'sitecustomize.py'))){throw 'QA keyring isolation missing'}
$env:SMARTI_DETERMINISTIC_PRODUCT_SMOKE='1'
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=19446'
$process=Start-Process -FilePath $expectedExecutable -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $qaRoot 'native-relaunch.stdout') -RedirectStandardError (Join-Path $qaRoot 'native-relaunch.stderr') -PassThru
$launch.pid=$process.Id
$launch | ConvertTo-Json | Set-Content -LiteralPath $launchPath
Write-Output $process.Id
