<#
.SYNOPSIS
    Installs, updates or removes the ITAM inventory agent.

.DESCRIPTION
    - copies ITAM-Agent.ps1 to "%ProgramFiles%\ITAM Agent";
    - writes agent.config.json (server address + enrollment key) when they are given as parameters or the package
      contains agent.config.json (downloaded from ITAM: Agents → Installation → Download package);
    - registers the scheduled task "ITAM Agent" (SYSTEM; at startup, at user logon and every hour);
    - runs the first inventory immediately, so the computer appears in ITAM within a minute.
    Safe to run repeatedly (GPO computer startup script): an installed agent of the same version is left as is.

.EXAMPLE
    install.cmd                                         # settings from agent.config.json in the package or from GPO
    install.cmd -ServerUrl http://itam:8080 -EnrollmentKey ABC123
    install.cmd -Uninstall
#>
[CmdletBinding()]
param(
    [string]$ServerUrl,
    [string]$EnrollmentKey,
    [int]$IntervalHours,
    [switch]$IgnoreCertificateErrors,
    [switch]$Uninstall,
    [switch]$Force,
    [switch]$NoRun
)

$ErrorActionPreference = 'Stop'
$TaskName = 'ITAM Agent'
$InstallDir = Join-Path $env:ProgramFiles 'ITAM Agent'
$DataDir = Join-Path $env:ProgramData 'ITAM Agent'
$UninstallKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\ITAMAgent'
$Source = $PSScriptRoot

function Say([string]$m) { Write-Host $m; try { if (Test-Path $DataDir) { Add-Content (Join-Path $DataDir 'install.log') ("{0} {1}" -f (Get-Date -Format 's'), $m) -Encoding UTF8 } } catch { } }

function Restrict-Acl([string]$Path) {
    # SYSTEM and Administrators only: the config holds the enrollment key, the data folder holds the device token.
    & icacls.exe $Path /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T /Q | Out-Null
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error 'Запустите установку от имени администратора.'
    exit 5
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
    if (Test-Path $DataDir) { Remove-Item $DataDir -Recurse -Force }
    if (Test-Path $UninstallKey) { Remove-Item $UninstallKey -Recurse -Force }
    Write-Host 'Агент ITAM удалён. Запись компьютера в ITAM сохраняется; её можно удалить в разделе «Агенты».'
    exit 0
}

$newVersion = ([regex]::Match((Get-Content (Join-Path $Source 'ITAM-Agent.ps1') -Raw), "\`$AgentVersion = '([^']+)'")).Groups[1].Value
$installedVersion = $null
if (Test-Path (Join-Path $InstallDir 'ITAM-Agent.ps1')) {
    $installedVersion = ([regex]::Match((Get-Content (Join-Path $InstallDir 'ITAM-Agent.ps1') -Raw), "\`$AgentVersion = '([^']+)'")).Groups[1].Value
}
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$hasNewConfig = $ServerUrl -or $EnrollmentKey -or $IntervalHours -or (Test-Path (Join-Path $Source 'agent.config.json'))
if ($task -and $installedVersion -eq $newVersion -and -not $Force -and -not $hasNewConfig) {
    Write-Host "Агент ITAM $installedVersion уже установлен."
    exit 0
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
Restrict-Acl $DataDir
Say "Installing ITAM agent $newVersion (was: $installedVersion)"
Copy-Item (Join-Path $Source 'ITAM-Agent.ps1') $InstallDir -Force
Copy-Item (Join-Path $Source 'Install-ITAMAgent.ps1') $InstallDir -Force
foreach ($f in 'uninstall.cmd') { if (Test-Path (Join-Path $Source $f)) { Copy-Item (Join-Path $Source $f) $InstallDir -Force } }

# Configuration: parameters > agent.config.json from the package > existing config > GPO (read by the agent itself).
$configFile = Join-Path $InstallDir 'agent.config.json'
$config = [ordered]@{}
if (Test-Path $configFile) { (Get-Content $configFile -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $config[$_.Name] = $_.Value } }
$packageConfig = Join-Path $Source 'agent.config.json'
if ((Test-Path $packageConfig) -and ((Resolve-Path $packageConfig).Path -ne (Resolve-Path $configFile -ErrorAction SilentlyContinue).Path)) {
    (Get-Content $packageConfig -Raw -Encoding UTF8 | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $config[$_.Name] = $_.Value }
}
if ($ServerUrl) { $config['serverUrl'] = $ServerUrl.Trim().TrimEnd('/') }
if ($EnrollmentKey) { $config['enrollmentKey'] = $EnrollmentKey.Trim() }
if ($IntervalHours) { $config['intervalHours'] = $IntervalHours }
if ($IgnoreCertificateErrors) { $config['ignoreCertificateErrors'] = $true }
if ($config.Count -gt 0) {
    ($config | ConvertTo-Json) | Set-Content -Path $configFile -Encoding UTF8
    & icacls.exe $configFile /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' /Q | Out-Null
}
$gpo = Test-Path 'HKLM:\SOFTWARE\Policies\ITAM\Agent'
if (-not $config['serverUrl'] -and -not $gpo) {
    Write-Warning 'Адрес сервера не задан: укажите -ServerUrl и -EnrollmentKey, используйте пакет из ITAM с agent.config.json или настройте GPO.'
}

# Scheduled task: SYSTEM, at startup (+3 min), at any user logon (+1 min) and hourly; the agent itself decides when to send.
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $ps -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$InstallDir\ITAM-Agent.ps1`""
$startup = New-ScheduledTaskTrigger -AtStartup
$startup.Delay = 'PT3M'
$logon = New-ScheduledTaskTrigger -AtLogOn
$logon.Delay = 'PT1M'
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Description 'ITAM: инвентаризация компьютера (оборудование, ОС, ПО, пользователь)' `
    -Action $action -Trigger @($startup, $logon, $hourly) -Settings $settings -Principal $taskPrincipal -Force | Out-Null

# "Programs and Features" entry so the agent can be found and removed like any other program.
New-Item -Path $UninstallKey -Force | Out-Null
Set-ItemProperty $UninstallKey -Name DisplayName -Value 'ITAM Agent'
Set-ItemProperty $UninstallKey -Name DisplayVersion -Value $newVersion
Set-ItemProperty $UninstallKey -Name Publisher -Value 'ITAM'
Set-ItemProperty $UninstallKey -Name InstallLocation -Value $InstallDir
Set-ItemProperty $UninstallKey -Name UninstallString -Value "`"$ps`" -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\Install-ITAMAgent.ps1`" -Uninstall"
Set-ItemProperty $UninstallKey -Name NoModify -Value 1 -Type DWord
Set-ItemProperty $UninstallKey -Name NoRepair -Value 1 -Type DWord

Say "ITAM agent $newVersion installed"
if (-not $NoRun) {
    # First inventory right away (synchronously, so errors are visible to whoever runs the installer).
    & $ps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir 'ITAM-Agent.ps1') -Force
    if ($LASTEXITCODE -eq 0) { Write-Host 'Данные компьютера отправлены на сервер ITAM.' }
    else { Write-Warning "Первая отправка не удалась — подробности в $DataDir\agent.log. Агент повторит попытку по расписанию." }
}
exit 0
