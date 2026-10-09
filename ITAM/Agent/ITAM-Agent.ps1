<#
.SYNOPSIS
    ITAM inventory agent for Windows: collects hardware, OS, network, logged-on user and installed software
    and sends it to the ITAM server.

.DESCRIPTION
    Runs as SYSTEM from the scheduled task "ITAM Agent" (created by Install-ITAMAgent.ps1): at startup, at user logon
    and every hour. A report is sent when the server-defined interval has passed, the logged-on user changed, or -Force.

    Configuration (first match wins):
      1. Group Policy:  HKLM\SOFTWARE\Policies\ITAM\Agent  (ServerUrl, EnrollmentKey, IntervalHours, IgnoreCertificateErrors)
      2. Local file:    %ProgramFiles%\ITAM Agent\agent.config.json  (written by the installer)
    State (device token): %ProgramData%\ITAM Agent\state.json — readable by SYSTEM and Administrators only.
    Log: %ProgramData%\ITAM Agent\agent.log

.PARAMETER Force
    Send a report now regardless of the interval.
.PARAMETER Output
    Only collect and write the report JSON to this file (nothing is sent). Useful for checking what is collected.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [string]$Output
)

$ErrorActionPreference = 'Stop'
# Windows PowerShell 5.1 adds an extended Count property to arrays, so ConvertTo-Json may write {"value":[...],"Count":n}.
Remove-TypeData -TypeName System.Array -ErrorAction SilentlyContinue
$AgentVersion = '1.0.0'
$InstallDir = Join-Path $env:ProgramFiles 'ITAM Agent'
$DataDir = Join-Path $env:ProgramData 'ITAM Agent'
$StateFile = Join-Path $DataDir 'state.json'
$LogFile = Join-Path $DataDir 'agent.log'

# ------------------------------------------------------------------ helpers

function Write-Log([string]$Message, [string]$Level = 'INFO') {
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Verbose $line
    if ($Output) { return }
    try {
        if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }
        if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 1MB) { Move-Item $LogFile "$LogFile.1" -Force }
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    } catch { }
}

function Get-Safe([scriptblock]$Block, $Default = $null) {
    try { $r = & $Block; if ($null -eq $r) { $Default } else { $r } } catch { Write-Log ("Collect: " + $_.Exception.Message) 'WARN'; $Default }
}

function Get-Cim([string]$Class, [string]$Namespace = 'root\cimv2', [string]$Filter) {
    $p = @{ ClassName = $Class; Namespace = $Namespace; ErrorAction = 'Stop' }
    if ($Filter) { $p.Filter = $Filter }
    @(Get-CimInstance @p)
}

function Text($v) {
    if ($null -eq $v) { return $null }
    $s = ([string]$v).Trim()
    if ($s.Length -eq 0) { return $null }
    $s
}

function Iso($dt) { if ($dt) { ([datetime]$dt).ToUniversalTime().ToString('o') } else { $null } }

# Windows PowerShell 5.1: an array that passed through a function return is wrapped in a PSObject and ConvertTo-Json
# writes it as {"value":[...],"Count":n}. Copy the items into a plain object[] so it is serialized as a JSON array.
function ConvertTo-PlainArray($items) {
    $list = New-Object System.Collections.Generic.List[object]
    foreach ($i in @($items)) { if ($null -ne $i) { $list.Add($i) } }
    , $list.ToArray()
}

function Decode-WmiString($arr) {
    if (-not $arr) { return $null }
    Text ((@($arr) | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join '')
}

# ------------------------------------------------------------------ configuration

function Get-AgentConfig {
    $cfg = @{ ServerUrl = $null; EnrollmentKey = $null; IntervalHours = $null; IgnoreCertificateErrors = $false; Source = $null }
    $policy = 'HKLM:\SOFTWARE\Policies\ITAM\Agent'
    if (Test-Path $policy) {
        $p = Get-ItemProperty $policy
        if ($p.ServerUrl) { $cfg.ServerUrl = [string]$p.ServerUrl; $cfg.Source = 'GPO' }
        if ($p.EnrollmentKey) { $cfg.EnrollmentKey = [string]$p.EnrollmentKey }
        if ($p.IntervalHours) { $cfg.IntervalHours = [int]$p.IntervalHours }
        if ($p.IgnoreCertificateErrors) { $cfg.IgnoreCertificateErrors = [int]$p.IgnoreCertificateErrors -eq 1 }
    }
    $file = Join-Path $InstallDir 'agent.config.json'
    if (-not (Test-Path $file)) { $file = Join-Path $PSScriptRoot 'agent.config.json' }
    if (Test-Path $file) {
        $j = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $cfg.ServerUrl -and $j.serverUrl) { $cfg.ServerUrl = [string]$j.serverUrl; $cfg.Source = $file }
        if (-not $cfg.EnrollmentKey -and $j.enrollmentKey) { $cfg.EnrollmentKey = [string]$j.enrollmentKey }
        if (-not $cfg.IntervalHours -and $j.intervalHours) { $cfg.IntervalHours = [int]$j.intervalHours }
        if ($j.ignoreCertificateErrors) { $cfg.IgnoreCertificateErrors = [bool]$j.ignoreCertificateErrors }
    }
    if ($cfg.ServerUrl) { $cfg.ServerUrl = $cfg.ServerUrl.Trim().TrimEnd('/') }
    $cfg
}

