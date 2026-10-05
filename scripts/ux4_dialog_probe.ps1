param([Parameter(Mandatory)][int]$ProbeProcessId, [long]$CancelHandle = 0)
$ErrorActionPreference = 'Stop'
if ([IO.Path]::GetFileName((Get-Process -Id $ProbeProcessId).Path) -ne 'ux4-native.exe') { throw 'Only the isolated UX-4 probe is permitted.' }
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Ux4Dialog {
  public delegate bool Visitor(IntPtr window, IntPtr data);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Visitor visitor, IntPtr data);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr window,uint command);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr window,StringBuilder text,int size);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr window,StringBuilder text,int size);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr window,uint message,IntPtr wparam,IntPtr lparam);
}
'@
$script:dialogs = @()
[Ux4Dialog]::EnumWindows({ param($window,$data)
  [uint32]$owner = 0
  [Ux4Dialog]::GetWindowThreadProcessId($window,[ref]$owner) | Out-Null
  $ancestor = [Ux4Dialog]::GetWindow($window,4)
  $belongs = $owner -eq $ProbeProcessId
  for ($i=0; $i -lt 8 -and $ancestor -ne [IntPtr]::Zero; $i++) {
    [uint32]$ancestorPid=0
    [Ux4Dialog]::GetWindowThreadProcessId($ancestor,[ref]$ancestorPid) | Out-Null
    if ($ancestorPid -eq $ProbeProcessId) { $belongs=$true; break }
    $ancestor=[Ux4Dialog]::GetWindow($ancestor,4)
  }
  if ($belongs -and [Ux4Dialog]::IsWindowVisible($window)) {
    $title=[Text.StringBuilder]::new(512);$className=[Text.StringBuilder]::new(256)
    [Ux4Dialog]::GetWindowText($window,$title,512) | Out-Null
    [Ux4Dialog]::GetClassName($window,$className,256) | Out-Null
    $script:dialogs += @{handle=$window.ToInt64();process=$owner;title=$title.ToString();className=$className.ToString();owner=[Ux4Dialog]::GetWindow($window,4).ToInt64()}
  }
  return $true
},[IntPtr]::Zero) | Out-Null
if ($CancelHandle) {
  $target=$script:dialogs | Where-Object { $_.handle -eq $CancelHandle -and $_.title -notmatch '^SmartiAI( \([0-9]+\))?$' }
  if (-not $target) { throw 'Refusing to close a window outside the verified QA dialog.' }
  if (-not [Ux4Dialog]::PostMessage([IntPtr]$CancelHandle,0x10,[IntPtr]::Zero,[IntPtr]::Zero)) { throw 'Cancel failed.' }
}
ConvertTo-Json -InputObject @($script:dialogs) -Compress
