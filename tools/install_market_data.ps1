$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VenvDir = Join-Path $RepoRoot ".venv-marketdata"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $VenvDir
    }
    elseif (Get-Command python3.12 -ErrorAction SilentlyContinue) {
        & python3.12 -m venv $VenvDir
    }
    else {
        throw "Python 3.12 is required. Install Python 3.12 x64, then rerun this script."
    }
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements-marketdata.txt")
if ($LASTEXITCODE -ne 0) { throw "Market-data package installation failed." }

& $VenvPython (Join-Path $RepoRoot "tools\check_marketdata_install.py")
if ($LASTEXITCODE -ne 0) { throw "Market-data import verification failed." }

Write-Host ""
Write-Host "Market-data environment is ready at: $VenvDir"
Write-Host "Use .venv-marketdata\Scripts\python.exe for market-data scripts."
Write-Host "Existing NIFTY dependencies and environment were not changed."
