using System.Globalization;
using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Storage;

public sealed class StorageModule : DiagnosticModuleBase
{
    public static readonly int[] DiskEventIds = { 7, 11, 51, 55, 98, 129, 153, 154, 157 };
    private static readonly string[] DiskProviders = { "disk", "ntfs", "stor", "volmgr", "iastor", "nvme", "volsnap" };

    private readonly ISystemProbe _system;
    private readonly IFileSystemProbe _fs;
    private readonly IPowerShellRunner _ps;
    private readonly IEventLogProbe _events;

    public StorageModule(ISystemProbe system, IFileSystemProbe fs, IPowerShellRunner ps, IEventLogProbe events)
    {
        _system = system;
        _fs = fs;
        _ps = ps;
        _events = events;
    }

    public override string Id => ModuleIds.Storage;
    public override string Name => "Диски";
    public override DiagnosticCategory Category => DiagnosticCategory.Storage;

    /// <summary>Disk analyzer: status by used percent and absolute free space.</summary>
    public static DiagnosticStatus Evaluate(DriveSnapshot d, int warnPercent, int critPercent)
    {
        var freeGb = d.FreeBytes / 1024d / 1024 / 1024;
        if (d.UsedPercent >= critPercent || (d.IsSystem && freeGb < 5)) return DiagnosticStatus.Error;
        if (d.UsedPercent >= warnPercent || (d.IsSystem && freeGb < 10)) return DiagnosticStatus.Warning;
        return DiagnosticStatus.Ok;
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var s = ctx.Settings.Diagnostics;
        var drives = _system.GetDrives();
        var sys = drives.FirstOrDefault(d => d.IsSystem);
        if (sys is not null)
        {
            var st = Evaluate(sys, s.DiskWarningPercent, s.DiskCriticalPercent);
            var c = Check(root, C.StorageSystem, $"Системный диск {sys.Name}", st,
                    $"Занято {sys.UsedPercent:F0}%, свободно {sys.FreeGb:F1} из {sys.TotalGb:F0} ГБ")
                .WithEvidence("drive", sys.Name)
                .WithEvidence("usedPercent", sys.UsedPercent.ToString(CultureInfo.InvariantCulture))
                .WithEvidence("freeGb", sys.FreeGb.ToString(CultureInfo.InvariantCulture))
                .WithEvidence("fileSystem", sys.Format);
            if (st != DiagnosticStatus.Ok) c.WithRecommendation("Освободите место: временные файлы, корзина, «Очистка диска».", A.ClearUserTemp, A.OpenDiskCleanup, A.OpenStorageSettings);
        }

        var others = drives.Where(d => !d.IsSystem).ToList();
        if (others.Count > 0)
        {
            var bad = others.Where(d => Evaluate(d, s.DiskWarningPercent, s.DiskCriticalPercent) != DiagnosticStatus.Ok).ToList();
            var c = Check(root, C.StorageDrives, "Другие диски", bad.Count == 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
                bad.Count == 0 ? $"Дисков: {others.Count}, места достаточно" : $"Заполнены: {string.Join(", ", bad.Select(d => $"{d.Name} {d.UsedPercent:F0}%"))}");
            foreach (var d in drives) c.WithEvidence(d.Name, $"{d.UsedPercent:F0}% used, {d.FreeGb:F1} GB free, {d.Format}, {d.DriveType}");
        }

        // Temp
        var temp = _system.GetEnvironmentVariable("TEMP") ?? Path.GetTempPath();
        var (bytes, files, truncated) = _fs.GetDirectorySize(temp, 50_000);
        var tempGb = bytes / 1024d / 1024 / 1024;
        Check(root, C.StorageTemp, "Временные файлы пользователя", tempGb >= 5 ? DiagnosticStatus.Warning : tempGb >= 1 ? DiagnosticStatus.Info : DiagnosticStatus.Ok,
                $"{temp}: {Gb(bytes)} в {files}{(truncated ? "+" : "")} файлах")
            .WithEvidence("sizeGb", tempGb.ToString("F2", CultureInfo.InvariantCulture))
            .WithRecommendation(tempGb >= 1 ? "Очистите временные файлы старше 7 дней." : "", tempGb >= 1 ? new[] { A.ClearUserTemp } : Array.Empty<string>());

        if (!ctx.System.IsWindows) return;

        // Physical disks
        var pd = await _ps.RunJsonAsync(
            "Get-PhysicalDisk -ErrorAction SilentlyContinue | Select FriendlyName,@{n='MediaType';e={[string]$_.MediaType}},@{n='HealthStatus';e={[string]$_.HealthStatus}},@{n='OperationalStatus';e={[string]($_.OperationalStatus -join ',')}},Size | ConvertTo-Json -Compress",
            TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
        if (pd is { } pj)
        {
            var disks = (pj.ValueKind == JsonValueKind.Array ? pj.EnumerateArray().ToList() : new List<JsonElement> { pj });
            var unhealthy = disks.Where(d => !string.Equals(Str(d, "HealthStatus"), "Healthy", StringComparison.OrdinalIgnoreCase)).ToList();
            var c = Check(root, C.StoragePhysical, "Состояние физических дисков",
                unhealthy.Count == 0 ? DiagnosticStatus.Ok : unhealthy.Any(d => Str(d, "HealthStatus") == "Unhealthy") ? DiagnosticStatus.Critical : DiagnosticStatus.Error,
                unhealthy.Count == 0 ? $"Все диски Healthy ({string.Join(", ", disks.Select(d => $"{Str(d, "FriendlyName")} {Str(d, "MediaType")}"))})"
                                     : $"Проблемные диски: {string.Join(", ", unhealthy.Select(d => $"{Str(d, "FriendlyName")}: {Str(d, "HealthStatus")}/{Str(d, "OperationalStatus")}"))}");
            foreach (var d in disks) c.WithEvidence(Str(d, "FriendlyName"), $"{Str(d, "MediaType")}; {Str(d, "HealthStatus")}; {Str(d, "OperationalStatus")}");
            if (unhealthy.Count > 0) c.WithRecommendation("Немедленно сделайте резервную копию данных и проверьте диск.", A.ChkdskScan);
        }

        // Performance (active time / queue / latency)
        var perf = await _ps.RunJsonAsync(
            "Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -ErrorAction SilentlyContinue | ? {$_.Name -eq '_Total'} | Select PercentIdleTime,CurrentDiskQueueLength,AvgDisksecPerTransfer | ConvertTo-Json -Compress",
            TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
        if (perf is { ValueKind: JsonValueKind.Object } p)
        {
            var idle = Num(p, "PercentIdleTime");
            var queue = Num(p, "CurrentDiskQueueLength");
            var latencyMs = Num(p, "AvgDisksecPerTransfer") * 1000;
            var active = Math.Clamp(100 - idle, 0, 100);
            var st = active >= 90 || queue >= 5 || latencyMs >= 50 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
            Check(root, C.StoragePerformance, "Нагрузка на диск", st,
                    $"Активность {active:F0}%, очередь {queue:F0}{(latencyMs > 0 ? $", задержка {latencyMs:F0} мс" : "")}")
                .WithEvidence("activePercent", active.ToString(CultureInfo.InvariantCulture))
                .WithEvidence("queue", queue.ToString(CultureInfo.InvariantCulture))
                .WithEvidence("latencyMs", latencyMs.ToString(CultureInfo.InvariantCulture));
        }

        // Disk errors in the System log
        var ev = await _events.QueryAsync("System", TimeSpan.FromDays(7), 300, true, ct, DiskEventIds).ConfigureAwait(false);
        if (ev.Available && !ev.AccessDenied)
        {
            var diskEvents = ev.Events.Where(e => e.Level is >= 1 and <= 3 && DiskProviders.Any(pr => e.Provider.Contains(pr, StringComparison.OrdinalIgnoreCase))).ToList();
            var ntfsCorrupt = diskEvents.Any(e => e.Provider.Contains("ntfs", StringComparison.OrdinalIgnoreCase) && e.EventId is 55 or 98);
            var c = Check(root, C.StorageEvents, "Ошибки дисков в журнале (7 дней)",
                diskEvents.Count == 0 ? DiagnosticStatus.Ok : ntfsCorrupt || diskEvents.Count >= 10 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                diskEvents.Count == 0 ? "Ошибок дисковой подсистемы нет"
                                      : $"Событий: {diskEvents.Count} ({string.Join(", ", diskEvents.GroupBy(e => $"{e.Provider} {e.EventId}").Select(g => $"{g.Key} ×{g.Count()}"))})")
                .WithEvidence("count", diskEvents.Count);
            if (diskEvents.Count > 0) c.WithRecommendation("Выполните CHKDSK /scan и проверьте состояние диска.", A.ChkdskScan);
        }
    }

    private static string Str(JsonElement e, string n) => e.TryGetProperty(n, out var v) ? v.ToString() : "";
    private static double Num(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0;
}
