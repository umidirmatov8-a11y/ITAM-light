<#
.SYNOPSIS
  Собирает ARA-Setup.exe: интерфейс и сервер → пакет приложения (только рабочие зависимости) →
  Node.js, PostgreSQL, WinSW → Inno Setup.
.EXAMPLE
  .\build-installer.ps1 -Version 1.0.0
#>
param(
    [string]$Version = "1.0.0",
    [string]$NodeMajor = "22",
    [string]$PostgresZipUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip",
    [string]$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Resolve-Path "$PSScriptRoot\.."
$build = Join-Path $PSScriptRoot "build"
$redist = Join-Path $PSScriptRoot "redist"
$app = Join-Path $build "app"

Write-Host "== Сборка интерфейса и сервера" -ForegroundColor Cyan
Push-Location $root
npm ci --no-audit --no-fund; if ($LASTEXITCODE) { throw "npm ci failed" }
npm run build; if ($LASTEXITCODE) { throw "build failed" }
if (-not $SkipTests) { npm test; if ($LASTEXITCODE) { throw "tests failed" } }
Pop-Location

Write-Host "== Пакет приложения" -ForegroundColor Cyan
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force "$app\server", "$app\web", "$app\database", "$app\docs" | Out-Null
Copy-Item "$root\package.json", "$root\package-lock.json" $app
Copy-Item "$root\server\package.json" "$app\server\"
Copy-Item "$root\web\package.json" "$app\web\"
Copy-Item "$root\server\dist" "$app\server\dist" -Recurse
Copy-Item "$root\web\dist" "$app\web\dist" -Recurse
Copy-Item "$root\database\migrations" "$app\database\migrations" -Recurse
Copy-Item "$root\docs\import-templates" "$app\docs\import-templates" -Recurse
Push-Location $app
# Только рабочие зависимости сервера (без React/Vite/TypeScript — интерфейс уже собран в web\dist).
npm ci --omit=dev --workspace "@ara/server" --ignore-scripts --no-audit --no-fund; if ($LASTEXITCODE) { throw "npm ci (production) failed" }
Pop-Location
foreach ($f in "server\dist\main.js", "web\dist\index.html", "node_modules\express\package.json", "node_modules\dejavu-fonts-ttf\ttf\DejaVuSans.ttf") {
    if (-not (Test-Path (Join-Path $app $f))) { throw "В пакете приложения нет $f" }
}

New-Item -ItemType Directory -Force $redist | Out-Null

$nodeExe = Join-Path $redist "node\node.exe"
if (-not (Test-Path $nodeExe)) {
    Write-Host "== Загрузка Node.js $NodeMajor (LTS)" -ForegroundColor Cyan
    $rel = (Invoke-RestMethod "https://nodejs.org/dist/index.json") | Where-Object { $_.version -like "v$NodeMajor.*" -and $_.lts } | Select-Object -First 1
    if (-not $rel) { throw "Не найден релиз Node.js $NodeMajor" }
    $zip = Join-Path $redist "node.zip"
    Invoke-WebRequest "https://nodejs.org/dist/$($rel.version)/node-$($rel.version)-win-x64.zip" -OutFile $zip
    $tmp = Join-Path $redist "node-tmp"
    Expand-Archive $zip -DestinationPath $tmp -Force
    New-Item -ItemType Directory -Force (Split-Path $nodeExe) | Out-Null
    Copy-Item (Get-ChildItem $tmp -Recurse -Filter node.exe | Select-Object -First 1).FullName $nodeExe
    Remove-Item $zip, $tmp -Recurse -Force
    Write-Host "Node.js $($rel.version)"
}

$pg = Join-Path $redist "pgsql"
if (-not (Test-Path (Join-Path $pg "bin\pg_ctl.exe"))) {
    Write-Host "== Загрузка PostgreSQL" -ForegroundColor Cyan
    $zip = Join-Path $redist "pgsql.zip"
    Invoke-WebRequest $PostgresZipUrl -OutFile $zip
    Expand-Archive $zip -DestinationPath $redist -Force
    Remove-Item $zip
    foreach ($d in "pgAdmin 4", "doc", "include", "StackBuilder", "symbols") {
        $p = Join-Path $pg $d; if (Test-Path $p) { Remove-Item $p -Recurse -Force }
    }
}

$winsw = Join-Path $redist "ARA-Service.exe"
if (-not (Test-Path $winsw)) {
    Write-Host "== Загрузка WinSW" -ForegroundColor Cyan
    Invoke-WebRequest $WinSWUrl -OutFile $winsw
}

Write-Host "== Inno Setup" -ForegroundColor Cyan
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) не найден. Установите: choco install innosetup" }
& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "ARA.iss")
if ($LASTEXITCODE) { throw "ISCC failed" }
$out = Join-Path $PSScriptRoot "Output\ARA-Setup.exe"
(Get-FileHash $out -Algorithm SHA256).Hash.ToLower() + "  ARA-Setup.exe" | Set-Content "$out.sha256" -Encoding ascii
Get-Item $out | Format-Table Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
