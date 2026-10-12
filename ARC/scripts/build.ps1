<#
  Full build of the Windows installer.
    1. backend: venv, dependencies, pyflakes, pytest, PyInstaller onedir, EXE self-test
    2. app:     npm ci, typecheck, vitest, Vite + tsc build, electron-builder (NSIS)
  Result:  app\release\ARC-Setup-<version>.exe and ARC-Setup-<version>.exe.sha256
  Usage:   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-SkipTests]

  Code signing (optional): set ARC_SIGN_PFX (path to a .pfx code-signing certificate) and
  ARC_SIGN_PASSWORD. Then arc-backend.exe is signed with signtool, and electron-builder signs
  ARC.exe, the uninstaller and the installer. ARC_SIGN_TIMESTAMP (RFC 3161 URL) adds a timestamp.
  Without a certificate the build is unsigned (Windows SmartScreen will warn).
#>
param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$app = Join-Path $root 'app'

function Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
$signing = [bool]$env:ARC_SIGN_PFX
if ($signing -and -not (Test-Path $env:ARC_SIGN_PFX)) { throw "ARC_SIGN_PFX not found: $env:ARC_SIGN_PFX" }

function Find-SignTool {
    $kits = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $tool = Get-ChildItem $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $tool) { throw 'signtool.exe not found (install the Windows 10/11 SDK)' }
    return $tool.FullName
}

function Sign-File($path) {
    $arguments = @('sign', '/f', $env:ARC_SIGN_PFX, '/p', $env:ARC_SIGN_PASSWORD, '/fd', 'SHA256', '/d', 'A.R.C.')
    if ($env:ARC_SIGN_TIMESTAMP) { $arguments += @('/tr', $env:ARC_SIGN_TIMESTAMP, '/td', 'SHA256') }
    & (Find-SignTool) @($arguments + @($path))
    # no Run(): its error message would print the certificate password
    if ($LASTEXITCODE -ne 0) { throw "signtool failed for $path (exit code $LASTEXITCODE)" }
}
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
    if ($signing) {
        Step 'Signing arc-backend.exe'
        Sign-File (Join-Path $backend 'dist\arc-backend\arc-backend.exe')
    }
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
    if ($signing) {
        $env:CSC_LINK = $env:ARC_SIGN_PFX
        $env:CSC_KEY_PASSWORD = $env:ARC_SIGN_PASSWORD
    } else {
        Remove-Item Env:CSC_LINK -ErrorAction SilentlyContinue
    }
    Get-ChildItem release -Filter 'ARC-Setup-*' -ErrorAction SilentlyContinue | Remove-Item -Force
    Run npx.cmd @('electron-builder', '--win', '--x64', '--publish', 'never')
    $setup = Get-ChildItem release\ARC-Setup-*.exe | Select-Object -First 1
    if (-not $setup) { throw 'Installer not produced' }
    $hash = (Get-FileHash $setup.FullName -Algorithm SHA256).Hash.ToLower()
    Set-Content -Path ($setup.FullName + '.sha256') -Value "$hash  $($setup.Name)" -Encoding ascii
    Write-Host ("Installer: {0} ({1:N1} MB)" -f $setup.FullName, ($setup.Length / 1MB)) -ForegroundColor Green
    Write-Host "SHA-256:   $hash"
    if ($signing) {
        foreach ($f in @($setup.FullName, 'release\win-unpacked\ARC.exe', 'release\win-unpacked\resources\backend\arc-backend.exe')) {
            $sig = Get-AuthenticodeSignature $f
            Write-Host ("Signature: {0} -> {1} ({2})" -f (Split-Path $f -Leaf), $sig.Status, $sig.SignerCertificate.Subject)
            if (-not $sig.SignerCertificate) { throw "Not signed: $f" }
        }
    } else {
        Write-Host 'Not signed: no ARC_SIGN_PFX certificate (see docs/SIGNING.md)' -ForegroundColor Yellow
    }
} finally { Pop-Location }
