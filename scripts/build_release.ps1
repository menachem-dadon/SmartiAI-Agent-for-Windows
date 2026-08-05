[CmdletBinding()]
param(
    [string]$Version,
    [switch]$Clean,
    [switch]$SkipRuntime,
    [switch]$SkipInstaller,
    [switch]$ForceRuntime
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

function Resolve-DefaultWorkRoot {
    if ($env:SMARTI_BUILD_WORK_DIR) { return $env:SMARTI_BUILD_WORK_DIR }
    $drive = if ($env:SystemDrive) { $env:SystemDrive } else { "C:" }
    $shortCandidate = Join-Path $drive "SmartiAI-build"
    try {
        New-Item -ItemType Directory -Force -Path $shortCandidate | Out-Null
        $probe = Join-Path $shortCandidate ".write-test"
        Set-Content -LiteralPath $probe -Value "ok" -Encoding ASCII
        Remove-Item -LiteralPath $probe -Force
        return $shortCandidate
    } catch {
        return (Join-Path ([System.IO.Path]::GetTempPath()) "SmartiAI-Agent-build")
    }
}

$WorkRoot = Resolve-DefaultWorkRoot
$WorkRoot = [System.IO.Path]::GetFullPath($WorkRoot)
$BuildDir = Join-Path $WorkRoot "build"
$DistRoot = Join-Path $WorkRoot "dist"
$DistDir = Join-Path $DistRoot "SmartiAI"
$ReleaseDir = Join-Path $RepoRoot "release"
$BuildVenv = Join-Path $WorkRoot ".venv-build"
$RuntimeDir = Join-Path $BuildDir "runtime"
$DownloadCacheDir = Join-Path $WorkRoot ".download-cache"
$PyInstallerWorkDir = Join-Path $WorkRoot "pyinstaller-work"
$InstallerRelativePathBudget = 190

function Get-SafeVersion {
    param([string]$Raw)
    if (-not $Raw) { return "dev" }
    $value = $Raw.Trim()
    if ($value.StartsWith("v", [System.StringComparison]::OrdinalIgnoreCase)) { $value = $value.Substring(1) }
    $value = $value -replace "[^A-Za-z0-9_.-]+", "-"
    if (-not $value) { return "dev" }
    return $value
}

function Resolve-ReleaseVersion {
    if ($Version) { return (Get-SafeVersion $Version) }
    try {
        $tag = (& git -C $RepoRoot describe --tags --always --dirty 2>$null)
        if ($LASTEXITCODE -eq 0 -and "$tag".Trim()) { return (Get-SafeVersion "$tag") }
    } catch {
    }
    return "dev"
}

function Get-AppVersionFromSource {
    $commonPath = Join-Path $RepoRoot "smarti\common.py"
    $line = Select-String -LiteralPath $commonPath -Pattern '^\s*APP_VERSION\s*=\s*["'']([^"'']+)["'']' | Select-Object -First 1
    if (-not $line -or -not $line.Matches.Count) {
        throw "Could not read APP_VERSION from $commonPath"
    }
    return (Get-SafeVersion $line.Matches[0].Groups[1].Value)
}

function Assert-AppVersionMatchesRelease {
    param([Parameter(Mandatory = $true)][string]$ReleaseVersion)
    if ($ReleaseVersion -notmatch '^\d+(?:\.\d+){1,3}(?:[-_.][A-Za-z0-9]+)?$') {
        Write-Warning "Skipping APP_VERSION sync check for non-release version '$ReleaseVersion'."
        return
    }
    $appVersion = Get-AppVersionFromSource
    if ($appVersion -ne $ReleaseVersion) {
        throw "APP_VERSION mismatch. smarti\common.py has $appVersion, but this build is $ReleaseVersion."
    }
    Write-Host "APP_VERSION sync OK: $appVersion"
}

function Resolve-HostPython {
    if ($env:SMARTI_BUILD_PYTHON -and (Test-Path $env:SMARTI_BUILD_PYTHON)) {
        return $env:SMARTI_BUILD_PYTHON
    }
    $probe = "import sys; print(sys.executable)"
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        try {
            $cmd = $candidate.Command
            $args = @($candidate.Args) + @("-c", $probe)
            $out = & $cmd @args 2>$null
            if ($LASTEXITCODE -eq 0 -and "$out".Trim()) {
                return "$out".Trim()
            }
        } catch {
        }
    }
    throw "Could not find a host Python. Install Python 3.12 or set SMARTI_BUILD_PYTHON."
}

function Find-InnoSetup {
    $cmd = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @()
    if (${env:ProgramFiles(x86)}) { $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe" }
    if ($env:ProgramFiles) { $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe" }
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $pathFull = [System.IO.Path]::GetFullPath($Path)
    $rootUri = [System.Uri]::new($rootFull)
    $pathUri = [System.Uri]::new($pathFull)
    return [System.Uri]::UnescapeDataString($rootUri.MakeRelativeUri($pathUri).ToString()).Replace('/', '\')
}

function Assert-ReleaseLayout {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string[]]$RequiredRelativePaths
    )
    foreach ($relative in $RequiredRelativePaths) {
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Release layout is missing required file or directory: $relative"
        }
    }
}

