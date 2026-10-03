using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Parsers;
using FirstAidAdmin.Diagnostics.WindowsUpdate;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.WindowsHealth;

public static class ImageHealth
{
    /// <summary>Maps Repair-WindowsImage ImageHealthState (language independent enum) to status.</summary>
    public static (DiagnosticStatus Status, string Text) Map(string? state) => state switch
    {
        "Healthy" or "0" => (DiagnosticStatus.Ok, "Хранилище компонентов исправно (Healthy)"),
        "Repairable" or "1" => (DiagnosticStatus.Error, "Хранилище компонентов повреждено, но может быть восстановлено (Repairable)"),
        "NonRepairable" or "2" => (DiagnosticStatus.Critical, "Хранилище компонентов повреждено и не может быть восстановлено (NonRepairable)"),
        _ => (DiagnosticStatus.Warning, $"Не удалось определить состояние образа ({state ?? "нет данных"})")
    };

    public static string? ReadState(JsonElement? json)
        => json is { } j && j.ValueKind == JsonValueKind.Object && j.TryGetProperty("state", out var s) ? s.ToString() : null;

    public const string CheckHealthScript = "@{state=[string](Repair-WindowsImage -Online -CheckHealth -ErrorAction Stop).ImageHealthState} | ConvertTo-Json -Compress";
    public const string ScanHealthScript = "@{state=[string](Repair-WindowsImage -Online -ScanHealth -ErrorAction Stop).ImageHealthState} | ConvertTo-Json -Compress";
}

/// <summary>Quick Windows health: DISM CheckHealth (admin), last SFC results in CBS.log, pending reboot, crashes.</summary>
public sealed class WindowsHealthModule : DiagnosticModuleBase
{
    private readonly IPowerShellRunner _ps;
    private readonly IFileSystemProbe _fs;
    private readonly IRegistryProbe _registry;
    private readonly IEventLogProbe _events;
    private readonly ISystemProbe _system;

    public WindowsHealthModule(IPowerShellRunner ps, IFileSystemProbe fs, IRegistryProbe registry, IEventLogProbe events, ISystemProbe system)
    {
        _ps = ps;
        _fs = fs;
        _registry = registry;
        _events = events;
        _system = system;
    }

    public override string Id => ModuleIds.WindowsHealth;
    public override string Name => "Здоровье Windows";
    public override DiagnosticCategory Category => DiagnosticCategory.WindowsHealth;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows)
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Доступно только в Windows";
            return;
        }

        // DISM CheckHealth (fast, read-only, requires admin)
        if (ctx.System.IsAdmin)
        {
            var json = await _ps.RunJsonAsync(ImageHealth.CheckHealthScript, TimeSpan.FromMinutes(5), ct).ConfigureAwait(false);
            var (st, text) = ImageHealth.Map(ImageHealth.ReadState(json));
            var c = Check(root, C.HealthDism, "DISM CheckHealth (хранилище компонентов)", st, text).WithEvidence("state", ImageHealth.ReadState(json));
            c.RequiresAdmin = true;
            if (st is DiagnosticStatus.Error or DiagnosticStatus.Critical)
                c.WithRecommendation("Выполните DISM /RestoreHealth, затем sfc /scannow.", A.DismRestoreHealth, A.SfcScanNow);
        }
        else
        {
            Skipped(root, C.HealthDism, "DISM CheckHealth", "Требуются права администратора — можно запустить с UAC", requiresAdmin: true)
                .WithRecommendation("Запустите проверку с повышением прав (только чтение).", A.DismCheckHealth);
        }

        // Last SFC results from CBS.log (readable without admin on many systems)
        var windir = _system.GetEnvironmentVariable("windir") ?? @"C:\Windows";
        var cbs = Path.Combine(windir, "Logs", "CBS", "CBS.log");
        var tail = _fs.ReadTail(cbs, 4 * 1024 * 1024);
        if (tail is null)
        {
            Check(root, C.HealthCbs, "Журнал CBS (результаты SFC)", DiagnosticStatus.Info, "CBS.log недоступен для чтения (нужны права администратора)")
                .WithRecommendation("Для проверки системных файлов запустите sfc /verifyonly (UAC).", A.SfcVerify);
        }
        else
        {
            var (violations, repaired, completed) = CbsLogParser.Analyze(tail);
            Check(root, C.HealthCbs, "Журнал CBS (результаты SFC)",
                    violations > 0 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                    !completed && violations == 0 ? "Недавних результатов SFC в CBS.log нет"
                    : violations > 0 ? $"В последних проверках SFC найдено нарушений: {violations} (исправлено: {repaired})" : "Последняя проверка SFC нарушений не выявила")
                .WithEvidence("violations", violations).WithEvidence("repaired", repaired)
                .WithRecommendation(violations > 0 ? "Выполните DISM /RestoreHealth и sfc /scannow." : "", violations > 0 ? new[] { A.DismRestoreHealth, A.SfcScanNow } : Array.Empty<string>());
        }

        var reasons = PendingReboot.Reasons(_registry);
        Check(root, C.HealthPendingReboot, "Ожидание перезагрузки", reasons.Count > 0 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
            reasons.Count > 0 ? $"Требуется перезагрузка: {string.Join(", ", reasons)}" : "Перезагрузка не требуется");

        // Unexpected shutdowns / BSOD (7 days)
        var ev = await _events.QueryAsync("System", TimeSpan.FromDays(7), 200, true, ct, new[] { 41, 1001, 6008 }).ConfigureAwait(false);
        if (ev.Available && !ev.AccessDenied)
        {
            var crashes = ev.Events.Where(e => (e.EventId == 41 && e.Provider.Contains("Kernel-Power", StringComparison.OrdinalIgnoreCase))
                                               || (e.EventId == 1001 && (e.Provider.Contains("WER-SystemErrorReporting", StringComparison.OrdinalIgnoreCase) || e.Provider.Contains("BugCheck", StringComparison.OrdinalIgnoreCase)))
                                               || (e.EventId == 6008 && e.Provider.Equals("EventLog", StringComparison.OrdinalIgnoreCase))).ToList();
            var c = Check(root, C.HealthCrashes, "Сбои и неожиданные выключения (7 дней)",
                    crashes.Count == 0 ? DiagnosticStatus.Ok : crashes.Count >= 3 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                    crashes.Count == 0 ? "Неожиданных выключений и BSOD нет"
                                       : $"Событий: {crashes.Count} ({string.Join(", ", crashes.GroupBy(e => $"{e.Provider} {e.EventId}").Select(g => $"{g.Key} ×{g.Count()}"))}); последнее {crashes[0].TimeCreated.ToLocalTime():dd.MM.yyyy HH:mm}")
                .WithEvidence("count", crashes.Count);
            if (crashes.Count > 0) c.WithRecommendation("Проверьте питание, температуру и драйверы; изучите события в журнале.", A.OpenEventViewer);
        }
    }
}

