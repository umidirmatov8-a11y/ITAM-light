using System.Globalization;
using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Parsers;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.WindowsUpdate;

public sealed record UpdateHistoryEntry(DateTimeOffset Date, string Title, int ResultCode, string HResult);
public sealed record UpdateHistory(IReadOnlyList<UpdateHistoryEntry> Entries, IReadOnlyList<(string Id, DateTimeOffset InstalledOn)> HotFixes, string? Error)
{
    public DateTimeOffset? LastSuccess
    {
        get
        {
            var fromHistory = Entries.Where(e => e.ResultCode is 2 or 3).Select(e => (DateTimeOffset?)e.Date).DefaultIfEmpty(null).Max();
            var fromHotfix = HotFixes.Select(h => (DateTimeOffset?)h.InstalledOn).DefaultIfEmpty(null).Max();
            return new[] { fromHistory, fromHotfix }.Where(d => d.HasValue).DefaultIfEmpty(null).Max();
        }
    }
}

public static class PendingReboot
{
    public static List<string> Reasons(IRegistryProbe reg)
    {
        var reasons = new List<string>();
        if (reg.KeyExists(RegistryHive.LocalMachine, @"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"))
            reasons.Add("Windows Update: RebootRequired");
        if (reg.KeyExists(RegistryHive.LocalMachine, @"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"))
            reasons.Add("CBS: RebootPending");
        if (reg.GetValue(RegistryHive.LocalMachine, @"SYSTEM\CurrentControlSet\Control\Session Manager", "PendingFileRenameOperations") is string[] { Length: > 0 })
            reasons.Add("PendingFileRenameOperations");
        return reasons;
    }
}

public sealed class WindowsUpdateModule : DiagnosticModuleBase
{
    public const string HistoryScript =
        "$err=$null;$items=@();try{$s=New-Object -ComObject Microsoft.Update.Session;$h=$s.CreateUpdateSearcher();$n=$h.GetTotalHistoryCount();" +
        "if($n -gt 0){$items=$h.QueryHistory(0,[Math]::Min(40,$n)) | ? {$_.Operation -eq 1} | Select @{n='Date';e={$_.Date.ToUniversalTime().ToString('o')}},Title,ResultCode,@{n='HResult';e={'0x{0:x8}' -f $_.HResult}}}}catch{$err=$_.Exception.Message};" +
        "$hf=Get-HotFix -ErrorAction SilentlyContinue | ? {$_.InstalledOn} | Sort InstalledOn -Desc | Select -First 5 @{n='Id';e={$_.HotFixID}},@{n='InstalledOn';e={$_.InstalledOn.ToString('o')}};" +
        "@{history=@($items);hotfix=@($hf);error=$err} | ConvertTo-Json -Depth 3 -Compress";

    private readonly IServiceProbe _services;
    private readonly IPowerShellRunner _ps;
    private readonly IEventLogProbe _events;
    private readonly IRegistryProbe _registry;
    private readonly Func<DateTimeOffset> _clock;

    public WindowsUpdateModule(IServiceProbe services, IPowerShellRunner ps, IEventLogProbe events, IRegistryProbe registry, Func<DateTimeOffset>? clock = null)
    {
        _services = services;
        _ps = ps;
        _events = events;
        _registry = registry;
        _clock = clock ?? (() => DateTimeOffset.Now);
    }

    public override string Id => ModuleIds.WindowsUpdate;
    public override string Name => "Windows Update";
    public override DiagnosticCategory Category => DiagnosticCategory.WindowsUpdate;

