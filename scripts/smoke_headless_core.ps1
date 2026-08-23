[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
& python (Join-Path $repoRoot "smarti_core_service.py") --smoke
if ($LASTEXITCODE -ne 0) {
    throw "Headless Smarti Core smoke failed with exit code $LASTEXITCODE"
}
