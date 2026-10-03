using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Engine;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Remediation;
using FirstAidAdmin.Reporting;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.Application;

/// <summary>
/// Orchestrates one support session: problem → diagnostics → correlation → findings → remediation → re-test → report.
/// UI and CLI both use it, so they share exactly the same diagnostic core.
/// </summary>
public sealed class DiagnosticSession
{
    // Checks whose OK status is worth a timeline line (the "story" of a network problem).
    private static readonly HashSet<string> KeyChecks = new(StringComparer.OrdinalIgnoreCase)
    {
        CheckIds.NetAdapters, CheckIds.NetGatewayPing, CheckIds.NetInternetIp, CheckIds.DnsResolveExternal, CheckIds.NetDnsResolve,
        CheckIds.DomainSecureChannel, CheckIds.RdpTargetTcp, CheckIds.PrinterSpooler, CheckIds.StorageSystem, CheckIds.WifiInterface
    };

    private readonly DiagnosticRunner _runner;
    private readonly CorrelationEngine _correlation;
    private readonly IAnalysisProvider _analysis;
    private readonly RemediationEngine _remediation;
    private readonly ISystemProbe _system;
    private readonly ICaseStore _cases;
    private readonly ICommandLog _commandLog;
    private readonly ILogger<DiagnosticSession> _logger;
    private readonly object _gate = new();
    private readonly List<DiagnosticResult> _results = new();
    private readonly List<RemediationRecord> _history = new();
    private readonly List<TimelineEntry> _timeline = new();

    public DiagnosticSession(DiagnosticRunner runner, CorrelationEngine correlation, IAnalysisProvider analysis, RemediationEngine remediation,
        ISystemProbe system, ICaseStore cases, ICommandLog commandLog, AppSettings settings, ILogger<DiagnosticSession> logger)
    {
        _runner = runner;
        _correlation = correlation;
        _analysis = analysis;
        _remediation = remediation;
        _system = system;
        _cases = cases;
        _commandLog = commandLog;
        Settings = settings;
        _logger = logger;
    }

    public AppSettings Settings { get; }
    public SystemSnapshot System { get; private set; } = new();
    public SupportCase? CurrentCase { get; private set; }
    public ProblemScenario? LastScenario { get; private set; }
    public List<Finding> Findings { get; private set; } = new();
    public IReadOnlyList<DiagnosticResult> Results { get { lock (_gate) return _results.ToList(); } }
    public IReadOnlyList<RemediationRecord> RemediationHistory { get { lock (_gate) return _history.ToList(); } }
    public IReadOnlyList<TimelineEntry> Timeline { get { lock (_gate) return (CurrentCase?.Timeline ?? _timeline).ToList(); } }
    public DiagnosticRunner Runner => _runner;
    public ICommandLog CommandLog => _commandLog;

    public event EventHandler<TimelineEntry>? TimelineChanged;

    /// <summary>Fast startup info only: OS, host, user, admin, basic network.</summary>
    public SystemSnapshot RefreshSystem()
    {
        System = _system.GetSnapshot();
        return System;
    }

    public void AddTimeline(string kind, string message)
    {
        var entry = new TimelineEntry(DateTimeOffset.Now, kind, message);
        lock (_gate)
        {
            if (CurrentCase is not null) CurrentCase.Timeline.Add(entry);
            else _timeline.Add(entry);
        }
        TimelineChanged?.Invoke(this, entry);
        SaveCase();
    }

    public SupportCase CreateCase(string problem, ProblemScenario? scenario = null, string? computer = null, string? user = null)
    {
        if (string.IsNullOrEmpty(System.MachineName)) RefreshSystem();
        var c = _cases.Create(problem, scenario, computer ?? System.MachineName, user ?? System.QualifiedUser);
        lock (_gate)
        {
            // Earlier activity in this session belongs to the new case as well.
            c.Timeline.InsertRange(0, _timeline);
            _timeline.Clear();
            c.Results.AddRange(_results);
            c.RemediationHistory.AddRange(_history);
            c.Findings = Findings.ToList();
            CurrentCase = c;
        }
        _logger.LogInformation("Case {CaseId} created", c.Id);
        SaveCase();
        TimelineChanged?.Invoke(this, c.Timeline[^1]);
        return c;
    }

    public void OpenCase(SupportCase existing)
    {
        lock (_gate)
        {
            CurrentCase = existing;
            _results.Clear();
            _results.AddRange(existing.Results);
            _history.Clear();
            _history.AddRange(existing.RemediationHistory);
            Findings = existing.Findings.ToList();
        }
        AddTimeline("case", "Case opened");
    }

