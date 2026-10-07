<#
.SYNOPSIS
  Builds dist\AgentLoop.exe (single file, Python not needed on target machines)
  and, if Inno Setup is installed, the installer installer\Output\AgentLoop-Setup.exe.

.EXAMPLE
  .\build.ps1               # exe + installer
  .\build.ps1 -SkipTests
  .\build.ps1 -NoInstaller
#>
param(
    [switch]$SkipTests,
    [switch]$NoInstaller,
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

if (-not $SkipTests) {
    Step "Running tests"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
}

Step "Building AgentLoop.exe (PyInstaller)"
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name AgentLoop main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Get-Item dist\AgentLoop.exe | Format-Table Name, Length

if (-not $NoInstaller) {
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        $default = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        if (Test-Path $default) { $iscc = Get-Item $default }
    }
    if ($iscc) {
        Step "Building installer (Inno Setup)"
        & $iscc.Source installer\AgentLoop.iss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
        Get-ChildItem installer\Output | Format-Table Name, Length
    } else {
        Write-Warning "Inno Setup 6 not found - skipping installer (https://jrsoftware.org/isinfo.php). dist\AgentLoop.exe works standalone."
    }
}