    public static UpdateHistory ParseHistory(JsonElement root)
    {
        static IEnumerable<JsonElement> Arr(JsonElement r, string n) => r.TryGetProperty(n, out var v) ? v.ValueKind == JsonValueKind.Array ? v.EnumerateArray() : v.ValueKind == JsonValueKind.Object ? new[] { v } : Array.Empty<JsonElement>() : Array.Empty<JsonElement>();
        static string S(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
        static DateTimeOffset D(string s) => DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var d) ? d : DateTimeOffset.MinValue;

        var entries = Arr(root, "history").Select(e => new UpdateHistoryEntry(D(S(e, "Date")), S(e, "Title"),
            e.TryGetProperty("ResultCode", out var rc) && rc.TryGetInt32(out var r) ? r : 0, S(e, "HResult"))).ToList();
        var hf = Arr(root, "hotfix").Select(h => (S(h, "Id"), D(S(h, "InstalledOn")))).Where(h => h.Item2 > DateTimeOffset.MinValue).ToList();
        var err = root.TryGetProperty("error", out var ev) && ev.ValueKind == JsonValueKind.String ? ev.GetString() : null;
        return new UpdateHistory(entries, hf, err);
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows && _services.Get("wuauserv").State == ServiceState.NotFound)
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Windows Update доступен только в Windows";
            return;
        }

        ServiceCheck(root, C.WuService, "Служба Windows Update (wuauserv)", "wuauserv");
        ServiceCheck(root, C.WuBits, "Служба BITS", "BITS");
        var related = new[] { "CryptSvc", "TrustedInstaller", "msiserver" }.Select(_services.Get).ToList();
        var disabled = related.Where(s => s.StartMode == ServiceStartMode.Disabled).ToList();
        var rel = Check(root, C.WuRelated, "Связанные службы (CryptSvc, TrustedInstaller, msiserver)",
            disabled.Count > 0 ? DiagnosticStatus.Error : DiagnosticStatus.Ok,
            disabled.Count > 0 ? $"Отключены: {string.Join(", ", disabled.Select(s => s.Name))}" : "Связанные службы не отключены");
        foreach (var s in related) rel.WithEvidence(s.Name, $"{s.State}; {s.StartMode}");
        if (disabled.Count > 0) rel.WithRecommendation("Верните тип запуска служб по умолчанию.", A.OpenServices);

        // History
        var json = await _ps.RunJsonAsync(HistoryScript, TimeSpan.FromSeconds(90), ct).ConfigureAwait(false);
        var now = _clock();
        if (json is { } j)
        {
            var h = ParseHistory(j);
            var last = h.LastSuccess;
            var days = last is { } l ? (now - l).TotalDays : double.MaxValue;
            var warn = ctx.Settings.Diagnostics.UpdateWarningDays;
            var lastCheck = Check(root, C.WuLastUpdate, "Последнее обновление",
                last is null ? DiagnosticStatus.Warning : days > warn * 2 ? DiagnosticStatus.Error : days > warn ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                last is null ? "Нет данных об установленных обновлениях" : $"Последнее успешное обновление: {last.Value.ToLocalTime():dd.MM.yyyy} ({days:F0} дн. назад)");
            foreach (var e in h.Entries.Take(10))
                lastCheck.WithEvidence(e.Date.ToLocalTime().ToString("dd.MM.yyyy HH:mm"), $"{ResultText(e.ResultCode)}: {e.Title}");
            foreach (var hf in h.HotFixes) lastCheck.WithEvidence(hf.Id, hf.InstalledOn.ToString("dd.MM.yyyy"));
            if (days > warn) lastCheck.WithRecommendation("Запустите поиск обновлений в Центре обновления Windows.", A.OpenWindowsUpdate);

            var failed = h.Entries.Where(e => e.ResultCode is 4 or 5 && (now - e.Date).TotalDays <= 30).ToList();
            var codes = failed.Select(f => f.HResult).Where(c => c.Length > 0).Distinct().ToList();
            var err = Check(root, C.WuHistoryErrors, "Ошибки установки обновлений",
                    failed.Count == 0 ? DiagnosticStatus.Ok : failed.Count >= 3 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                    failed.Count == 0 ? (h.Error is null ? "Ошибок установки за 30 дней нет" : $"История недоступна: {h.Error}")
                                      : $"Неудачных установок за 30 дней: {failed.Count}; коды: {string.Join(", ", codes.Select(c => $"{c} ({WindowsUpdateErrors.Describe(c)})"))}")
                .WithEvidence("codes", string.Join(",", codes)).WithEvidence("failed", failed.Count);
            foreach (var f in failed.Take(10)) err.WithEvidence(f.Date.ToLocalTime().ToString("dd.MM.yyyy"), $"{f.HResult}: {f.Title}");
            if (failed.Count > 0) err.WithRecommendation("Изучите коды ошибок; часто помогает перезапуск служб Windows Update.", A.RestartWindowsUpdate, A.ResetWindowsUpdateCache);
        }
        else
        {
            Check(root, C.WuLastUpdate, "Последнее обновление", DiagnosticStatus.Warning, "Не удалось получить историю обновлений");
        }

        // Event log
        var ev = await _events.QueryAsync("Microsoft-Windows-WindowsUpdateClient/Operational", TimeSpan.FromDays(7), 200, false, ct).ConfigureAwait(false);
        if (ev.Available && !ev.AccessDenied)
        {
            var evCheck = Check(root, C.WuEvents, "События Windows Update (7 дней)", ev.Events.Count == 0 ? DiagnosticStatus.Ok : ev.Events.Count > 5 ? DiagnosticStatus.Warning : DiagnosticStatus.Info,
                ev.Events.Count == 0 ? "Ошибок в журнале WindowsUpdateClient нет" : $"Ошибок в журнале: {ev.Events.Count}");
            foreach (var e in ev.Events.Take(5)) evCheck.WithEvidence($"{e.TimeCreated:dd.MM HH:mm} ID {e.EventId}", Short(e.Message));
        }

        // Pending reboot
        var reasons = PendingReboot.Reasons(_registry);
        Check(root, C.WuPendingReboot, "Ожидание перезагрузки", reasons.Count > 0 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
            reasons.Count > 0 ? $"Требуется перезагрузка: {string.Join(", ", reasons)}" : "Перезагрузка не требуется");

        // Policy (WSUS)
        var wsus = _registry.GetValue(RegistryHive.LocalMachine, @"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "WUServer") as string;
        var noAuto = _registry.GetValue(RegistryHive.LocalMachine, @"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU", "NoAutoUpdate");
        Check(root, C.WuPolicy, "Политика обновлений", Convert.ToInt32(noAuto ?? 0) == 1 ? DiagnosticStatus.Warning : DiagnosticStatus.Info,
                (string.IsNullOrEmpty(wsus) ? "Сервер обновлений Microsoft" : $"WSUS: {wsus}") + (Convert.ToInt32(noAuto ?? 0) == 1 ? "; автоматическое обновление отключено политикой" : ""))
            .WithEvidence("wsus", wsus);
    }

    private void ServiceCheck(DiagnosticResult root, string id, string name, string svcName)
    {
        var s = _services.Get(svcName);
        // wuauserv/BITS are demand-start: "Stopped + Manual" is normal. Disabled is the problem.
        var status = s.State == ServiceState.NotFound ? DiagnosticStatus.Error
            : s.StartMode == ServiceStartMode.Disabled ? DiagnosticStatus.Error
            : DiagnosticStatus.Ok;
        var c = Check(root, id, name, status,
                status == DiagnosticStatus.Ok ? $"{s.State}, запуск: {s.StartMode}" : s.State == ServiceState.NotFound ? "Служба не найдена" : $"Служба отключена (Disabled), состояние {s.State}")
            .WithEvidence("state", s.State).WithEvidence("startMode", s.StartMode);
        if (status != DiagnosticStatus.Ok) c.WithRecommendation("Верните тип запуска службы «Вручную» и перезапустите службы Windows Update.", A.RestartWindowsUpdate);
    }

    private static string ResultText(int code) => code switch
    {
        2 => "Успешно", 3 => "Успешно с ошибками", 4 => "Ошибка", 5 => "Прервано", 1 => "Выполняется", _ => "Неизвестно"
    };

    private static string Short(string s) { var l = s.Split('\n')[0].Trim(); return l.Length > 160 ? l[..160] + "…" : l; }
}
