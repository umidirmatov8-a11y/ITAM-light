using System.Text.RegularExpressions;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.EventLog;

public sealed record EventGroup(string Log, string Provider, int EventId, int Count, int WorstLevel, DateTimeOffset First, DateTimeOffset Last, string LastMessage)
{
    public bool IsNoise => EventAnalyzer.IsNoise(Provider, EventId);
    public bool IsSerious => EventAnalyzer.IsSerious(Provider, EventId) || WorstLevel == 1;
}

/// <summary>Groups identical events instead of listing thousands of raw records.</summary>
public static class EventAnalyzer
{
    // Common harmless errors that would only distract the administrator.
    private static readonly (string Provider, int Id)[] Noise =
    {
        ("Microsoft-Windows-DistributedCOM", 10016), ("Microsoft-Windows-DistributedCOM", 10010),
        ("Microsoft-Windows-Security-SPP", 8198), ("Microsoft-Windows-Security-SPP", 16385),
        ("Microsoft-Windows-Perflib", 1008), ("Microsoft-Windows-Perflib", 1023),
        ("ESENT", 455), ("Microsoft-Windows-User Profiles Service", 1534), ("VSS", 8193),
    };

    private static readonly (string Provider, int Id)[] Serious =
    {
        ("Microsoft-Windows-Kernel-Power", 41), ("Microsoft-Windows-WER-SystemErrorReporting", 1001), ("BugCheck", 1001),
        ("EventLog", 6008), ("disk", 7), ("disk", 51), ("disk", 153), ("Ntfs", 55), ("Ntfs", 98),
        ("Microsoft-Windows-Ntfs", 55), ("Microsoft-Windows-Ntfs", 98), ("Microsoft-Windows-WHEA-Logger", 1), ("Microsoft-Windows-WHEA-Logger", 18),
        ("Microsoft-Windows-WHEA-Logger", 19), ("Microsoft-Windows-WHEA-Logger", 47), ("volmgr", 161), ("Service Control Manager", 7031), ("Service Control Manager", 7034),
    };

    public static bool IsNoise(string provider, int id) => Noise.Any(n => n.Id == id && provider.Equals(n.Provider, StringComparison.OrdinalIgnoreCase));
    public static bool IsSerious(string provider, int id) => Serious.Any(n => n.Id == id && provider.Equals(n.Provider, StringComparison.OrdinalIgnoreCase));

    public static List<EventGroup> Group(IEnumerable<EventRecordInfo> events)
        => events
            .GroupBy(e => (e.Log, e.Provider, e.EventId))
            .Select(g =>
            {
                var ordered = g.OrderByDescending(e => e.TimeCreated).ToList();
                return new EventGroup(g.Key.Log, g.Key.Provider, g.Key.EventId, ordered.Count,
                    ordered.Where(e => e.Level > 0).Select(e => e.Level).DefaultIfEmpty(2).Min(),
                    ordered[^1].TimeCreated, ordered[0].TimeCreated, Normalize(ordered[0].Message));
            })
            .OrderByDescending(g => g.IsSerious)
            .ThenBy(g => g.IsNoise)
            .ThenByDescending(g => g.Count)
            .ThenByDescending(g => g.Last)
            .ToList();

    public static string Normalize(string message)
    {
        var m = Regex.Replace(message, @"\s+", " ").Trim();
        return m.Length > 400 ? m[..400] + "…" : m;
    }

    public static string GroupId(EventGroup g)
        => $"events.group.{g.Log}.{g.Provider}.{g.EventId}".ToLowerInvariant()
            .Replace("microsoft-windows-", "").Replace(' ', '-').Replace('/', '-');
}

public sealed class EventLogModule : DiagnosticModuleBase
{
    private readonly IEventLogProbe _events;

    public EventLogModule(IEventLogProbe events) => _events = events;

