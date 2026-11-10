param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z0-9]+$")]
    [string]$Instrument,

    [Parameter(Mandatory = $true)]
    [string]$FromDate,

    [Parameter(Mandatory = $true)]
    [string]$ToDate,

    [ValidateSet("tick", "s1", "m1", "m5", "m15", "m30", "h1", "h4", "d1", "mn1")]
    [string]$Timeframe = "m1",

    [ValidateSet("bid", "ask")]
    [string]$PriceType = "bid",

    [string]$OutputDir = "data/raw/dukascopy"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

try {
    $from = [DateTimeOffset]::Parse($FromDate)
    $to = [DateTimeOffset]::Parse($ToDate)
}
catch {
    throw "Use ISO dates, for example -FromDate 2024-01-01 -ToDate 2025-01-01."
}
if ($to -le $from) {
    throw "ToDate must be later than FromDate. ToDate is exclusive."
}

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$npxCommand = Get-Command npx -ErrorAction SilentlyContinue
if (-not $nodeCommand -or -not $npxCommand) {
    throw "Node.js 20+ is required for Dukascopy data. Install the current Node.js LTS from https://nodejs.org/, reopen PowerShell, and rerun this command."
}
$nodeVersion = (& node --version).Trim().TrimStart("v")
$nodeMajor = [int]($nodeVersion.Split(".")[0])
if ($nodeMajor -lt 20) {
    throw "Node.js 20+ is required; detected $nodeVersion. Upgrade from https://nodejs.org/."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$npxArgs = @(
    "--yes", "dukascopy-node@1.51.1",
    "-i", $Instrument.ToLowerInvariant(),
    "-from", $FromDate,
    "-to", $ToDate,
    "-t", $Timeframe,
    "-f", "csv",
    "-v",
    "--cache",
    "--retries", "3",
    "--batch-pause", "1500",
    "-dir", $OutputDir
)
if ($Timeframe -ne "tick") {
    $npxArgs += @("-p", $PriceType)
}

Write-Host "Downloading $Instrument $Timeframe from Dukascopy public quotes."
Write-Host "No API key or paid market-data subscription is used."
Write-Host "Source timestamps are UTC; end date is exclusive."
& $npxCommand.Source @npxArgs
if ($LASTEXITCODE -ne 0) {
    throw "dukascopy-node failed with exit code $LASTEXITCODE. Check the error above; Dukascopy may rate-limit or deny automated requests."
}
