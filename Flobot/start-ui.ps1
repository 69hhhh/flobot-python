$ErrorActionPreference = "Stop"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendPath = Join-Path $projectPath "frontend"

Set-Location -LiteralPath $frontendPath
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    Write-Host "First run: installing frontend dependencies..."
    & npm.cmd install --no-audit --no-fund
}

Write-Host "Building the Flobot web UI..."
& npm.cmd run build

Set-Location -LiteralPath $projectPath
Write-Host "Starting the original Python Flobot and web UI..."
if ($null -ne (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    python -m flobot.web_app
    exit $LASTEXITCODE
}
if ($null -ne (Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    py -3 -m flobot.web_app
    exit $LASTEXITCODE
}

throw "Python was not found. Install Python 3.11 or newer first."
