param([Parameter(Mandatory)][int]$ProbeProcessId, [Parameter(Mandatory)][int]$Width, [Parameter(Mandatory)][int]$Height, [long]$ProbeWindowHandle = 0)
$ErrorActionPreference = 'Stop'
$probe = Get-Process -Id $ProbeProcessId
if ([IO.Path]::GetFileName($probe.Path) -ne 'ux4-native.exe') { throw 'Only the isolated UX-4 native probe can be resized.' }
if ($Width -lt 360 -or $Width -gt 1920 -or $Height -lt 320 -or $Height -gt 1200) { throw 'QA dimensions outside the intended range.' }
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Ux4Window {
  [StructLayout(LayoutKind.Sequential)] public struct Rect { public int left, top, right, bottom; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr window,out Rect rect);
  public delegate bool Visitor(IntPtr window, IntPtr data);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Visitor visitor, IntPtr data);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr window, StringBuilder text, int size);
  [DllImport("user32.dll")] public static extern uint GetDpiForWindow(IntPtr window);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr window,int command);
  [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr window,StringBuilder text,int size);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr window,int x,int y,int width,int height,bool repaint);
}
'@
[Ux4Window]::SetThreadDpiAwarenessContext([IntPtr](-4)) | Out-Null
$script:qaArea = 0
$script:qaWindow = [IntPtr]::Zero
[Ux4Window]::EnumWindows({ param($window, $data)
  [uint32]$owner = 0
  [Ux4Window]::GetWindowThreadProcessId($window, [ref]$owner) | Out-Null
  if ($owner -eq $ProbeProcessId) {
    $title = [Text.StringBuilder]::new(256)
    [Ux4Window]::GetWindowText($window, $title, 256) | Out-Null
    if ($title.ToString() -match '^SmartiAI( \([0-9]+\))?$' -and ($ProbeWindowHandle -eq 0 -or $window.ToInt64() -eq $ProbeWindowHandle)) {
      $className=[Text.StringBuilder]::new(256);[Ux4Window]::GetClassName($window,$className,256) | Out-Null
      if ($className.ToString() -notlike '*Chrome*') {
        $candidate=[Ux4Window+Rect]::new();[Ux4Window]::GetClientRect($window,[ref]$candidate) | Out-Null
        $area=$candidate.right*$candidate.bottom
        if ($area -gt $script:qaArea) { $script:qaWindow=$window; $script:qaArea=$area }
      }
    }
  }
  return $true
}, [IntPtr]::Zero) | Out-Null
if ($script:qaWindow -eq [IntPtr]::Zero) { throw 'The probe main window was not found.' }
[Ux4Window]::ShowWindow($script:qaWindow,9) | Out-Null
[Ux4Window]::ShowWindow($script:qaWindow,4) | Out-Null
$scale = [Ux4Window]::GetDpiForWindow($script:qaWindow) / 96.0
if (-not [Ux4Window]::MoveWindow($script:qaWindow, 0, 0, [int]($Width * $scale), [int]($Height * $scale), $true)) { throw 'Probe resize failed.' }

$taskRect = [Ux4Window+Rect]::new()
[Ux4Window]::GetClientRect($script:qaWindow,[ref]$taskRect) | Out-Null
@{physicalWidth=$taskRect.right;physicalHeight=$taskRect.bottom;scale=$scale;window=$script:qaWindow.ToInt64()} | ConvertTo-Json -Compress
