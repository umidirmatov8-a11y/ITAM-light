using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Reporting;

namespace FirstAidAdmin.Application.Cli;

public sealed class CliOptions
{
    public ProblemScenario? Scenario { get; set; }
    public List<string> ExtraModules { get; } = new();
    public bool Report { get; set; }
    public bool Zip { get; set; }
    public bool Json { get; set; }
    public bool Help { get; set; }
    public bool List { get; set; }
    public bool Redact { get; set; }
    public bool Quiet { get; set; }
    public string? CaseProblem { get; set; }
    public bool CreateCase { get; set; }
    public string? OutputFolder { get; set; }
    public Dictionary<string, string> Inputs { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> Errors { get; } = new();
}

/// <summary>
/// Command line interface using exactly the same diagnostic core as the GUI.
/// The CLI is read-only: it diagnoses and reports, it never runs remediation.
/// </summary>
public sealed class CliRunner
{
    public const int ExitOk = 0, ExitWarnings = 1, ExitProblems = 2, ExitUsage = 3, ExitError = 4;

    private static readonly HashSet<string> CliArgs = new(StringComparer.OrdinalIgnoreCase)
    {
        "diagnose", "full", "firstresponse", "first-response", "quick", "network", "internet", "dns", "wifi", "wi-fi", "domain", "ad", "login", "logon",
        "rdp", "printer", "print", "update", "windowsupdate", "wu", "disk", "storage", "health", "errors", "performance", "slow", "perf", "boot",
        "security", "service", "services", "app", "application", "share", "report", "case", "zip", "json", "help", "?", "h", "list", "redact",
        "quiet", "sfc", "dismscan", "target", "port", "exe", "out", "service-name", "allow-launch", "printer-host"
    };

    private readonly DiagnosticSession _session;
    private readonly TextWriter _out;

    public CliRunner(DiagnosticSession session, TextWriter output)
    {
        _session = session;
        _out = output;
    }

    /// <summary>True when the arguments request CLI mode (so the GUI must not start).</summary>
    public static bool IsCliInvocation(IReadOnlyList<string> args)
        => args.Any(a => (a.StartsWith('/') || a.StartsWith('-')) && CliArgs.Contains(Key(a)));

    private static string Key(string arg)
    {
        var a = arg.TrimStart('/', '-');
        var idx = a.IndexOfAny(new[] { ':', '=' });
        return idx >= 0 ? a[..idx] : a;
    }

    public static CliOptions Parse(IReadOnlyList<string> args)
    {
        var o = new CliOptions();
        for (var i = 0; i < args.Count; i++)
        {
            var raw = args[i];
            if (!(raw.StartsWith('/') || raw.StartsWith('-'))) { o.Errors.Add($"Неизвестный аргумент: {raw}"); continue; }
            var a = raw.TrimStart('/', '-');
            var idx = a.IndexOfAny(new[] { ':', '=' });
            var key = (idx >= 0 ? a[..idx] : a).ToLowerInvariant();
            var value = idx >= 0 ? a[(idx + 1)..].Trim('"') : null;
            // Allow "/case "text"" style: value as the next non-switch argument.
            if (value is null && key is "case" or "target" or "port" or "share" or "app" or "exe" or "out" or "service-name" or "printer-host"
                && i + 1 < args.Count && !args[i + 1].StartsWith('/') && !args[i + 1].StartsWith('-'))
                value = args[++i];

            switch (key)
            {
                case "help" or "?" or "h": o.Help = true; break;
                case "list": o.List = true; break;
                case "report": o.Report = true; break;
                case "zip": o.Zip = true; break;
                case "json": o.Json = true; break;
                case "redact": o.Redact = true; break;
                case "quiet": o.Quiet = true; break;
                case "out": o.OutputFolder = value; break;
                case "case": o.CreateCase = true; o.CaseProblem = value; break;
                case "sfc": o.ExtraModules.Add(ModuleIds.Sfc); break;
                case "dismscan": o.ExtraModules.Add(ModuleIds.DismScan); break;
                case "target": if (value is not null) o.Inputs[InputKeys.RdpTarget] = value; break;
                case "port": if (value is not null) o.Inputs[InputKeys.RdpPort] = value; break;
                case "exe": if (value is not null) o.Inputs[InputKeys.AppExe] = value; break;
                case "service-name": if (value is not null) o.Inputs[InputKeys.ServiceName] = value; break;
                case "printer-host": if (value is not null) o.Inputs[InputKeys.PrinterHost] = value; break;
                case "allow-launch": o.Inputs[InputKeys.AppAllowLaunch] = "true"; break;
                case "share":
                    o.Scenario ??= ProblemScenario.NetworkShare;
                    if (value is not null) o.Inputs[InputKeys.SharePath] = value;
                    break;
                case "app" or "application":
                    o.Scenario ??= ProblemScenario.ApplicationNotWorking;
                    if (value is not null) o.Inputs[InputKeys.AppName] = value;
                    break;
                default:
                    var s = ScenarioCatalog.Parse(key);
                    if (s is null) o.Errors.Add($"Неизвестный параметр: {raw}");
                    else
                    {
                        o.Scenario = s;
                        if (key is "rdp" && value is not null) o.Inputs[InputKeys.RdpTarget] = value;
                        if (key is "service" or "services" && value is not null) o.Inputs[InputKeys.ServiceName] = value;
                    }
                    break;
            }
        }
        if (o.CreateCase && o.Scenario is null) o.Scenario = ProblemScenario.FirstResponse;
        if ((o.Report || o.Zip || o.Json) && o.Scenario is null && o.ExtraModules.Count == 0) o.Scenario = ProblemScenario.FullDiagnostics;
        return o;
    }

