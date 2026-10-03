using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Printer;

public sealed record PrinterInfo(string Name, bool IsDefault, bool WorkOffline, int PrinterStatus, int ErrorState, string PortName, bool IsNetwork, string Driver);
public sealed record PrinterPort(string Name, string Host, int Port);
public sealed record PrintJob(string Printer, string Status);
public sealed record PrinterInventory(IReadOnlyList<PrinterInfo> Printers, IReadOnlyList<PrinterPort> Ports, IReadOnlyList<PrintJob> Jobs);

public sealed class PrinterModule : DiagnosticModuleBase
{
    public const string Script =
        "$pr=Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Select Name,Default,WorkOffline,PrinterStatus,DetectedErrorState,PortName,Network,DriverName;" +
        "$po=Get-CimInstance Win32_TCPIPPrinterPort -ErrorAction SilentlyContinue | Select Name,HostAddress,PortNumber;" +
        "$jb=Get-CimInstance Win32_PrintJob -ErrorAction SilentlyContinue | Select Name,JobStatus,Status;" +
        "@{printers=@($pr);ports=@($po);jobs=@($jb)} | ConvertTo-Json -Depth 3 -Compress";

    private static readonly string[] VirtualPrinterMarkers = { "pdf", "xps", "onenote", "fax", "send to", "отправить" };

    private readonly IServiceProbe _services;
    private readonly IPowerShellRunner _ps;
    private readonly INetworkProbe _net;

    public PrinterModule(IServiceProbe services, IPowerShellRunner ps, INetworkProbe net)
    {
        _services = services;
        _ps = ps;
        _net = net;
    }

    public override string Id => ModuleIds.Printer;
    public override string Name => "Принтеры";
    public override DiagnosticCategory Category => DiagnosticCategory.Printer;

    public static bool IsVirtual(PrinterInfo p) => VirtualPrinterMarkers.Any(m => p.Name.Contains(m, StringComparison.OrdinalIgnoreCase) || p.PortName.Contains("PORTPROMPT", StringComparison.OrdinalIgnoreCase));

    public static string ErrorStateText(int s) => s switch
    {
        3 => "мало бумаги", 4 => "нет бумаги", 5 => "мало тонера", 6 => "нет тонера", 7 => "открыта крышка",
        8 => "замятие бумаги", 9 => "автономно", 10 => "требуется обслуживание", 11 => "лоток переполнен", _ => ""
    };

    public static bool HasProblem(PrinterInfo p) => p.WorkOffline || p.PrinterStatus is 6 or 7 || p.ErrorState is 4 or 6 or 7 or 8 or 9 or 10;