    public void CloseCase()
    {
        if (CurrentCase is null) return;
        AddTimeline("case", "Case closed");
        CurrentCase.ClosedAt = DateTimeOffset.Now;
        SaveCase();
        lock (_gate)
        {
            CurrentCase = null;
            _results.Clear();
            _history.Clear();
            _timeline.Clear();
            Findings = new List<Finding>();
        }
    }

    public DiagnosticContext CreateContext(IReadOnlyDictionary<string, string>? inputs = null, IProgress<DiagnosticProgress>? progress = null)
    {
        if (string.IsNullOrEmpty(System.MachineName)) RefreshSystem();
        var ctx = new DiagnosticContext
        {
            Settings = Settings,
            System = System,
            Inputs = inputs ?? new Dictionary<string, string>(),
            Logger = _logger,
            Progress = progress
        };
        lock (_gate)
            foreach (var r in _results) ctx.PreviousResults[r.Id] = r;
        return ctx;
    }

    public Task<List<DiagnosticResult>> RunScenarioAsync(ProblemScenario scenario, IReadOnlyDictionary<string, string>? inputs,
        IProgress<DiagnosticProgress>? progress, CancellationToken cancellationToken)
    {
        LastScenario = scenario;
        var def = ScenarioCatalog.Get(scenario);
        if (CurrentCase is not null && CurrentCase.Scenario is null) CurrentCase.Scenario = scenario;
        AddTimeline("scenario", $"Сценарий «{def.Title}» запущен");
        return RunModulesAsync(def.Modules, inputs, progress, cancellationToken);
    }

