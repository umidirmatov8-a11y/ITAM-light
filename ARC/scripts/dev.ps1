<#
  Development run: creates backend\.venv, installs dependencies (first time), starts Vite + Electron.
  Usage:  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 [-Mock]
  -Mock   simulate all system actions (nothing is launched or changed on this PC).
#>
param([switch]$Mock)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$app = Join-Path $root 'app'
$venvPy = Join-Path $backend '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPy)) {
    Write-Host 'Creating backend virtual environment...' -ForegroundColor Cyan
    & py -3.12 -m venv (Join-Path $backend '.venv')
    if ($LASTEXITCODE -ne 0) { & python -m venv (Join-Path $backend '.venv') }
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r (Join-Path $backend 'requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
}
if (-not (Test-Path (Join-Path $app 'node_modules'))) {
    Write-Host 'Installing npm packages...' -ForegroundColor Cyan
    Push-Location $app; npm ci; $code = $LASTEXITCODE; Pop-Location
    if ($code -ne 0) { throw 'npm ci failed' }
}
if ($Mock) { $env:ARC_BACKEND_MOCK = '1' }
Push-Location $app
try { npm run dev } finally { Pop-Location }
