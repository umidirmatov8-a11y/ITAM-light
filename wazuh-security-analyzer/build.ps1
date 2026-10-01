<#
.SYNOPSIS
  Builds WazuhSecurityAnalyzer.exe with PyInstaller (no Python needed on target machines).

.EXAMPLE
  .\build.ps1                 # single-file dist\WazuhSecurityAnalyzer.exe
  .\build.ps1 -OneDir         # portable folder dist\WazuhSecurityAnalyzer\
  .\build.ps1 -SkipTests      # skip the test suite
  .\build.ps1 -Console        # console build (shows output of --analyze / --self-test)
#>
param(
    [switch]$OneDir,
    [switch]$SkipTests,
    [switch]$Console,
    [string]$Python = "py"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Creating build virtual environment (.venv-build)"
if (-not (Test-Path ".venv-build")) {
    & $Python -3.12 -m venv .venv-build 2>$null
    if ($LASTEXITCODE -ne 0) { & $Python -m venv .venv-build }
}
$py = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"

Step "Installing dependencies"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Step "Generating demo dataset"
& $py scripts\generate_demo_data.py
if ($LASTEXITCODE -ne 0) { throw "demo data generation failed" }

if (-not $SkipTests) {
    Step "Running tests (excluding slow performance tests)"
    $env:QT_QPA_PLATFORM = "offscreen"
    & $py -m pytest -q -m "not slow"
    if ($LASTEXITCODE -ne 0) { throw "tests failed - build aborted" }
    Remove-Item Env:QT_QPA_PLATFORM
}

Step "Building with PyInstaller"
$env:WSA_ONEFILE = if ($OneDir) { "0" } else { "1" }
$env:WSA_CONSOLE = if ($Console) { "1" } else { "0" }
& $py -m PyInstaller --noconfirm --clean WazuhSecurityAnalyzer.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = if ($OneDir) { "dist\WazuhSecurityAnalyzer\WazuhSecurityAnalyzer.exe" } else { "dist\WazuhSecurityAnalyzer.exe" }

Step "Self-test of the packaged executable"
$env:WSA_HOME = Join-Path $env:TEMP "wsa_selftest"
$proc = Start-Process -FilePath $exe -ArgumentList "--self-test" -Wait -PassThru -NoNewWindow
Get-Content (Join-Path $env:WSA_HOME "logs\self_test.log") -ErrorAction SilentlyContinue
Remove-Item Env:WSA_HOME
if ($proc.ExitCode -ne 0) { throw "Self-test of the executable failed (exit code $($proc.ExitCode))" }

$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Step "Done: $exe ($size MB)"
Write-Host "Run it with a double-click or: $exe" -ForegroundColor Green
