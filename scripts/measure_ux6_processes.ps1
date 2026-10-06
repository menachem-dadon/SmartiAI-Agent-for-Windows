param([Parameter(Mandatory)][ValidatePattern('^\d+(,\d+)*$')][string]$RootIds,[int]$Seconds=5)
$ErrorActionPreference='Stop'
if($Seconds -lt 1 -or $Seconds -gt 30){throw 'Use a short measurement sample.'}
$all=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name
$owned=[Collections.Generic.HashSet[int]]::new()
foreach($taskId in $RootIds.Split(',')){$owned.Add([int]$taskId)|Out-Null}
do {$changed=$false;foreach($item in $all){if($owned.Contains([int]$item.ParentProcessId) -and $owned.Add([int]$item.ProcessId)){$changed=$true}}}while($changed)
$before=@{};foreach($taskId in $owned){$p=Get-Process -Id $taskId -ErrorAction SilentlyContinue;if($p){$before[$taskId]=$p.TotalProcessorTime.TotalSeconds}}
$watch=[Diagnostics.Stopwatch]::StartNew();Start-Sleep -Seconds $Seconds
$samples=@();$cpu=0.0
foreach($taskId in $owned){$p=Get-Process -Id $taskId -ErrorAction SilentlyContinue;if($p -and $before.ContainsKey($taskId)){$delta=[Math]::Max(0,$p.TotalProcessorTime.TotalSeconds-$before[$taskId]);$cpu+=$delta;$samples+=@{pid=$taskId;name=$p.ProcessName;workingSetBytes=$p.WorkingSet64;privateBytes=$p.PrivateMemorySize64;cpuSeconds=$delta}}}
@{elapsedSeconds=$watch.Elapsed.TotalSeconds;cpuPercentOneLogicalCore=100*$cpu/$watch.Elapsed.TotalSeconds;logicalProcessors=[Environment]::ProcessorCount;workingSetBytes=($samples|Measure-Object workingSetBytes -Sum).Sum;privateBytes=($samples|Measure-Object privateBytes -Sum).Sum;processes=$samples;scope='Owned browser/WebView tree and Core; sum of working sets counts shared pages multiple times'} | ConvertTo-Json -Depth 5
