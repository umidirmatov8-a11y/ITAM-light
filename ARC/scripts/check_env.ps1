<#
  A.R.C. environment check. Read-only: installs nothing, downloads nothing.
  Usage:  powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1 [-Dev]
  -Dev  also checks the tools needed to build from source (Python 3.12+, Node.js 20+).
#>
param([switch]$Dev)
$ErrorActionPreference = 'Continue'
$fail = 0; $warn = 0

function Report($state, $name, $detail) {
    $color = @{ OK = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Gray' }[$state]
    Write-Host ("[{0,-4}] {1,-28} {2}" -f $state, $name, $detail) -ForegroundColor $color
    if ($state -eq 'FAIL') { $script:fail++ }
    if ($state -eq 'WARN') { $script:warn++ }
}

Write-Host "A.R.C. environment check" -ForegroundColor Cyan

# --- OS
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
    $build = [int]$os.BuildNumber
    if ($build -ge 10240 -and [Environment]::Is64BitOperatingSystem) { Report OK 'Windows' "$($os.Caption) build $build x64" }
    else { Report FAIL 'Windows' "Windows 10/11 x64 required (found $($os.Caption) build $build)" }
    $ramGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    if ($ramGb -ge 16) { Report OK 'RAM' "$ramGb GB" } else { Report WARN 'RAM' "$ramGb GB (16+ GB recommended for local LLM)" }
}

# --- disk
$drive = Get-PSDrive -Name ($env:SystemDrive.TrimEnd(':')) -ErrorAction SilentlyContinue
if ($drive) {
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    if ($freeGb -ge 15) { Report OK 'Free disk space' "$freeGb GB on $($env:SystemDrive)" }
    else { Report WARN 'Free disk space' "$freeGb GB (app ~0.5 GB; speech models 0.5-3 GB; LLM 4-5 GB)" }
}

# --- GPU
$gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
foreach ($g in $gpus) { Report INFO 'GPU' $g.Name }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) {
    $q = & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
    Report OK 'NVIDIA driver' ($q | Select-Object -First 1)
} else {
    Report WARN 'NVIDIA driver' 'nvidia-smi not found: GPU metrics unavailable, local AI/speech will run on CPU (slower)'
}

# --- Ollama (optional)
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) { Report OK 'Ollama CLI' $ollama.Source } else { Report WARN 'Ollama CLI' 'not installed (optional; system commands work without it)' }
try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
    $names = ($tags.models | ForEach-Object { $_.name }) -join ', '
    if (-not $names) { $names = 'no models pulled' }
    Report OK 'Ollama server' $names
} catch {
    Report WARN 'Ollama server' 'not reachable on 127.0.0.1:11434 (start Ollama if you want local AI)'
}

# --- microphone / camera
$mics = Get-PnpDevice -Class AudioEndpoint -Status OK -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'SWD\MMDEVAPI\{0.0.1.*' }  # capture endpoints
if ($mics) { Report OK 'Microphone' (($mics | Select-Object -ExpandProperty FriendlyName) -join '; ') }
else { Report WARN 'Microphone' 'no microphone found (voice control needs one; text commands still work)' }
$cams = Get-PnpDevice -Class Camera, Image -Status OK -ErrorAction SilentlyContinue
if ($cams) { Report OK 'Camera' (($cams | Select-Object -ExpandProperty FriendlyName) -join '; ') }
else { Report WARN 'Camera' 'no camera found (gestures need one; everything else works)' }
$micPolicy = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone' -Name Value -ErrorAction SilentlyContinue
if ($micPolicy -and $micPolicy.Value -eq 'Deny') { Report WARN 'Microphone privacy' 'Settings > Privacy > Microphone: access for desktop apps is OFF' }

# --- installed A.R.C.
$installed = Join-Path $env:LOCALAPPDATA 'Programs\ARC\ARC.exe'
if (Test-Path $installed) { Report OK 'A.R.C. installed' $installed } else { Report INFO 'A.R.C. installed' 'not found in the default per-user location' }
$data = Join-Path $env:LOCALAPPDATA 'ARC'
if (Test-Path $data) { Report INFO 'A.R.C. data' $data }

# --- developer tools
if ($Dev) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    $pyVer = $null
    if ($py) { $pyVer = & py -3.12 -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null }
    if (-not $pyVer) { $p = Get-Command python -ErrorAction SilentlyContinue; if ($p) { $pyVer = & python -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null } }
    if ($pyVer -and [version]$pyVer -ge [version]'3.12.0') { Report OK 'Python' $pyVer } else { Report FAIL 'Python' "3.12+ required for building (found: $pyVer)" }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        $nv = (& node --version).TrimStart('v')
        if ([version]$nv -ge [version]'20.0.0') { Report OK 'Node.js' $nv } else { Report FAIL 'Node.js' "20+ required (found $nv)" }
    } else { Report FAIL 'Node.js' 'not found (https://nodejs.org, LTS)' }
    if (Get-Command git -ErrorAction SilentlyContinue) { Report OK 'git' (& git --version) } else { Report WARN 'git' 'not found' }
}

Write-Host ""
Write-Host ("Result: {0} error(s), {1} warning(s)" -f $fail, $warn) -ForegroundColor ($(if ($fail) { 'Red' } elseif ($warn) { 'Yellow' } else { 'Green' }))
exit $(if ($fail) { 1 } else { 0 })
