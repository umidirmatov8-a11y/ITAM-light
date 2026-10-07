<#
.SYNOPSIS
  Builds AgentLoop for Windows:
    dist\AgentLoop.exe                      the app (Python not needed on target machines)
    runtime\, models\                       llama.cpp engine + GGUF weights from Hugging Face (downloaded once)
    installer\Output\AgentLoop-Setup.exe    installer with everything inside (+ AgentLoop-Setup-*.bin slices
                                            when the model is larger than ~2 GB; keep them next to the .exe)

.EXAMPLE
  .\build.ps1                                   # default model Qwen2.5-3B-Instruct Q4_K_M
  .\build.ps1 -ModelRepo Qwen/Qwen2.5-1.5B-Instruct-GGUF -ModelFile qwen2.5-1.5b-instruct-q4_k_m.gguf
  .\build.ps1 -SkipTests -NoInstaller
#>
param(
    [switch]$SkipTests,
    [switch]$NoInstaller,
    [string]$ModelRepo = "Qwen/Qwen2.5-3B-Instruct-GGUF",
    [string]$ModelFile = "qwen2.5-3b-instruct-q4_k_m.gguf",
    [string]$LlamaTag = "latest",
    [string]$Backend = $(if ($env:LLAMA_CPP_BACKEND) { $env:LLAMA_CPP_BACKEND } else { "vulkan" }),
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

Step "Downloading llama.cpp ($LlamaTag, $Backend) and $ModelRepo/$ModelFile"
& $py scripts\fetch_assets.py --llama-tag $LlamaTag --backend $Backend --model-repo $ModelRepo --model-file $ModelFile
if ($LASTEXITCODE -ne 0) { throw "asset download failed" }

Step "Building AgentLoop.exe (PyInstaller)"
& $py scripts\make_icon.py | Out-Null
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name AgentLoop `
    --icon resources\agentloop.ico --add-data "resources\agentloop.ico;resources" main.py
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
        if (Test-Path installer\Output) { Remove-Item installer\Output -Recurse -Force }
        & $iscc.Source installer\AgentLoop.iss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
        Get-ChildItem installer\Output | Format-Table Name, Length
    } else {
        Write-Warning "Inno Setup 6 not found - skipping installer (https://jrsoftware.org/isinfo.php)."
    }
}
