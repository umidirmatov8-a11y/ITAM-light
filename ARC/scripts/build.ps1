<#
  Full build of the Windows installer.
    1. backend: venv, dependencies, pyflakes, pytest, PyInstaller onedir, EXE self-test
    2. app:     npm ci, typecheck, vitest, Vite + tsc build, electron-builder (NSIS)
  Result:  app\release\ARC-Setup-<version>.exe
  Usage:   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-SkipTests]
#>
param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$app = Join-Path $root 'app'

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "$exe $($arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

# ---------------------------------------------------------------- backend
Push-Location $backend
try {
    $venvPy = Join-Path $backend '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPy)) {
        Step 'Creating backend venv'
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { Run python @('-m', 'venv', '.venv') }
    }
    Step 'Installing backend dependencies'
    Run $venvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', 'requirements-dev.txt')
    if (-not $SkipTests) {
        Step 'pyflakes'
        Run $venvPy @('-m', 'pyflakes', 'arc_backend', 'tests')
        Step 'pytest'
        New-Item -ItemType Directory -Force -Path build | Out-Null
        Run $venvPy @('-m', 'pytest', 'tests', '-q', '-p', 'no:warnings', '--junitxml=build\test-results.xml')
    }
    Step 'PyInstaller'
    Run $venvPy @('-m', 'PyInstaller', '--noconfirm', '--clean', '--log-level', 'WARN', 'arc-backend.spec')
    Step 'Backend EXE self-test'
    Run (Join-Path $backend 'dist\arc-backend\arc-backend.exe') @('--selftest', '--selftest-out=build\selftest.json')
    Get-Content build\selftest.json -Encoding UTF8 | Select-Object -First 3
} finally { Pop-Location }

# ---------------------------------------------------------------- app
Push-Location $app
try {
    Step 'npm ci'
    Run npm.cmd @('ci', '--no-audit', '--no-fund')
    if (-not $SkipTests) {
        Step 'typecheck + vitest'
        Run npm.cmd @('run', 'typecheck')
        Run npm.cmd @('test')
    }
    Step 'Building renderer and main process'
    Run npm.cmd @('run', 'build:renderer')
    Run npm.cmd @('run', 'build:electron')
    Step 'electron-builder (NSIS)'
    $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
    Run npx.cmd @('electron-builder', '--win', '--x64', '--publish', 'never')
    $setup = Get-ChildItem release\ARC-Setup-*.exe | Select-Object -First 1
    if (-not $setup) { throw 'Installer not produced' }
    Write-Host ("Installer: {0} ({1:N1} MB)" -f $setup.FullName, ($setup.Length / 1MB)) -ForegroundColor Green
} finally { Pop-Location }
