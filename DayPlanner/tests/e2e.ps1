# Сквозная проверка DayPlanner на настоящей Windows: выезд панели у верхнего края,
# отсутствие выезда при перетаскивании (зажатая кнопка мыши) и запись отчёта в C:\worksheet.
#   pwsh tests\e2e.ps1 -Exe target\release\DayPlanner.exe
param([Parameter(Mandatory)][string]$Exe)
$ErrorActionPreference = 'Stop'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class W {
    public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindowW(string cls, string title);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[W]::SetProcessDPIAware() | Out-Null

# Задача, созданная вчера: при запуске программа обязана дописать отчёт за вчерашний день.
$data = Join-Path ([IO.Path]::GetTempPath()) "dayplanner-e2e-$PID"
New-Item -ItemType Directory -Force $data | Out-Null
$yesterday = (Get-Date).AddDays(-1)
$stamp = $yesterday.ToString('yyyy-MM-dd')
@"
{"tasks":[{"id":1,"title":"E2E task","due":"${stamp}T18:00:00","created":"${stamp}T09:00:00","done_at":"${stamp}T10:00:00"}],"next_id":1}
"@ | Set-Content -Encoding utf8 (Join-Path $data 'tasks.json')
$env:DAYPLANNER_DATA_DIR = $data
Remove-Item Env:DAYPLANNER_REPORT_DIR -ErrorAction SilentlyContinue   # настоящий путь C:\worksheet
$report = "C:\worksheet\Отчет_$stamp.txt"
Remove-Item $report -ErrorAction SilentlyContinue

$app = Start-Process $Exe -PassThru
try {
    $hwnd = [IntPtr]::Zero
    for ($i = 0; $i -lt 60 -and $hwnd -eq [IntPtr]::Zero; $i++) {
        Start-Sleep -Milliseconds 500
        if ($app.HasExited) { throw "DayPlanner exited with code $($app.ExitCode)" }
        $hwnd = [W]::FindWindowW($null, 'DayPlanner')
    }
    if ($hwnd -eq [IntPtr]::Zero) { throw 'Panel window not found' }
    Start-Sleep -Seconds 2

    $mid = [int]([W]::GetSystemMetrics(0) / 2)
    function Rect { $r = New-Object W+RECT; [W]::GetWindowRect($hwnd, [ref]$r) | Out-Null; $r }
    function Assert-Hidden($why) {
        $r = Rect
        if ($r.B -gt 0) { throw "Panel must be hidden ($why), but rect is top=$($r.T) bottom=$($r.B)" }
        "OK hidden: $why (top=$($r.T))"
    }
    function Assert-Open($why) {
        $r = Rect
        if ($r.T -ne 0) { throw "Panel must be open ($why), but rect is top=$($r.T) bottom=$($r.B)" }
        "OK open: $why (height=$($r.B))"
    }
    function Move($x, $y, $ms = 1500) { [W]::SetCursorPos($x, $y) | Out-Null; Start-Sleep -Milliseconds $ms }

    Move 300 500
    Assert-Hidden 'cursor away from the top edge'

    Move $mid 0 60
    Move 300 500 800
    Assert-Hidden 'edge touched for a moment only'

    Move $mid 0
    Assert-Open 'cursor rests on the top edge'
    $r = Rect
    Move $mid ([int]($r.B / 2))
    Assert-Open 'cursor is over the panel'
    Move 5 ($r.B + 200)
    Assert-Hidden 'cursor left the panel'

    # Перетаскивание: кнопка зажата — панель не выезжает ни во время, ни сразу после.
    Move 300 500 300
    [W]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)   # LEFTDOWN
    try {
        Move $mid 200 200
        Move $mid 0
        Assert-Hidden 'dragging with the left button held down'
    } finally {
        [W]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)   # LEFTUP
    }
    Start-Sleep -Milliseconds 1500
    Assert-Hidden 'button released at the edge after a drag'
    Move 300 500 500
    Move $mid 0
    Assert-Open 'edge works again after the drag is over'
    Move 5 900
    Assert-Hidden 'closed again'

    if (-not (Test-Path $report)) { throw "Report not created: $report" }
    $text = Get-Content $report -Raw -Encoding utf8
    if ($text -notmatch 'E2E task') { throw "Report has no task:`n$text" }
    "OK report: $report"
    $text
}
finally {
    if (-not $app.HasExited) { $app.Kill() }
    Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $report -ErrorAction SilentlyContinue
}