function Assert-PathInside {
    param(
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Child,
        [string]$Description = "path"
    )
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $childFull = [System.IO.Path]::GetFullPath($Child)
    if (-not $childFull.StartsWith($parentFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate on $Description outside expected root. Root: $parentFull Path: $childFull"
    }
}

function Assert-AssetSync {
    param(
        [Parameter(Mandatory = $true)][string]$SourceAssetsDir,
        [Parameter(Mandatory = $true)][string]$DestinationAssetsDir
    )
    if (-not (Test-Path -LiteralPath $SourceAssetsDir)) {
        throw "Missing source assets directory: $SourceAssetsDir"
    }
    if (-not (Test-Path -LiteralPath $DestinationAssetsDir)) {
        throw "Missing release assets directory: $DestinationAssetsDir"
    }

    $sourceFiles = @(Get-ChildItem -LiteralPath $SourceAssetsDir -Recurse -File)
    $destinationFiles = @(Get-ChildItem -LiteralPath $DestinationAssetsDir -Recurse -File)
    $sourceByRelative = @{}
    foreach ($file in $sourceFiles) {
        $relative = Get-RelativePath -Root $SourceAssetsDir -Path $file.FullName
        $sourceByRelative[$relative] = $file
    }
    $destinationByRelative = @{}
    foreach ($file in $destinationFiles) {
        $relative = Get-RelativePath -Root $DestinationAssetsDir -Path $file.FullName
        $destinationByRelative[$relative] = $file
    }

    $problems = New-Object System.Collections.Generic.List[string]
    foreach ($relative in ($sourceByRelative.Keys | Sort-Object)) {
        if (-not $destinationByRelative.ContainsKey($relative)) {
            $problems.Add("missing: $relative")
            continue
        }
        $sourceFile = $sourceByRelative[$relative]
        $destinationFile = $destinationByRelative[$relative]
        if ($sourceFile.Length -ne $destinationFile.Length) {
            $problems.Add("size mismatch: $relative")
            continue
        }
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile.FullName).Hash
        $destinationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationFile.FullName).Hash
        if ($sourceHash -ne $destinationHash) {
            $problems.Add("hash mismatch: $relative")
        }
    }
    foreach ($relative in ($destinationByRelative.Keys | Sort-Object)) {
        if (-not $sourceByRelative.ContainsKey($relative)) {
            $problems.Add("extra: $relative")
        }
    }

    if ($problems.Count -gt 0) {
        $details = ($problems | Select-Object -First 40) -join [Environment]::NewLine
        if ($problems.Count -gt 40) {
            $details += [Environment]::NewLine + "... $($problems.Count - 40) more asset sync problems"
        }
        throw "Release assets are not synchronized with source assets.$([Environment]::NewLine)$details"
    }
    Write-Host "Asset sync OK: $($sourceFiles.Count) files copied to release layout."
}

function Sync-ReleaseAssets {
    param(
        [Parameter(Mandatory = $true)][string]$SourceAssetsDir,
        [Parameter(Mandatory = $true)][string]$DistDir
    )
    $internalDir = Join-Path $DistDir "_internal"
    $destinationAssetsDir = Join-Path $internalDir "assets"
    Assert-PathInside -Parent $DistDir -Child $destinationAssetsDir -Description "release assets directory"
    if (-not (Test-Path -LiteralPath $SourceAssetsDir)) {
        throw "Missing source assets directory: $SourceAssetsDir"
    }
    New-Item -ItemType Directory -Force -Path $internalDir | Out-Null
    if (Test-Path -LiteralPath $destinationAssetsDir) {
        Remove-Item -LiteralPath $destinationAssetsDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $destinationAssetsDir | Out-Null
    Copy-Item -Path (Join-Path $SourceAssetsDir "*") -Destination $destinationAssetsDir -Recurse -Force
    Assert-AssetSync -SourceAssetsDir $SourceAssetsDir -DestinationAssetsDir $destinationAssetsDir
}

function Assert-InstallerPathBudget {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [int]$MaxRelativeLength = 190
    )
    $longest = Get-ChildItem -LiteralPath $Root -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            $relative = Get-RelativePath -Root $Root -Path $_.FullName
            [pscustomobject]@{ Length = $relative.Length; RelativePath = $relative }
        } |
        Sort-Object Length -Descending |
        Select-Object -First 10
    $tooLong = @($longest | Where-Object { $_.Length -gt $MaxRelativeLength })
    if ($tooLong.Count -gt 0) {
        $details = ($tooLong | ForEach-Object { "$($_.Length): $($_.RelativePath)" }) -join [Environment]::NewLine
        throw "Installer path budget exceeded. Prune packaging-only runtime files or shorten paths before building the installer. Limit: $MaxRelativeLength relative characters.$([Environment]::NewLine)$details"
    }
    $top = $longest | Select-Object -First 1
    if ($top) {
        Write-Host "Installer path budget OK: longest relative path is $($top.Length)/$MaxRelativeLength characters."
    }
}

