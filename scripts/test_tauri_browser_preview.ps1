[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = Join-Path $repositoryRoot 'desktop\src-tauri'
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$manifestTool = Get-ChildItem -LiteralPath $sdkRoot -Directory |
    Sort-Object Name -Descending |
    ForEach-Object { Join-Path $_.FullName 'x64\mt.exe' } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $manifestTool) { throw 'Windows SDK mt.exe is required to run the native test harness.' }

$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('smarti-preview-harness-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
$manifestPath = Join-Path $testRoot 'native-test.manifest'
# Cargo's unit-test executable lacks the Common Controls v6 manifest that the
# production Tauri executable embeds. TaskDialogIndirect needs that manifest.
$manifest = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <dependency><dependentAssembly>
    <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*" />
  </dependentAssembly></dependency>
</assembly>
'@
[IO.File]::WriteAllText($manifestPath, $manifest, [Text.UTF8Encoding]::new($false))
Push-Location $nativeRoot
try {
    $output = & cargo test --lib --features native-preview-test --no-run --message-format=json
    if ($LASTEXITCODE -ne 0) { throw 'Native preview test compilation failed.' }
    $artifacts = $output | Where-Object { $_.StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json }
    $executable = $artifacts | Where-Object { $_.reason -eq 'compiler-artifact' -and $_.profile.test -and $_.executable } |
        Select-Object -Last 1 -ExpandProperty executable
    if (-not $executable) { throw 'Cargo did not return the native test executable.' }
    & $manifestTool -nologo -manifest $manifestPath "-outputresource:$executable;#1"
    if ($LASTEXITCODE -ne 0) { throw 'Could not add the native test harness manifest.' }
    & $executable browser::tests::native_collapsed_preview_updates_and_closes --ignored --nocapture --test-threads=1
    if ($LASTEXITCODE -ne 0) { throw 'Native browser preview regression failed.' }
} finally {
    Pop-Location
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTestRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