function Get-State {
    if (Test-Path $StateFile) { try { return (Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { } }
    $null
}

function Save-State($state) {
    if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }
    ($state | ConvertTo-Json -Depth 3) | Set-Content -Path $StateFile -Encoding UTF8
    # Token file: SYSTEM and Administrators only.
    try { & icacls.exe $StateFile /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null } catch { Write-Log ('ACL: ' + $_.Exception.Message) 'WARN' }
}

# ------------------------------------------------------------------ inventory

function Get-FormFactor($cs, $enclosure, $manufacturer, $model) {
    $virtual = "$manufacturer $model" -match 'VMware|VirtualBox|Virtual Machine|QEMU|KVM|Xen|Hyper-V|Parallels'
    if ($virtual) { return 'Virtual' }
    $types = @()
    if ($enclosure) { $types = @($enclosure.ChassisTypes) }
    if ($types | Where-Object { $_ -in 8, 9, 10, 11, 12, 14, 18, 21, 31, 32 }) { return 'Laptop' }
    if ($types | Where-Object { $_ -eq 30 }) { return 'Tablet' }
    if ($types | Where-Object { $_ -eq 13 }) { return 'AllInOne' }
    if ($types | Where-Object { $_ -in 17, 23, 28 }) { return 'Server' }
    if ($cs -and $cs.PCSystemType -eq 2) { return 'Laptop' }
    if ($cs -and $cs.PCSystemType -in 4, 5, 7) { return 'Server' }
    'Desktop'
}

function Get-CurrentUser($cs) {
    $u = Text $cs.UserName
    if ($u) { return $u }
    # No console user (RDP / fast user switching): owner of explorer.exe.
    $owners = @(Get-Cim Win32_Process -Filter "Name='explorer.exe'" | ForEach-Object {
        $o = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
        if ($o -and $o.User) { if ($o.Domain) { "$($o.Domain)\$($o.User)" } else { $o.User } }
    } | Select-Object -Unique)
    if ($owners.Count -gt 0) { $owners[0] } else { $null }
}

function Get-InstalledSoftware {
    $paths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'Registry::HKEY_USERS\*\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $seen = @{}
    foreach ($p in $paths) {
        foreach ($k in @(Get-ItemProperty -Path $p -ErrorAction SilentlyContinue)) {
            $name = Text $k.DisplayName
            if (-not $name) { continue }
            if ($k.SystemComponent -eq 1 -or $k.ParentKeyName -or $k.ReleaseType -in 'Update', 'Hotfix', 'Security Update') { continue }
            if ($name -match '^(Security Update|Update for|Hotfix for)\b') { continue }
            $version = Text $k.DisplayVersion
            $key = "$name|$version"
            if ($seen.ContainsKey($key)) { continue }
            $seen[$key] = $true
            [pscustomobject]@{ name = $name; version = $version; publisher = (Text $k.Publisher); installDate = (Text $k.InstallDate) }
        }
    }
}

function Get-Inventory {
    $cs = Get-Safe { (Get-Cim Win32_ComputerSystem)[0] }
    $bios = Get-Safe { (Get-Cim Win32_BIOS)[0] }
    $product = Get-Safe { (Get-Cim Win32_ComputerSystemProduct)[0] }
    $enclosure = Get-Safe { (Get-Cim Win32_SystemEnclosure)[0] }
    $os = Get-Safe { (Get-Cim Win32_OperatingSystem)[0] }
    $cpus = Get-Safe { Get-Cim Win32_Processor } @()
    $nt = Get-Safe { Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' }

    $manufacturer = Text $cs.Manufacturer
    $model = Text $cs.Model
    if ($manufacturer -match '^LENOVO$' -and $product -and (Text $product.Version)) { $model = Text $product.Version } # "ThinkPad T14 Gen 3" instead of "21AH00..."

    $ramMb = Get-Safe { [int](((Get-Cim Win32_PhysicalMemory) | Measure-Object Capacity -Sum).Sum / 1MB) }
    if (-not $ramMb -and $cs) { $ramMb = [int]($cs.TotalPhysicalMemory / 1MB) }

    $disks = Get-Safe {
        @(Get-CimInstance -Namespace 'root\Microsoft\Windows\Storage' -ClassName MSFT_PhysicalDisk -ErrorAction Stop | ForEach-Object {
            $media = switch ($_.MediaType) { 3 { 'HDD' } 4 { 'SSD' } 5 { 'SCM' } default { $null } }
            if ($_.BusType -eq 17) { $media = 'NVMe SSD' }
            if ($_.BusType -in 7, 18) { return } # USB, SD: removable media are not part of the computer
            [pscustomobject]@{ model = (Text $_.FriendlyName); serialNumber = (Text $_.SerialNumber); sizeGb = [math]::Round($_.Size / 1e9); mediaType = $media }
        })
    } @()
    if ($disks.Count -eq 0) {
        $disks = Get-Safe { @(Get-Cim Win32_DiskDrive | Where-Object { $_.MediaType -notmatch 'Removable' -and $_.InterfaceType -ne 'USB' } | ForEach-Object {
            [pscustomobject]@{ model = (Text $_.Model); serialNumber = (Text $_.SerialNumber); sizeGb = [math]::Round($_.Size / 1e9); mediaType = $null } }) } @()
    }
    $volumes = Get-Safe { @(Get-Cim Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        [pscustomobject]@{ drive = $_.DeviceID; sizeGb = [math]::Round($_.Size / 1GB, 1); freeGb = [math]::Round($_.FreeSpace / 1GB, 1); fileSystem = $_.FileSystem } }) } @()
    $network = Get-Safe { @(Get-Cim Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' | Where-Object { $_.MACAddress } | ForEach-Object {
        [pscustomobject]@{ name = (Text $_.Description); macAddress = $_.MACAddress; ip = @($_.IPAddress | Where-Object { $_ }); gateway = @($_.DefaultIPGateway | Where-Object { $_ }); dhcp = [bool]$_.DHCPEnabled } }) } @()
    $monitors = Get-Safe { @(Get-CimInstance -Namespace 'root\wmi' -ClassName WmiMonitorID -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{ manufacturer = (Decode-WmiString $_.ManufacturerName); model = (Decode-WmiString $_.UserFriendlyName); serialNumber = (Decode-WmiString $_.SerialNumberID) } }) } @()
    $gpus = Get-Safe { @(Get-Cim Win32_VideoController | ForEach-Object { Text $_.Name } | Where-Object { $_ -and $_ -notmatch 'Basic Display|Remote Display|Mirror' } | Select-Object -Unique) } @()
    $printers = Get-Safe { @(Get-Cim Win32_Printer | Where-Object { $_.Name -notmatch 'PDF|XPS|OneNote|Fax' } | ForEach-Object { Text $_.Name }) } @()
    $antivirus = Get-Safe { (@(Get-CimInstance -Namespace 'root\SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop | ForEach-Object { $_.displayName } | Select-Object -Unique) -join ', ') }
    $software = Get-Safe { @(Get-InstalledSoftware) } @()

    $osVersion = $null; $osBuild = $null
    if ($nt) {
        $osVersion = Text $nt.DisplayVersion
        if (-not $osVersion) { $osVersion = Text $nt.ReleaseId }
        if ($nt.CurrentBuild) { $osBuild = "$($nt.CurrentBuild)$(if ($nt.UBR) { '.' + $nt.UBR })" }
    }
    if (-not $osVersion -and $os) { $osVersion = Text $os.Version }
    if (-not $osBuild -and $os) { $osBuild = Text $os.BuildNumber }

    $hostname = $env:COMPUTERNAME
    if ($cs -and $cs.Name) { $hostname = $cs.Name }

    [ordered]@{
        agentVersion   = $AgentVersion
        hostname       = $hostname
        domain         = $(if ($cs -and $cs.PartOfDomain) { Text $cs.Domain } else { $null })
        manufacturer   = $manufacturer
        model          = $model
        serialNumber   = $(if ($bios) { Text $bios.SerialNumber })
        hardwareUuid   = $(if ($product) { Text $product.UUID })
        formFactor     = (Get-FormFactor $cs $enclosure $manufacturer $model)
        osName         = $(if ($os) { Text $os.Caption })
        osVersion      = $osVersion
        osBuild        = $osBuild
        osArchitecture = $(if ($os) { Text $os.OSArchitecture })
        osInstallDate  = $(if ($os) { Iso $os.InstallDate })
        lastBootAt     = $(if ($os) { Iso $os.LastBootUpTime })
        cpu            = $(if ($cpus.Count -gt 0) { (Text $cpus[0].Name) -replace '\s+', ' ' })
        cpuCores       = $(if ($cpus.Count -gt 0) { [int](($cpus | Measure-Object NumberOfCores -Sum).Sum) })
        ramMb          = $ramMb
        biosVersion    = $(if ($bios) { Text $bios.SMBIOSBIOSVersion })
        currentUser    = (Get-Safe { Get-CurrentUser $cs })
        antivirus      = (Text $antivirus)
        disks          = [object[]](ConvertTo-PlainArray $disks)
        volumes        = [object[]](ConvertTo-PlainArray $volumes)
        network        = [object[]](ConvertTo-PlainArray $network)
        monitors       = [object[]](ConvertTo-PlainArray $monitors)
        gpus           = [object[]](ConvertTo-PlainArray $gpus)
        printers       = [object[]](ConvertTo-PlainArray $printers)
        software       = [object[]](ConvertTo-PlainArray $software)
    }
}

# ------------------------------------------------------------------ transport

function Invoke-Api([hashtable]$Config, [string]$Path, $Body, [string]$Token) {
    $json = $Body | ConvertTo-Json -Depth 6 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $headers = @{ 'User-Agent' = "ITAM-Agent/$AgentVersion" }
    if ($Token) { $headers['X-ITAM-Agent-Token'] = $Token }
    Invoke-RestMethod -Uri ($Config.ServerUrl + $Path) -Method Post -Body $bytes -ContentType 'application/json; charset=utf-8' `
        -Headers $headers -UseBasicParsing -TimeoutSec 120
}

function Get-HttpStatus($err) {
    try { [int]$err.Exception.Response.StatusCode } catch { 0 }
}

function Register-Agent([hashtable]$Config) {
    if (-not $Config.EnrollmentKey) { throw 'Не задан ключ регистрации (EnrollmentKey) — настройте GPO или переустановите агент с ключом.' }
    $machineId = Get-Safe { (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid }
    if (-not $machineId) { $machineId = Get-Safe { (Get-Cim Win32_ComputerSystemProduct)[0].UUID } }
    if (-not $machineId) { $machineId = 'host-' + $env:COMPUTERNAME.ToLowerInvariant() }
    $r = Invoke-Api $Config '/api/agent/register' @{ enrollmentKey = $Config.EnrollmentKey; machineId = $machineId; hostname = $env:COMPUTERNAME; agentVersion = $AgentVersion }
    Write-Log "Registered on $($Config.ServerUrl) as device $($r.deviceId)"
    $state = [pscustomobject]@{ deviceId = $r.deviceId; token = $r.token; server = $Config.ServerUrl; intervalHours = $r.intervalHours; lastSentAt = $null; lastUser = $null }
    Save-State $state
    $state
}

# ------------------------------------------------------------------ main

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch { }

try {
    if ($Output) {
        $inv = Get-Inventory
        ($inv | ConvertTo-Json -Depth 6) | Set-Content -Path $Output -Encoding UTF8
        Write-Host "Inventory written to $Output ($(@($inv.software).Count) programs)"
        exit 0
    }

    $config = Get-AgentConfig
    if (-not $config.ServerUrl) { throw 'Не задан адрес сервера ITAM (ServerUrl) — настройте GPO или переустановите агент.' }
    if ($config.IgnoreCertificateErrors) { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } }

    $state = Get-State
    if (-not $state -or -not $state.token -or $state.server -ne $config.ServerUrl) { $state = Register-Agent $config }

    $inv = Get-Inventory
    $interval = $config.IntervalHours
    if (-not $interval) { $interval = $state.intervalHours }
    if (-not $interval) { $interval = 4 }
    $due = $Force -or -not $state.lastSentAt -or ((Get-Date) - [datetime]$state.lastSentAt).TotalHours -ge ($interval - 0.1) -or $state.lastUser -ne $inv.currentUser
    if (-not $due) { Write-Log "Not due yet (interval $interval h)" 'DEBUG'; exit 0 }

    try {
        $r = Invoke-Api $config '/api/agent/inventory' $inv $state.token
    } catch {
        if ((Get-HttpStatus $_) -ne 401) { throw }
        Write-Log 'Token rejected by the server — registering again' 'WARN'
        $state = Register-Agent $config
        $r = Invoke-Api $config '/api/agent/inventory' $inv $state.token
    }
    $state.lastSentAt = (Get-Date).ToString('o')
    $state.lastUser = $inv.currentUser
    if ($r.intervalHours) { $state.intervalHours = $r.intervalHours }
    Save-State $state
    $asset = ''
    if ($r.assetNumber) { $asset = ", asset $($r.assetNumber)" }
    Write-Log ("Inventory sent: {0} programs, user {1}{2}" -f @($inv.software).Count, $inv.currentUser, $asset)
    exit 0
} catch {
    $detail = ''
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $detail = ' | ' + $_.ErrorDetails.Message }
    Write-Log ($_.Exception.Message + $detail) 'ERROR'
    Write-Error $_.Exception.Message
    exit 1
}