$ReleaseVersion = Resolve-ReleaseVersion
Write-Host "Building SmartiAI release $ReleaseVersion"
Assert-AppVersionMatchesRelease -ReleaseVersion $ReleaseVersion

if ($Clean) {
    foreach ($path in @($BuildDir, $DistRoot, $BuildVenv, $DownloadCacheDir, $PyInstallerWorkDir, $ReleaseDir, (Join-Path $RepoRoot "build"), (Join-Path $RepoRoot "dist"), (Join-Path $RepoRoot ".venv-build"))) {
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

New-Item -ItemType Directory -Force -Path $BuildDir, $ReleaseDir, $WorkRoot | Out-Null

$HostPython = Resolve-HostPython
Write-Host "Host Python: $HostPython"

if (-not (Test-Path (Join-Path $BuildVenv "Scripts\python.exe"))) {
    Invoke-Checked -FilePath $HostPython -Arguments @("-m", "venv", $BuildVenv)
}
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $RepoRoot "requirements.txt"), "-r", (Join-Path $RepoRoot "requirements-build.txt"))
Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "check")
Invoke-Checked -FilePath $VenvPython -Arguments @("-c", "import pymupdf, fitz; print('PyMuPDF visual-QA dependency:', pymupdf.__version__)")

if (-not $SkipRuntime) {
    $prepareArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $RepoRoot "scripts\prepare_runtime.ps1"),
        "-RuntimeDir", $RuntimeDir,
        "-CacheDir", $DownloadCacheDir
    )
    if ($ForceRuntime) { $prepareArgs += "-Force" }
    Invoke-Checked -FilePath "powershell.exe" -Arguments $prepareArgs
} elseif (-not (Test-Path $RuntimeDir)) {
    throw "Runtime was skipped, but $RuntimeDir does not exist."
}

Push-Location $RepoRoot
try {
    Invoke-Checked -FilePath $VenvPython -Arguments @(
        "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--workpath", $PyInstallerWorkDir,
        "--distpath", $DistRoot,
        (Join-Path $RepoRoot "packaging\smarti.spec")
    )
} finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $DistDir "SmartiAI.exe"))) {
    throw "PyInstaller output is missing SmartiAI.exe in $DistDir"
}

Sync-ReleaseAssets -SourceAssetsDir (Join-Path $RepoRoot "assets") -DistDir $DistDir

$DistRuntime = Join-Path $DistDir "runtime"
if (Test-Path $DistRuntime) { Remove-Item -LiteralPath $DistRuntime -Recurse -Force }
New-Item -ItemType Directory -Force -Path $DistRuntime | Out-Null
Copy-Item -Path (Join-Path $RuntimeDir "*") -Destination $DistRuntime -Recurse -Force

Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination $DistDir -Force
Copy-Item -LiteralPath (Join-Path $RepoRoot "README.md") -Destination $DistDir -Force

$gitCommit = ""
try {
    $gitCommit = (& git -C $RepoRoot rev-parse --short HEAD 2>$null)
} catch {
}

$manifest = [ordered]@{
    version = $ReleaseVersion
    builtAt = (Get-Date).ToUniversalTime().ToString("o")
    gitCommit = "$gitCommit".Trim()
    appExe = "SmartiAI.exe"
    runtime = "runtime"
    pythonExe = "runtime\python\python.exe"
    nodeExe = "runtime\node\node.exe"
    npxExe = "runtime\node\npx.cmd"
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $DistDir "release_manifest.json") -Encoding UTF8

Assert-ReleaseLayout -Root $DistDir -RequiredRelativePaths @(
    "SmartiAI.exe",
    "_internal\assets\smarti.ico",
    "LICENSE",
    "README.md",
    "release_manifest.json",
    "runtime\runtime_manifest.json",
    "runtime\python\python.exe",
    "runtime\node\node.exe",
    "runtime\node\npx.cmd"
)
Assert-InstallerPathBudget -Root $DistDir -MaxRelativeLength $InstallerRelativePathBudget

$zipPath = Join-Path $ReleaseDir "SmartiAI-Agent-for-Windows-$ReleaseVersion-win-x64-portable.zip"
if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -LiteralPath $DistDir -DestinationPath $zipPath -Force
Write-Host "Portable package: $zipPath"

if (-not $SkipInstaller) {
    $iscc = Find-InnoSetup
    if ($iscc) {
        $iss = Join-Path $RepoRoot "packaging\smarti.iss"
        $sourceDefine = "/DSourceDir=$DistDir"
        $outputDefine = "/DOutputDir=$ReleaseDir"
        $versionDefine = "/DMyAppVersion=$ReleaseVersion"
        $iconDefine = "/DIconFile=$(Join-Path $RepoRoot 'assets\smarti.ico')"
        Invoke-Checked -FilePath $iscc -Arguments @($sourceDefine, $outputDefine, $versionDefine, $iconDefine, $iss)
        Write-Host "Installer output directory: $ReleaseDir"
    } else {
        Write-Warning "Inno Setup (ISCC.exe) was not found. Portable ZIP was created; install Inno Setup 6 to also build the setup EXE."
    }
}

Write-Host "Release build complete."
