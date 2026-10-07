<#
.SYNOPSIS
  Builds ITAM-Setup.exe: frontend → backend publish (self-contained win-x64) → PostgreSQL binaries → Inno Setup.
.EXAMPLE
  .\build-installer.ps1 -Version 1.0.0
  .\build-installer.ps1 -SkipPostgres          # installer without the bundled PostgreSQL option
#>
param(
    [string]$Version = "1.0.0",
    [string]$PostgresZipUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.4-1-windows-x64-binaries.zip",
    [switch]$SkipPostgres,
    [switch]$SkipFrontend
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
$publish = Join-Path $root "publish\server"

if (-not $SkipFrontend) {
    Write-Host "== Frontend build" -ForegroundColor Cyan
    Push-Location (Join-Path $root "Frontend")
    npm ci; if ($LASTEXITCODE) { throw "npm ci failed" }
    npm run build; if ($LASTEXITCODE) { throw "frontend build failed" }
    Pop-Location
}

Write-Host "== Backend publish" -ForegroundColor Cyan
if (Test-Path $publish) { Remove-Item $publish -Recurse -Force }
dotnet publish (Join-Path $root "Backend\ITAM.Api\ITAM.Api.csproj") -c Release -r win-x64 --self-contained true `
    -p:Version=$Version -p:PublishSingleFile=false -o $publish
if ($LASTEXITCODE) { throw "dotnet publish failed" }
if (-not (Test-Path (Join-Path $publish "wwwroot\index.html"))) { throw "wwwroot/index.html missing in publish output" }

if (-not $SkipPostgres) {
    $redist = Join-Path $PSScriptRoot "redist"
    $pg = Join-Path $redist "pgsql"
    if (-not (Test-Path (Join-Path $pg "bin\pg_ctl.exe"))) {
        Write-Host "== Downloading PostgreSQL binaries" -ForegroundColor Cyan
        New-Item -ItemType Directory -Force $redist | Out-Null
        $zip = Join-Path $redist "pgsql.zip"
        Invoke-WebRequest $PostgresZipUrl -OutFile $zip
        Expand-Archive $zip -DestinationPath $redist -Force
        Remove-Item $zip
        # Not needed on a server: admin GUI, docs, headers, debug symbols.
        foreach ($d in "pgAdmin 4", "doc", "include", "StackBuilder", "symbols") {
            $p = Join-Path $pg $d; if (Test-Path $p) { Remove-Item $p -Recurse -Force }
        }
    }
}

Write-Host "== Inno Setup" -ForegroundColor Cyan
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found. Install: choco install innosetup" }
& $iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "ITAM.iss")
if ($LASTEXITCODE) { throw "ISCC failed" }
Get-Item (Join-Path $PSScriptRoot "Output\ITAM-Setup.exe") | Format-Table Name, Length