    public static string Usage => """
        Первая помощь сисадмина — SysAdmin First Response Toolkit (CLI)

        Использование: FirstAidAdmin.exe <команда> [параметры]

        Команды диагностики:
          /diagnose            Полная диагностика
          /firstresponse       Быстрая первичная диагностика (1–3 мин)
          /network             Нет интернета (сеть, DNS, Wi-Fi)
          /dns /wifi /domain /login /printer /update /disk /health /performance /security /boot
          /rdp[:host] [/port:3389]   Диагностика RDP (опционально — проверка доступности узла)
          /app:"имя" [/exe:путь] [/allow-launch]   Не работает программа
          /share:\\сервер\ресурс     Не работает сетевой ресурс
          /services [/service-name:имя]
          /sfc /dismscan       Длительные проверки (нужны права администратора)

        Отчёты и обращения:
          /report              Сохранить report.html и report.json (по умолчанию — полная диагностика)
          /case:"описание"     Создать обращение (CASE), выполнить диагностику и собрать ZIP-пакет
          /zip                 Собрать пакет диагностики (ZIP, с маскированием данных)
          /json                Вывести JSON-отчёт в stdout
          /out:папка           Папка для отчётов
          /redact              Маскировать данные и в report.html/report.json
          /list                Список сценариев и модулей

        Коды возврата: 0 — норма, 1 — предупреждения, 2 — проблемы, 3 — ошибка параметров, 4 — внутренняя ошибка.
        CLI ничего не исправляет: исправления выполняются только в окне программы с подтверждением.
        """;

    public async Task<int> RunAsync(IReadOnlyList<string> args, CancellationToken cancellationToken)
    {
        var o = Parse(args);
        if (o.Help) { _out.WriteLine(Usage); return ExitOk; }
        if (o.Errors.Count > 0)
        {
            foreach (var e in o.Errors) _out.WriteLine(e);
            _out.WriteLine("Справка: FirstAidAdmin.exe /help");
            return ExitUsage;
        }
        if (o.List) { PrintList(); return ExitOk; }
        if (o.Scenario is null && o.ExtraModules.Count == 0) { _out.WriteLine(Usage); return ExitUsage; }

        try
        {
            var sys = _session.RefreshSystem();
            if (!o.Quiet && !o.Json)
            {
                _out.WriteLine($"Первая помощь сисадмина v{AppInfo.Version}");
                _out.WriteLine($"{sys.MachineName} | {sys.QualifiedUser} | {(sys.IsAdmin ? "Administrator" : "User")} | {sys.OsDescription}");
                _out.WriteLine();
            }
            if (o.CreateCase)
            {
                var c = _session.CreateCase(o.CaseProblem ?? (o.Scenario is { } sc ? ScenarioCatalog.Get(sc).Title : "Диагностика"), o.Scenario);
                if (!o.Json) _out.WriteLine($"{c.DisplayId} создано");
            }

            var progress = o.Quiet || o.Json ? null : new ConsoleProgress(_out);
            if (o.Scenario is { } scenario)
                await _session.RunScenarioAsync(scenario, o.Inputs, progress, cancellationToken).ConfigureAwait(false);
            if (o.ExtraModules.Count > 0)
                await _session.RunModulesAsync(o.ExtraModules, o.Inputs, progress, cancellationToken).ConfigureAwait(false);

            var report = await _session.BuildReportAsync().ConfigureAwait(false);
            if (o.Json)
                _out.WriteLine(JsonSerializer.Serialize(report, JsonDefaults.Indented));
            else
                PrintSummary(report);

            if (o.Report || o.CreateCase)
            {
                var folder = o.OutputFolder ?? _session.OutputFolder();
                var files = await _session.ExportReportAsync(folder, o.Redact).ConfigureAwait(false);
                if (!o.Json) foreach (var f in files) _out.WriteLine($"Отчёт: {f}");
            }
            if (o.Zip || o.CreateCase)
            {
                var zip = await _session.BuildPackageAsync(o.OutputFolder).ConfigureAwait(false);
                if (!o.Json) _out.WriteLine($"Пакет диагностики: {zip}");
            }

            return report.Summary.ProblemCount > 0 ? ExitProblems : report.Summary.WarningCount > 0 ? ExitWarnings : ExitOk;
        }
        catch (OperationCanceledException)
        {
            _out.WriteLine("Отменено.");
            return ExitError;
        }
        catch (Exception ex)
        {
            _out.WriteLine($"Ошибка: {ex.Message}");
            return ExitError;
        }
    }

