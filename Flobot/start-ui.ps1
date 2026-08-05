$ErrorActionPreference = "Stop"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendPath = Join-Path $projectPath "frontend"

Set-Location -LiteralPath $frontendPath
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    Write-Host "首次运行：正在安装前端依赖……"
    & npm.cmd install --no-audit --no-fund
}

Write-Host "正在构建 Flobot 网页……"
& npm.cmd run build

Set-Location -LiteralPath $projectPath
Write-Host "正在启动原版 Python Flobot 和网页……"
$pythonExecutable = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonExecutable) {
    $pythonExecutable = Get-Command py -ErrorAction SilentlyContinue
}
if ($null -eq $pythonExecutable) {
    throw "未找到 Python。请先安装 Python 3.11 或更高版本。"
}
& $pythonExecutable.Source -m flobot.web_app