    public async Task<List<DiagnosticResult>> RunModulesAsync(IEnumerable<string> moduleIds, IReadOnlyDictionary<string, string>? inputs,
        IProgress<DiagnosticProgress>? progress, CancellationToken cancellationToken)
    {
        RefreshSystem();
        var ctx = CreateContext(inputs, new SyncProgress(p =>
        {
            if (p.Result is null) AddTimeline("module", $"{p.ModuleName}: диагностика начата");
            else LogResult(p.Result);
            progress?.Report(p);
        }));

        List<DiagnosticResult> results;
        try
        {
            results = await _runner.RunAsync(moduleIds, ctx, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            AddTimeline("module", "Диагностика отменена пользователем");
            throw;
        }
        Merge(results);
        Analyze();
        return results;
    }

    private void LogResult(DiagnosticResult module)
    {
        foreach (var c in module.Checks)
        {
            if (c.IsProblem || c.IsWarning) AddTimeline("check", $"{c.Name} {(c.IsProblem ? "FAILED" : "WARNING")}: {c.Summary}");
            else if (c.Status == DiagnosticStatus.Ok && KeyChecks.Contains(c.Id)) AddTimeline("check", $"{c.Name} OK");
        }
        AddTimeline("module", $"{module.Name}: {module.Summary}");
    }

    private void Merge(IEnumerable<DiagnosticResult> results)
    {
        lock (_gate)
        {
            foreach (var r in results)
            {
                _results.RemoveAll(x => x.Id.Equals(r.Id, StringComparison.OrdinalIgnoreCase));
                _results.Add(r);
            }
            if (CurrentCase is not null)
            {
                CurrentCase.Results.Clear();
                CurrentCase.Results.AddRange(_results);
            }
        }
    }

    public List<Finding> Analyze()
    {
        List<DiagnosticResult> snapshot;
        lock (_gate) snapshot = _results.ToList();
        var findings = _correlation.Analyze(snapshot);
        lock (_gate)
        {
            Findings = findings;
            if (CurrentCase is not null) CurrentCase.Findings = findings.ToList();
        }
        SaveCase();
        return findings;
    }

    public async Task<RemediationRun> RemediateAsync(string actionId, string? parameter, CancellationToken cancellationToken)
    {
        var action = RemediationCatalog.Find(actionId);
        AddTimeline("remediation", $"{action?.Title ?? actionId}: запрошено (Risk: {action?.Risk.ToString().ToUpperInvariant()})");
        var ctx = CreateContext();
        var run = await _remediation.ExecuteAsync(actionId, parameter, ctx, cancellationToken).ConfigureAwait(false);
        lock (_gate)
        {
            _history.Add(run.Record);
            if (CurrentCase is not null) CurrentCase.RemediationHistory.Add(run.Record);
        }
        AddTimeline("remediation", $"{run.Record.Title}: {HtmlReportGenerator.OutcomeText(run.Record.Outcome)}" +
                                   (run.Record.Error is null ? "" : $" ({run.Record.Error})"));
        foreach (var line in run.Record.RetestSummary) AddTimeline("retest", "Re-test: " + line);
        if (run.Record.Feedback != UserFeedback.None) AddTimeline("feedback", $"Отзыв: {HtmlReportGenerator.FeedbackText(run.Record.Feedback)}");
        if (run.RetestResults.Count > 0)
        {
            Merge(run.RetestResults);
            Analyze();
        }
        SaveCase();
        return run;
    }

    public void SetFeedback(RemediationRecord record, UserFeedback feedback)
    {
        record.Feedback = feedback;
        AddTimeline("feedback", $"{record.Title}: {HtmlReportGenerator.FeedbackText(feedback)}");
    }

    public async Task<DiagnosticReport> BuildReportAsync()
    {
        List<DiagnosticResult> results;
        lock (_gate) results = _results.ToList();
        var report = new DiagnosticReport
        {
            AppVersion = AppInfo.Version,
            GeneratedAt = DateTimeOffset.Now,
            Scenario = LastScenario,
            System = string.IsNullOrEmpty(System.MachineName) ? RefreshSystem() : System,
            Case = CurrentCase,
            Results = results,
            RemediationHistory = RemediationHistory.ToList(),
            Timeline = Timeline.ToList()
        };
        var analysis = await _analysis.AnalyzeAsync(report).ConfigureAwait(false);
        report.Findings = analysis.Findings;
        report.Summary = analysis.Summary;
        report.AnalysisProvider = analysis.Provider;
        return report;
    }

    public string OutputFolder()
    {
        var root = Settings.ResolveReportFolder();
        return CurrentCase is null ? Path.Combine(root, $"Report-{DateTime.Now:yyyyMMdd-HHmmss}") : Path.Combine(root, CurrentCase.FileStem);
    }

    public Redactor CreateRedactor()
    {
        var netbios = Environment.UserDomainName;
        return new Redactor(Settings.Security, System.UserName, System.MachineName, System.DomainName, netbios);
    }

    /// <summary>Writes report.html / report.json according to settings. Returns written file paths.</summary>
    public async Task<List<string>> ExportReportAsync(string? folder = null, bool redact = false)
    {
        var report = await BuildReportAsync().ConfigureAwait(false);
        folder ??= OutputFolder();
        Directory.CreateDirectory(folder);
        var redactor = redact ? CreateRedactor() : null;
        var written = new List<string>();
        if (Settings.Reports.Format is ReportFormat.Html or ReportFormat.Both)
        {
            var p = Path.Combine(folder, "report.html");
            await File.WriteAllTextAsync(p, Apply(redactor, new HtmlReportGenerator().Generate(report))).ConfigureAwait(false);
            written.Add(p);
        }
        if (Settings.Reports.Format is ReportFormat.Json or ReportFormat.Both)
        {
            var p = Path.Combine(folder, "report.json");
            await File.WriteAllTextAsync(p, Apply(redactor, new JsonReportGenerator().Generate(report))).ConfigureAwait(false);
            written.Add(p);
        }
        AddTimeline("export", $"Report exported: {folder}");
        if (Settings.Reports.AutoZip) written.Add(await BuildPackageAsync(Path.GetDirectoryName(folder)).ConfigureAwait(false));
        return written;
    }

    private static string Apply(Redactor? r, string s) => r is null ? s : r.Redact(s);

    /// <summary>Builds the diagnostic ZIP package (always redacted).</summary>
    public async Task<string> BuildPackageAsync(string? folder = null)
    {
        AddTimeline("export", "Case exported (diagnostic package)");
        var report = await BuildReportAsync().ConfigureAwait(false);
        folder ??= Settings.ResolveReportFolder();
        var stem = CurrentCase?.FileStem ?? $"Diagnostics-{DateTime.Now:yyyyMMdd-HHmmss}";
        var path = new DiagnosticPackageBuilder().Build(report, _commandLog.Render(), folder, CreateRedactor(), stem);
        _logger.LogInformation("Diagnostic package created: {Path}", path);
        return path;
    }

    private void SaveCase()
    {
        var c = CurrentCase;
        if (c is null) return;
        try
        {
            lock (_gate) _cases.Save(c);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not save case {CaseId}", c.Id);
        }
    }

    /// <summary>Synchronous progress (System.Progress posts to the captured context, which would reorder timeline entries).</summary>
    private sealed class SyncProgress : IProgress<DiagnosticProgress>
    {
        private readonly Action<DiagnosticProgress> _action;
        public SyncProgress(Action<DiagnosticProgress> action) => _action = action;
        public void Report(DiagnosticProgress value) => _action(value);
    }
}