    public static PrinterInventory Parse(JsonElement root)
    {
        static string S(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
        static bool B(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.True;
        static int I(JsonElement e, string n) => e.TryGetProperty(n, out var v) && v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var i) ? i : 0;
        static IEnumerable<JsonElement> Arr(JsonElement r, string n) => r.TryGetProperty(n, out var v) ? v.ValueKind == JsonValueKind.Array ? v.EnumerateArray() : v.ValueKind == JsonValueKind.Object ? new[] { v } : Array.Empty<JsonElement>() : Array.Empty<JsonElement>();

        var printers = Arr(root, "printers").Select(p => new PrinterInfo(S(p, "Name"), B(p, "Default"), B(p, "WorkOffline"), I(p, "PrinterStatus"),
            I(p, "DetectedErrorState"), S(p, "PortName"), B(p, "Network"), S(p, "DriverName"))).ToList();
        var ports = Arr(root, "ports").Select(p => new PrinterPort(S(p, "Name"), S(p, "HostAddress"), I(p, "PortNumber") is var n and > 0 ? n : 9100)).ToList();
        var jobs = Arr(root, "jobs").Select(j =>
        {
            var name = S(j, "Name");
            var idx = name.LastIndexOf(',');
            return new PrintJob(idx > 0 ? name[..idx].Trim() : name, (S(j, "JobStatus") + " " + S(j, "Status")).Trim());
        }).ToList();
        return new PrinterInventory(printers, ports, jobs);
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var spooler = _services.Get("Spooler");
        if (spooler.State == ServiceState.NotFound && !ctx.System.IsWindows)
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Диагностика печати доступна только в Windows";
            return;
        }
        var spOk = spooler.State == ServiceState.Running;
        Check(root, C.PrinterSpooler, "Служба Print Spooler", spOk ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                spOk ? "Диспетчер печати запущен" : $"Диспетчер печати: {spooler.State}, тип запуска {spooler.StartMode}")
            .WithEvidence("state", spooler.State).WithEvidence("startMode", spooler.StartMode)
            .WithRecommendation(spOk ? "" : "Перезапустите Print Spooler.", spOk ? Array.Empty<string>() : new[] { ActionIds.RestartSpooler });

        var json = await _ps.RunJsonAsync(Script, TimeSpan.FromSeconds(40), ct).ConfigureAwait(false);
        if (json is null)
        {
            Check(root, C.PrinterInstalled, "Установленные принтеры", DiagnosticStatus.Warning, "Не удалось получить список принтеров (WMI/CIM)");
            return;
        }
        var inv = Parse(json.Value);
        var real = inv.Printers.Where(p => !IsVirtual(p)).ToList();
        var installed = Check(root, C.PrinterInstalled, "Установленные принтеры",
            real.Count > 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
            real.Count > 0 ? $"Принтеров: {real.Count} (+ виртуальных: {inv.Printers.Count - real.Count})" : "Физические принтеры не установлены");
        foreach (var p in inv.Printers) installed.WithEvidence(p.Name, $"port {p.PortName}; driver {p.Driver}{(p.IsDefault ? "; default" : "")}");

        var def = inv.Printers.FirstOrDefault(p => p.IsDefault);
        Check(root, C.PrinterDefault, "Принтер по умолчанию", def is null ? DiagnosticStatus.Warning : IsVirtual(def) && real.Count > 0 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
            def is null ? "Принтер по умолчанию не задан" : IsVirtual(def) && real.Count > 0 ? $"По умолчанию выбран виртуальный принтер «{def.Name}»" : $"По умолчанию: {def.Name}")
            .WithRecommendation(def is null || IsVirtual(def) ? "Выберите нужный принтер по умолчанию." : "", def is null || IsVirtual(def) ? new[] { A.OpenPrinters } : Array.Empty<string>());

        var problems = real.Where(HasProblem).ToList();
        var stCheck = Check(root, C.PrinterStatus, "Состояние принтеров", problems.Count == 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
            problems.Count == 0 ? "Принтеры без ошибок" : string.Join("; ", problems.Select(p => $"{p.Name}: {(p.WorkOffline ? "работает автономно" : ErrorStateText(p.ErrorState))}".TrimEnd(':', ' '))));
        if (problems.Count > 0) stCheck.WithRecommendation("Проверьте принтер (бумага, тонер, замятие), снимите режим «автономно».", A.OpenPrinters);

        var errorJobs = inv.Jobs.Where(j => j.Status.Contains("Error", StringComparison.OrdinalIgnoreCase) || j.Status.Contains("Degraded", StringComparison.OrdinalIgnoreCase)
                                            || j.Status.Contains("Paused", StringComparison.OrdinalIgnoreCase) || j.Status.Contains("Blocked", StringComparison.OrdinalIgnoreCase)).ToList();
        var q = Check(root, C.PrinterQueue, "Очередь печати",
                errorJobs.Count > 0 ? DiagnosticStatus.Warning : inv.Jobs.Count > 20 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                inv.Jobs.Count == 0 ? "Очередь пуста" : $"Заданий: {inv.Jobs.Count}, с ошибками: {errorJobs.Count}")
            .WithEvidence("jobs", inv.Jobs.Count).WithEvidence("errorJobs", errorJobs.Count);
        foreach (var j in inv.Jobs.Take(15)) q.WithEvidence(j.Printer, j.Status);
        if (errorJobs.Count > 0) q.WithRecommendation("Перезапустите Print Spooler или очистите очередь.", A.RestartSpooler, A.ClearPrintQueue);

        // Network printers reachability (TCP/IP ports)
        var netPorts = real.Select(p => inv.Ports.FirstOrDefault(port => port.Name.Equals(p.PortName, StringComparison.OrdinalIgnoreCase)))
            .Where(p => p is not null && !string.IsNullOrWhiteSpace(p.Host)).Cast<PrinterPort>().DistinctBy(p => p.Host).ToList();
        var extraHost = ctx.Input(Core.Abstractions.InputKeys.PrinterHost);
        if (extraHost is not null) netPorts.Add(new PrinterPort("input", extraHost, 9100));
        if (netPorts.Count == 0)
        {
            Check(root, C.PrinterNetwork, "Сетевые принтеры", DiagnosticStatus.Info, "Принтеров с TCP/IP-портом нет");
            return;
        }
        var results = await Task.WhenAll(netPorts.Select(async port =>
        {
            var tcp = await _net.TcpConnectAsync(port.Host, port.Port, ctx.Settings.Diagnostics.TcpTimeoutMs, ct).ConfigureAwait(false);
            if (tcp.Success) return (port, ok: true, info: $"{tcp.ElapsedMs} мс");
            var ping = await _net.PingAsync(port.Host, ctx.Settings.Diagnostics.PingTimeoutMs, ct).ConfigureAwait(false);
            return (port, ok: false, info: ping.Success ? $"ping OK, порт {port.Port} закрыт" : "не отвечает");
        })).ConfigureAwait(false);
        var bad = results.Where(r => !r.ok).ToList();
        var netCheck = Check(root, C.PrinterNetwork, "Сетевые принтеры", bad.Count == 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            bad.Count == 0 ? $"Доступны: {string.Join(", ", results.Select(r => r.port.Host))}" : $"Недоступны: {string.Join(", ", bad.Select(r => $"{r.port.Host} ({r.info})"))}");
        foreach (var r in results) netCheck.WithEvidence($"{r.port.Host}:{r.port.Port}", r.info);
    }
}
