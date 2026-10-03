using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Diagnostics.Services;
using FirstAidAdmin.Diagnostics.Storage;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Performance;

/// <summary>Threshold logic, kept pure for unit testing.</summary>
public static class PerformanceAnalyzer
{
    public static DiagnosticStatus Cpu(double percent, DiagnosticsSettings s) => percent >= 95 ? DiagnosticStatus.Error : percent >= s.CpuWarningPercent ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
    public static DiagnosticStatus Ram(double percent, DiagnosticsSettings s) => percent >= s.RamCriticalPercent ? DiagnosticStatus.Error : percent >= s.RamWarningPercent ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
    public static DiagnosticStatus Uptime(TimeSpan uptime, DiagnosticsSettings s) => uptime.TotalDays >= s.UptimeWarningDays ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
    public static DiagnosticStatus Startup(int count) => count > 20 ? DiagnosticStatus.Warning : count > 12 ? DiagnosticStatus.Info : DiagnosticStatus.Ok;
    public static DiagnosticStatus Boot(double seconds) => seconds >= 180 ? DiagnosticStatus.Error : seconds >= 90 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;

    /// <summary>Extracts the boot duration (ms) from a Diagnostics-Performance event 100 message (en/ru).</summary>
    public static double? ParseBootMs(string message)
    {
        var m = Regex.Match(message, @"(\d[\d\s ]*)\s*(?:ms|мс)", RegexOptions.IgnoreCase);
        if (!m.Success) return null;
        var digits = new string(m.Groups[1].Value.Where(char.IsDigit).ToArray());
        return double.TryParse(digits, NumberStyles.Integer, CultureInfo.InvariantCulture, out var v) ? v : null;
    }
}

public sealed class PerformanceModule : DiagnosticModuleBase
{
    private readonly ISystemProbe _system;
    private readonly IPowerShellRunner _ps;
    private readonly IServiceProbe _services;
    private readonly IEventLogProbe _events;

    public PerformanceModule(ISystemProbe system, IPowerShellRunner ps, IServiceProbe services, IEventLogProbe events)
    {
        _system = system;
        _ps = ps;
        _services = services;
        _events = events;
    }

    public override string Id => ModuleIds.Performance;
    public override string Name => "Производительность";
    public override DiagnosticCategory Category => DiagnosticCategory.Performance;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var s = ctx.Settings.Diagnostics;
        var cpuTask = _system.GetCpuUsageAsync(TimeSpan.FromSeconds(1), ct);
        var procTask = _system.GetTopProcessesAsync(TimeSpan.FromSeconds(1), 5, ct);
        await Task.WhenAll(cpuTask, procTask).ConfigureAwait(false);

        var cpu = cpuTask.Result;
        var procs = procTask.Result;
        if (cpu is { } c)
        {
            var top = procs.OrderByDescending(p => p.CpuPercent).Take(3).Where(p => p.CpuPercent > 1).ToList();
            Check(root, C.PerfCpu, "CPU", PerformanceAnalyzer.Cpu(c, s),
                    $"Загрузка {c:F0}% ({Environment.ProcessorCount} логических процессоров){(top.Count > 0 ? "; лидеры: " + string.Join(", ", top.Select(p => $"{p.Name} {p.CpuPercent:F0}%")) : "")}")
                .WithEvidence("cpuPercent", c.ToString(CultureInfo.InvariantCulture));
        }
        else
        {
            Check(root, C.PerfCpu, "CPU", DiagnosticStatus.Info, "Загрузка CPU недоступна");
        }

        var mem = _system.GetMemory();
        var topMem = procs.OrderByDescending(p => p.WorkingSetBytes).Take(3).ToList();
        Check(root, C.PerfRam, "RAM", PerformanceAnalyzer.Ram(mem.UsedPercent, s),
                $"Занято {mem.UsedPercent:F0}%: свободно {Gb(mem.AvailableBytes)} из {Gb(mem.TotalBytes)}; больше всего: {string.Join(", ", topMem.Select(p => $"{p.Name} {Mb(p.WorkingSetBytes)}"))}")
            .WithEvidence("usedPercent", mem.UsedPercent.ToString(CultureInfo.InvariantCulture))
            .WithEvidence("totalGb", (mem.TotalBytes / 1024d / 1024 / 1024).ToString("F1", CultureInfo.InvariantCulture))
            .WithRecommendation(mem.UsedPercent >= s.RamWarningPercent ? "Закройте ресурсоёмкие программы; при постоянной нехватке — добавьте RAM." : "",
                mem.UsedPercent >= s.RamWarningPercent ? new[] { A.OpenTaskManager } : Array.Empty<string>());

