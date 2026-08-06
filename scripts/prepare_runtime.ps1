[CmdletBinding()]
param(
    [string]$RuntimeDir,
    [string]$ConfigPath,
    [string]$CacheDir,
    [switch]$Force,
    [switch]$SkipRequirements
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
if (-not $RuntimeDir) { $RuntimeDir = Join-Path $RepoRoot "build\runtime" }
if (-not $ConfigPath) { $ConfigPath = Join-Path $RepoRoot "packaging\runtime-versions.json" }
if (-not $CacheDir) { $CacheDir = Join-Path $RepoRoot ".build-cache" }

$RuntimeDir = [System.IO.Path]::GetFullPath($RuntimeDir)
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$CacheDir = [System.IO.Path]::GetFullPath($CacheDir)

function Get-ConfigValue {
    param($Object, [string]$Name, [string]$Fallback = "")
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) {
        $value = $Object.$Name
        if ($null -ne $value -and "$value".Trim()) { return "$value" }
    }
    return $Fallback
}

function Invoke-Download {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$OutFile,
        [string]$Sha256 = ""
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
    if (-not (Test-Path $OutFile)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
    } else {
        Write-Host "Using cached $OutFile"
    }
    if ($Sha256) {
        $actual = (Get-FileHash -Algorithm SHA256 -Path $OutFile).Hash.ToLowerInvariant()
        if ($actual -ne $Sha256.ToLowerInvariant()) {
            throw "SHA256 mismatch for $OutFile. Expected $Sha256, got $actual."
        }
    }
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

function Reset-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Expand-CleanZip {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    Reset-Directory $Destination
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
}

function Enable-EmbeddedPythonSite {
    param([Parameter(Mandatory = $true)][string]$PythonDir)
    $pth = Get-ChildItem -LiteralPath $PythonDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $pth) { throw "Could not find python*._pth in $PythonDir" }

    $lines = Get-Content -LiteralPath $pth.FullName
    $updated = New-Object System.Collections.Generic.List[string]
    $hasImportSite = $false
    $hasSitePackages = $false

    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "#import site" -or $trimmed -eq "import site") {
            $updated.Add("import site")
            $hasImportSite = $true
            continue
        }
        if ($trimmed -ieq "Lib\site-packages") { $hasSitePackages = $true }
        $updated.Add($line)
    }

    if (-not $hasSitePackages) { $updated.Insert([Math]::Max(0, $updated.Count - 1), "Lib\site-packages") }
    if (-not $hasImportSite) { $updated.Add("import site") }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($pth.FullName, [string[]]$updated, $utf8NoBom)
    New-Item -ItemType Directory -Force -Path (Join-Path $PythonDir "Lib\site-packages") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $PythonDir "Scripts") | Out-Null
}

function Copy-SiteCustomize {
    param([Parameter(Mandatory = $true)][string]$PythonDir)
    $source = Join-Path $RepoRoot "sitecustomize.py"
    $targetDir = Join-Path $PythonDir "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $targetDir "sitecustomize.py") -Force
}

function Remove-PathIfExists {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
        Write-Host "Pruned packaging-only runtime path: $Path"
    }
}

function Optimize-PythonRuntimeForPackaging {
    param([Parameter(Mandatory = $true)][string]$PythonDir)
    $sitePackages = Join-Path $PythonDir "Lib\site-packages"
    if (-not (Test-Path -LiteralPath $sitePackages)) { return }

    $pruneRelativeDirs = @(
        "litellm\proxy\guardrails\guardrail_hooks\litellm_content_filter\guardrail_benchmarks",
        "litellm\proxy\_experimental\out"
    )
    foreach ($relative in $pruneRelativeDirs) {
        Remove-PathIfExists -Path (Join-Path $sitePackages $relative)
    }

    Get-ChildItem -LiteralPath $sitePackages -Directory -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $sitePackages -File -Filter "*.pyc" -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
    Get-ChildItem -LiteralPath $sitePackages -File -Filter "*.pyo" -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
}

function Install-PythonPackages {
    param(
        [Parameter(Mandatory = $true)][string]$PythonExe,
        [Parameter(Mandatory = $true)]$Config
    )
    $requirements = Join-Path $RepoRoot "requirements.txt"
    Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "install", "--upgrade", "--no-cache-dir", "pip", "setuptools", "wheel")
    Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "install", "--no-cache-dir", "-r", $requirements)
    $extra = @()
    if ($Config.PSObject.Properties.Name -contains "extraPythonPackages") {
        $extra = @($Config.extraPythonPackages)
    }
    foreach ($package in $extra) {
        if ("$package".Trim()) {
            Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "install", "--no-cache-dir", "$package")
        }
    }
    Invoke-Checked -FilePath $PythonExe -Arguments @("-m", "pip", "check")
}

