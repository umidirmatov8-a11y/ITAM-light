# Резервное копирование ARA: дамп PostgreSQL + файловое хранилище.
# Использование: powershell -ExecutionPolicy Bypass -File scripts\backup.ps1 [-PgDump "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"]
param([string]$PgDump = "pg_dump")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
$cfg = @{ PGHOST = "localhost"; PGPORT = "5432"; PGDATABASE = "ara"; PGUSER = "ara"; ARA_DATA_DIR = "data" }
if (Test-Path $envFile) {
  Get-Content $envFile | Where-Object { $_ -match '^\s*([A-Z_]+)=(.*)$' } | ForEach-Object { $cfg[$Matches[1]] = $Matches[2].Trim() }
}
$dataDir = Join-Path $root $cfg.ARA_DATA_DIR
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$target = Join-Path $dataDir "backups\$stamp"
New-Item -ItemType Directory -Force -Path $target | Out-Null
if ($cfg.PGPASSWORD) { $env:PGPASSWORD = $cfg.PGPASSWORD }
& $PgDump --format=custom --no-owner "--host=$($cfg.PGHOST)" "--port=$($cfg.PGPORT)" "--username=$($cfg.PGUSER)" "--file=$target\ara-db.dump" $cfg.PGDATABASE
if ($LASTEXITCODE -ne 0) { throw "pg_dump завершился с ошибкой" }
foreach ($sub in "imports", "reports") {
  $src = Join-Path $dataDir $sub
  if (Test-Path $src) { Copy-Item -Recurse -Force $src (Join-Path $target $sub) }
}
Write-Host "Резервная копия создана: $target"