        var up = _system.GetUptime();
        Check(root, C.PerfUptime, "Время работы (uptime)", PerformanceAnalyzer.Uptime(up, s), $"{(int)up.TotalDays} дн. {up.Hours} ч")
            .WithEvidence("days", ((int)up.TotalDays).ToString(CultureInfo.InvariantCulture))
            .WithRecommendation(up.TotalDays >= s.UptimeWarningDays ? "Перезагрузите компьютер в удобное время." : "");

        var procCheck = Check(root, C.PerfProcesses, "Ресурсоёмкие процессы", DiagnosticStatus.Info,
            $"Процессов проанализировано, лидеры по памяти: {string.Join(", ", topMem.Select(p => p.Name))}");
        foreach (var p in procs.OrderByDescending(p => p.CpuPercent).ThenByDescending(p => p.WorkingSetBytes).Take(10))
            procCheck.WithEvidence($"{p.Name} ({p.Pid})", $"CPU {p.CpuPercent:F1}%, RAM {Mb(p.WorkingSetBytes)}");

        var sys = _system.GetDrives().FirstOrDefault(d => d.IsSystem);
        if (sys is not null)
            Check(root, C.PerfDisk, $"Диск {sys.Name}", StorageModule.Evaluate(sys, s.DiskWarningPercent, s.DiskCriticalPercent),
                    $"Занято {sys.UsedPercent:F0}%, свободно {sys.FreeGb:F1} ГБ")
                .WithEvidence("usedPercent", sys.UsedPercent.ToString(CultureInfo.InvariantCulture));

        if (ctx.System.IsWindows)
        {
            var json = await _ps.RunJsonAsync("@(Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | Select Name,Command,Location) | ConvertTo-Json -Compress", TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
            if (json is { } j)
            {
                var items = j.ValueKind == JsonValueKind.Array ? j.EnumerateArray().ToList() : j.ValueKind == JsonValueKind.Object ? new List<JsonElement> { j } : new List<JsonElement>();
                var st = Check(root, C.PerfStartup, "Автозагрузка", PerformanceAnalyzer.Startup(items.Count), $"Программ в автозагрузке: {items.Count}");
                foreach (var i in items.Take(30))
                    st.WithEvidence(i.TryGetProperty("Name", out var n) ? n.ToString() : "?", i.TryGetProperty("Location", out var l) ? l.ToString() : "");
                if (items.Count > 12) st.WithRecommendation("Отключите лишние программы в автозагрузке (Диспетчер задач → Автозагрузка).", A.OpenStartupApps);
            }
        }

        var auto = ServiceAnalyzer.AutoNotRunning(_services.GetAll());
        Check(root, C.PerfServices, "Потенциально проблемные службы", auto.Count > 5 ? DiagnosticStatus.Warning : DiagnosticStatus.Info,
            auto.Count == 0 ? "Автоматические службы работают" : $"Автоматических служб не запущено: {auto.Count} ({string.Join(", ", auto.Take(5).Select(x => x.Name))})");

        if (ctx.System.IsAdmin)
        {
            var boot = await _events.QueryAsync("Microsoft-Windows-Diagnostics-Performance/Operational", TimeSpan.FromDays(30), 5, true, ct, new[] { 100 }).ConfigureAwait(false);
            var last = boot.Events.FirstOrDefault();
            var ms = last is null ? null : PerformanceAnalyzer.ParseBootMs(last.Message);
            if (ms is { } bootMs)
                Check(root, C.PerfBoot, "Время загрузки", PerformanceAnalyzer.Boot(bootMs / 1000), $"Последняя загрузка: {bootMs / 1000:F0} с ({last!.TimeCreated.ToLocalTime():dd.MM.yyyy HH:mm})")
                    .WithEvidence("bootSeconds", (bootMs / 1000).ToString("F0", CultureInfo.InvariantCulture));
            else
                Check(root, C.PerfBoot, "Время загрузки", DiagnosticStatus.Info, "Данные о загрузке недоступны");
        }
        else
        {
            Skipped(root, C.PerfBoot, "Время загрузки", "Журнал Diagnostics-Performance доступен администратору", true);
        }

        // Plain performance summary (no causality claims).
        var causes = root.Checks.Where(x => x.Status is DiagnosticStatus.Warning or DiagnosticStatus.Error && x.Id is C.PerfCpu or C.PerfRam or C.PerfDisk or C.PerfUptime or C.PerfStartup or C.PerfBoot).ToList();
        root.Summary = causes.Count == 0
            ? "Явных причин снижения производительности не обнаружено"
            : "Потенциальные причины: " + string.Join("; ", causes.Select(x => x.Name));
    }
}