    private void PrintList()
    {
        _out.WriteLine("Сценарии:");
        foreach (var s in ScenarioCatalog.All)
            _out.WriteLine($"  {s.Scenario,-22} {s.Title} — {string.Join(", ", s.Modules)}");
        _out.WriteLine();
        _out.WriteLine("Модули:");
        foreach (var m in _session.Runner.Modules.OrderBy(m => m.Id))
            _out.WriteLine($"  {m.Id,-16} {m.Name}{(m is IDiagnosticModuleInfo { IsLongRunning: true } ? " (длительный)" : "")}");
    }

    public static string Tag(DiagnosticStatus s) => s switch
    {
        DiagnosticStatus.Ok => "[ OK ]",
        DiagnosticStatus.Warning => "[WARN]",
        DiagnosticStatus.Error => "[FAIL]",
        DiagnosticStatus.Critical => "[CRIT]",
        DiagnosticStatus.Skipped => "[SKIP]",
        _ => "[INFO]"
    };

    private void PrintSummary(DiagnosticReport r)
    {
        _out.WriteLine();
        _out.WriteLine("═══════════════ РЕЗУЛЬТАТЫ ═══════════════");
        foreach (var m in r.Results)
        {
            _out.WriteLine($"{Tag(m.Status)} {m.Name}: {m.Summary}");
            foreach (var c in m.Checks.Where(c => c.Status is not DiagnosticStatus.Ok and not DiagnosticStatus.Info))
                _out.WriteLine($"   {Tag(c.Status)} {c.Name}: {c.Summary}");
        }
        _out.WriteLine();
        _out.WriteLine("═══════════════ ИТОГ ДИАГНОСТИКИ ═══════════════");
        _out.WriteLine($"Норма: {r.Summary.OkCount}   Предупреждения: {r.Summary.WarningCount}   Проблемы: {r.Summary.ProblemCount}   Пропущено: {r.Summary.SkippedCount}");
        if (r.Findings.Count > 0)
        {
            _out.WriteLine();
            _out.WriteLine("НАХОДКИ:");
            var i = 0;
            foreach (var f in r.Findings)
            {
                _out.WriteLine($"{++i}. [{f.Severity.ToString().ToUpperInvariant()}] {f.Title} (уверенность: {SeverityEngine.Russian(f.Confidence)})");
                foreach (var b in f.Basis) _out.WriteLine($"     {(b.Supports ? "✓" : "✗")} {b.Text}");
                _out.WriteLine($"     Вероятная причина: {f.ProbableCause}");
                _out.WriteLine($"     Рекомендация: {f.Recommendation}");
            }
        }
        else
        {
            _out.WriteLine("Проблем не обнаружено.");
        }
        _out.WriteLine();
    }

    private sealed class ConsoleProgress : IProgress<DiagnosticProgress>
    {
        private readonly TextWriter _out;
        public ConsoleProgress(TextWriter output) => _out = output;
        public void Report(DiagnosticProgress p)
        {
            if (p.Result is null) _out.WriteLine($"[{p.Index + 1}/{p.Total}] {p.ModuleName}…");
        }
    }
}
