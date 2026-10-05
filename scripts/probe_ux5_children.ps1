param([Parameter(Mandatory)][int]$ProbeProcessId)
$ErrorActionPreference='Stop'
$probe=Get-Process -Id $ProbeProcessId
if([IO.Path]::GetFileName($probe.Path) -ne 'ux5-native.exe'){throw 'Unexpected QA process'}
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Ux5Children {
 public delegate bool Visitor(IntPtr window,IntPtr data);
 [StructLayout(LayoutKind.Sequential)] public struct Rect {public int left,top,right,bottom;}
 [DllImport("user32.dll")] public static extern bool EnumWindows(Visitor visitor,IntPtr data);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr window,Visitor visitor,IntPtr data);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr window,StringBuilder text,int size);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr window,StringBuilder text,int size);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr window,out Rect rect);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
 [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
}
'@
[Ux5Children]::SetThreadDpiAwarenessContext([IntPtr](-4)) | Out-Null
$script:rows=[Collections.Generic.List[object]]::new()
[Ux5Children]::EnumWindows({param($window,$data)
 [uint32]$owner=0;[Ux5Children]::GetWindowThreadProcessId($window,[ref]$owner)|Out-Null
 if($owner -ne $ProbeProcessId){return $true}
 $title=[Text.StringBuilder]::new(256);[Ux5Children]::GetWindowText($window,$title,256)|Out-Null
 if($title.ToString() -notmatch '^SmartiAI( \([0-9]+\))?$'){return $true}
 [Ux5Children]::EnumChildWindows($window,{param($child,$unused)
  $name=[Text.StringBuilder]::new(256);[Ux5Children]::GetClassName($child,$name,256)|Out-Null
  if($name.ToString() -eq 'Chrome_WidgetWin_0'){
   $rect=[Ux5Children+Rect]::new();[Ux5Children]::GetWindowRect($child,[ref]$rect)|Out-Null
   $script:rows.Add(@{handle=$child.ToInt64();x=$rect.left;y=$rect.top;width=$rect.right-$rect.left;height=$rect.bottom-$rect.top;visible=[Ux5Children]::IsWindowVisible($child)})
  }
  return $true
 },[IntPtr]::Zero)|Out-Null
 return $true
},[IntPtr]::Zero)|Out-Null
ConvertTo-Json -InputObject @($script:rows.ToArray()) -Compress