/// <summary>sfc /verifyonly — long running (5–20 min), read-only, requires admin.</summary>
public sealed class SfcModule : DiagnosticModuleBase
{
    private readonly ICommandRunner _cmd;
    private readonly IFileSystemProbe _fs;
    private readonly ISystemProbe _system;

    public SfcModule(ICommandRunner cmd, IFileSystemProbe fs, ISystemProbe system)
    {
        _cmd = cmd;
        _fs = fs;
        _system = system;
    }

    public override string Id => ModuleIds.Sfc;
    public override string Name => "Проверка системных файлов (SFC /verifyonly)";
    public override DiagnosticCategory Category => DiagnosticCategory.WindowsHealth;
    public override bool IsLongRunning => true;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows) { root.Status = DiagnosticStatus.Skipped; root.Summary = "Доступно только в Windows"; return; }
        if (!ctx.System.IsAdmin)
        {
            Skipped(root, C.HealthSfc, "SFC /verifyonly", "Требуются права администратора — запустите через «Проверить с UAC»", true)
                .WithRecommendation("Запустите проверку через UAC (только чтение).", A.SfcVerify);
            return;
        }
        var r = await _cmd.RunAsync("sfc", "/verifyonly", TimeSpan.FromMinutes(40), ct, OutputEncoding.Unicode).ConfigureAwait(false);
        var windir = _system.GetEnvironmentVariable("windir") ?? @"C:\Windows";
        var tail = _fs.ReadTail(Path.Combine(windir, "Logs", "CBS", "CBS.log"), 8 * 1024 * 1024) ?? "";
        var (violations, _, completed) = CbsLogParser.Analyze(tail);
        var status = r.TimedOut ? DiagnosticStatus.Warning : violations > 0 ? DiagnosticStatus.Error : r.ExitCode == 0 || completed ? DiagnosticStatus.Ok : DiagnosticStatus.Warning;
        var c = Check(root, C.HealthSfc, "SFC /verifyonly", status,
                r.TimedOut ? "Проверка не завершилась за отведённое время"
                : violations > 0 ? $"Обнаружены нарушения целостности системных файлов: {violations}"
                : status == DiagnosticStatus.Ok ? "Нарушений целостности не обнаружено" : $"SFC завершился с кодом {r.ExitCode}")
            .WithEvidence("violations", violations).WithEvidence("exitCode", r.ExitCode)
            .WithDetails(r.StdOut.Replace("\0", "").Trim());
        c.RequiresAdmin = true;
        if (violations > 0) c.WithRecommendation("Выполните DISM /RestoreHealth, затем sfc /scannow.", A.DismRestoreHealth, A.SfcScanNow);
    }
}

/// <summary>DISM ScanHealth — long running (several minutes), read-only, requires admin.</summary>
public sealed class DismScanModule : DiagnosticModuleBase
{
    private readonly IPowerShellRunner _ps;
    public DismScanModule(IPowerShellRunner ps) => _ps = ps;

    public override string Id => ModuleIds.DismScan;
    public override string Name => "DISM ScanHealth";
    public override DiagnosticCategory Category => DiagnosticCategory.WindowsHealth;
    public override bool IsLongRunning => true;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows) { root.Status = DiagnosticStatus.Skipped; root.Summary = "Доступно только в Windows"; return; }
        if (!ctx.System.IsAdmin)
        {
            Skipped(root, C.HealthDismScan, "DISM ScanHealth", "Требуются права администратора — запустите через UAC", true)
                .WithRecommendation("Запустите проверку через UAC (только чтение).", A.DismScanHealth);
            return;
        }
        var json = await _ps.RunJsonAsync(ImageHealth.ScanHealthScript, TimeSpan.FromMinutes(40), ct).ConfigureAwait(false);
        var state = ImageHealth.ReadState(json);
        var (st, text) = ImageHealth.Map(state);
        var c = Check(root, C.HealthDismScan, "DISM ScanHealth", st, text).WithEvidence("state", state);
        c.RequiresAdmin = true;
        if (st is DiagnosticStatus.Error or DiagnosticStatus.Critical) c.WithRecommendation("Выполните DISM /RestoreHealth.", A.DismRestoreHealth);
    }
}