    public override string Id => ModuleIds.EventLog;
    public override string Name => "Анализ системных событий";
    public override DiagnosticCategory Category => DiagnosticCategory.EventLog;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var hours = Math.Max(1, ctx.Settings.Diagnostics.EventLogHours);
        var window = TimeSpan.FromHours(hours);
        var max = ctx.Settings.Diagnostics.EventLogMaxEvents;
        await AnalyzeLog(root, C.EventsSystem, "Журнал System", "System", window, max, ct).ConfigureAwait(false);
        await AnalyzeLog(root, C.EventsApplication, "Журнал Application", "Application", window, max, ct).ConfigureAwait(false);
        await AnalyzeLog(root, C.EventsWindowsUpdate, "Журнал Windows Update", "Microsoft-Windows-WindowsUpdateClient/Operational", TimeSpan.FromDays(7), max, ct).ConfigureAwait(false);
        if (ctx.System.IsAdmin)
            await AnalyzeLog(root, C.EventsSecurity, "Журнал Security (аудит отказов)", "Security", window, max, ct, new[] { 4625, 4771, 4740, 1102 }).ConfigureAwait(false);
        else
            Skipped(root, C.EventsSecurity, "Журнал Security", "Доступен только с правами администратора", requiresAdmin: true);

        var total = root.Checks.Sum(c => c.Checks.Sum(g => int.TryParse(g.GetEvidence("count"), out var n) ? n : 0));
        root.Summary = total == 0 ? $"Ошибок за {hours} ч не найдено" : $"Ошибок за период: {total}, групп: {root.Checks.Sum(c => c.Checks.Count)}";
    }

    private async Task AnalyzeLog(DiagnosticResult root, string id, string name, string log, TimeSpan window, int max, CancellationToken ct, int[]? ids = null)
    {
        var q = await _events.QueryAsync(log, window, max, false, ct, ids).ConfigureAwait(false);
        if (q.AccessDenied) { Skipped(root, id, name, "Нет прав на чтение журнала", requiresAdmin: true); return; }
        if (!q.Available) { Skipped(root, id, name, q.Error ?? "Журнал недоступен"); return; }

        var groups = EventAnalyzer.Group(q.Events);
        var serious = groups.Where(g => g.IsSerious).ToList();
        var relevant = groups.Where(g => !g.IsNoise).ToList();
        var status = serious.Count > 0 ? DiagnosticStatus.Error : relevant.Sum(g => g.Count) >= 20 ? DiagnosticStatus.Warning : relevant.Count > 0 ? DiagnosticStatus.Info : DiagnosticStatus.Ok;
        var check = Check(root, id, name, status,
            groups.Count == 0 ? "Ошибок нет"
            : $"Событий: {q.Events.Count}, групп: {groups.Count}{(serious.Count > 0 ? $", серьёзных: {string.Join(", ", serious.Select(s => $"{s.Provider} {s.EventId}"))}" : "")}")
            .WithEvidence("events", q.Events.Count).WithEvidence("groups", groups.Count);
        if (serious.Count > 0) check.WithRecommendation("Изучите серьёзные события (сбои питания, ошибки дисков, падения служб).", A.OpenEventViewer);

        foreach (var g in groups.Take(15))
        {
            var gs = g.IsSerious ? DiagnosticStatus.Error : g.IsNoise ? DiagnosticStatus.Info : g.Count >= 10 ? DiagnosticStatus.Warning : DiagnosticStatus.Info;
            var child = DiagnosticResult.Create(EventAnalyzer.GroupId(g), $"{g.Provider} (ID {g.EventId})", DiagnosticCategory.EventLog, gs,
                    $"Количество: {g.Count}; последнее: {g.Last.ToLocalTime():dd.MM.yyyy HH:mm}")
                .WithEvidence("provider", g.Provider).WithEvidence("eventId", g.EventId).WithEvidence("count", g.Count)
                .WithEvidence("first", g.First.ToLocalTime().ToString("dd.MM.yyyy HH:mm")).WithEvidence("last", g.Last.ToLocalTime().ToString("dd.MM.yyyy HH:mm"))
                .WithEvidence("log", g.Log)
                .WithDetails(g.LastMessage);
            if (g.IsNoise) child.WithEvidence("note", "Типичное безвредное событие");
            check.Checks.Add(child);
        }
    }
}