function Prepare-PythonRuntime {
    param($Config)
    $pythonVersion = if ($env:SMARTI_PYTHON_VERSION) { $env:SMARTI_PYTHON_VERSION } else { Get-ConfigValue $Config.python "version" }
    $pythonUrl = if ($env:SMARTI_PYTHON_URL) { $env:SMARTI_PYTHON_URL } else { Get-ConfigValue $Config.python "url" }
    $pythonSha = if ($env:SMARTI_PYTHON_SHA256) { $env:SMARTI_PYTHON_SHA256 } else { Get-ConfigValue $Config.python "sha256" }
    if (-not $pythonVersion -or -not $pythonUrl) { throw "Python runtime version/url is missing." }

    $zipPath = Join-Path $CacheDir "python-$pythonVersion-embed-amd64.zip"
    $pythonDir = Join-Path $RuntimeDir "python"
    Invoke-Download -Url $pythonUrl -OutFile $zipPath -Sha256 $pythonSha
    if ($Force -or -not (Test-Path (Join-Path $pythonDir "python.exe"))) {
        Expand-CleanZip -ZipPath $zipPath -Destination $pythonDir
    }
    Enable-EmbeddedPythonSite -PythonDir $pythonDir

    $pythonExe = Join-Path $pythonDir "python.exe"
    $pipOk = $false
    try {
        & $pythonExe -m pip --version | Out-Null
        if ($LASTEXITCODE -eq 0) { $pipOk = $true }
    } catch {
        $pipOk = $false
    }
    if (-not $pipOk) {
        $getPipUrl = if ($env:SMARTI_GET_PIP_URL) { $env:SMARTI_GET_PIP_URL } else { Get-ConfigValue $Config.getPip "url" "https://bootstrap.pypa.io/get-pip.py" }
        $getPipSha = if ($env:SMARTI_GET_PIP_SHA256) { $env:SMARTI_GET_PIP_SHA256 } else { Get-ConfigValue $Config.getPip "sha256" }
        $getPipPath = Join-Path $CacheDir "get-pip.py"
        Invoke-Download -Url $getPipUrl -OutFile $getPipPath -Sha256 $getPipSha
        Invoke-Checked -FilePath $pythonExe -Arguments @($getPipPath, "--no-warn-script-location")
    }

    Copy-SiteCustomize -PythonDir $pythonDir
    if (-not $SkipRequirements) {
        Install-PythonPackages -PythonExe $pythonExe -Config $Config
    }
    Optimize-PythonRuntimeForPackaging -PythonDir $pythonDir
    Invoke-Checked -FilePath $pythonExe -Arguments @("--version")
    Invoke-Checked -FilePath $pythonExe -Arguments @("-m", "pip", "--version")
}

function Prepare-NodeRuntime {
    param($Config)
    $nodeVersion = if ($env:SMARTI_NODE_VERSION) { $env:SMARTI_NODE_VERSION } else { Get-ConfigValue $Config.node "version" }
    $nodeUrl = if ($env:SMARTI_NODE_URL) { $env:SMARTI_NODE_URL } else { Get-ConfigValue $Config.node "url" }
    $nodeSha = if ($env:SMARTI_NODE_SHA256) { $env:SMARTI_NODE_SHA256 } else { Get-ConfigValue $Config.node "sha256" }
    if (-not $nodeVersion -or -not $nodeUrl) { throw "Node runtime version/url is missing." }

    $zipPath = Join-Path $CacheDir "node-v$nodeVersion-win-x64.zip"
    $nodeDir = Join-Path $RuntimeDir "node"
    Invoke-Download -Url $nodeUrl -OutFile $zipPath -Sha256 $nodeSha
    if ($Force -or -not (Test-Path (Join-Path $nodeDir "node.exe"))) {
        $tempDir = Join-Path $CacheDir "node-extract-$nodeVersion"
        Expand-CleanZip -ZipPath $zipPath -Destination $tempDir
        Reset-Directory $nodeDir
        $nodeRoot = Get-ChildItem -LiteralPath $tempDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName "node.exe") } | Select-Object -First 1
        if ($nodeRoot) {
            Copy-Item -Path (Join-Path $nodeRoot.FullName "*") -Destination $nodeDir -Recurse -Force
        } elseif (Test-Path (Join-Path $tempDir "node.exe")) {
            Copy-Item -Path (Join-Path $tempDir "*") -Destination $nodeDir -Recurse -Force
        } else {
            throw "Could not locate node.exe in extracted Node archive."
        }
    }
    Invoke-Checked -FilePath (Join-Path $nodeDir "node.exe") -Arguments @("--version")
    Invoke-Checked -FilePath (Join-Path $nodeDir "npx.cmd") -Arguments @("--version")
}

if (-not (Test-Path $ConfigPath)) { throw "Missing runtime config: $ConfigPath" }
$config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

Prepare-PythonRuntime -Config $config
Prepare-NodeRuntime -Config $config

$manifest = [ordered]@{
    createdAt = (Get-Date).ToUniversalTime().ToString("o")
    pythonVersion = Get-ConfigValue $config.python "version"
    nodeVersion = Get-ConfigValue $config.node "version"
    layout = "runtime/python + runtime/node"
    notes = "Python and Node are private to Smarti packaged builds. Dynamic MCP downloads use the user npm cache; Skills may install Python/uv packages through this runtime."
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $RuntimeDir "runtime_manifest.json") -Encoding UTF8
Write-Host "Runtime ready: $RuntimeDir"
