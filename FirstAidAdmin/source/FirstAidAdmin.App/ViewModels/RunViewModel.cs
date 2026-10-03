using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using FirstAidAdmin.App.Services;
using FirstAidAdmin.Application;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Remediation;
using FirstAidAdmin.Reporting;
using C = FirstAidAdmin.Core.CheckIds;

namespace FirstAidAdmin.App.ViewModels;

/// <summary>Problem → diagnostics → findings → (optional) remediation → re-test → report.</summary>
public sealed partial class RunViewModel : ObservableObject
{
    private readonly DiagnosticSession _session;
    private readonly IDialogService _dialogs;
    private readonly KnowledgeBaseService _kb;
    private readonly Action _goHome;
    private CancellationTokenSource? _cts;

    public RunViewModel(ScenarioDefinition definition, DiagnosticSession session, IDialogService dialogs, KnowledgeBaseService kb, Action goHome)
    {
        Definition = definition;
        _session = session;
        _dialogs = dialogs;
        _kb = kb;
        _goHome = goHome;
        foreach (var id in new[] { ActionIds.DismCheckHealth, ActionIds.SfcVerify, ActionIds.DismScanHealth })
            ElevatedChecks.Add(new ActionViewModel(RemediationCatalog.Find(id)!, null, ExecuteActionAsync));
    }

    public ScenarioDefinition Definition { get; }
    public string Title => $"{Definition.Icon} {Definition.Title}";
    public string Description => Definition.Description;

    // ── Inputs ──
    public bool ShowRdpInputs => Definition.Scenario == ProblemScenario.Rdp;
    public bool ShowAppInputs => Definition.Scenario == ProblemScenario.ApplicationNotWorking;
    public bool ShowShareInput => Definition.Scenario == ProblemScenario.NetworkShare;
    public bool ShowServiceInput => Definition.Scenario == ProblemScenario.ServiceNotWorking;
    public bool ShowElevatedChecks => Definition.Scenario is ProblemScenario.WindowsErrors or ProblemScenario.WindowsUpdate or ProblemScenario.FullDiagnostics;
    public bool HasInputs => ShowRdpInputs || ShowAppInputs || ShowShareInput || ShowServiceInput;

    [ObservableProperty] private string _rdpTarget = "";
    [ObservableProperty] private string _rdpPort = "3389";
    [ObservableProperty] private string _appName = "";
    [ObservableProperty] private string _appExe = "";
    [ObservableProperty] private bool _allowLaunch;
    [ObservableProperty] private string _sharePath = "";
    [ObservableProperty] private string _serviceName = "";

    // ── State ──
    [ObservableProperty, NotifyCanExecuteChangedFor(nameof(StartCommand), nameof(CancelCommand), nameof(ExportReportCommand), nameof(BuildPackageCommand))]
    private bool _isRunning;
    [ObservableProperty] private bool _hasRun;
    [ObservableProperty] private double _progressValue;
    [ObservableProperty] private double _progressMax = 1;
    [ObservableProperty] private string _statusText = "Нажмите «Начать диагностику». Проверки только читают состояние системы.";
    [ObservableProperty] private int _okCount;
    [ObservableProperty] private int _warningCount;
    [ObservableProperty] private int _problemCount;
    [ObservableProperty] private string _dashboardTitle = "";

    public ObservableCollection<ResultViewModel> Modules { get; } = new();
    public ObservableCollection<FindingViewModel> Findings { get; } = new();
    public ObservableCollection<DashboardTile> Dashboard { get; } = new();
    public ObservableCollection<ActionViewModel> ElevatedChecks { get; } = new();
    public bool HasNoFindings => HasRun && Findings.Count == 0;

    private Dictionary<string, string> BuildInputs()
    {
        var d = new Dictionary<string, string>();
        void Put(string key, string v) { if (!string.IsNullOrWhiteSpace(v)) d[key] = v.Trim(); }
        Put(InputKeys.RdpTarget, RdpTarget);
        Put(InputKeys.RdpPort, RdpPort);
        Put(InputKeys.AppName, AppName);
        Put(InputKeys.AppExe, AppExe);
        Put(InputKeys.SharePath, SharePath);
        Put(InputKeys.ServiceName, ServiceName);
        if (AllowLaunch) d[InputKeys.AppAllowLaunch] = "true";
        return d;
    }

    private bool CanStart() => !IsRunning;

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task StartAsync()
    {
        if (ShowShareInput && string.IsNullOrWhiteSpace(SharePath)) { _dialogs.Info("Укажите путь к ресурсу, например \\\\server\\share."); return; }
        if (ShowAppInputs && string.IsNullOrWhiteSpace(AppName) && string.IsNullOrWhiteSpace(AppExe)) { _dialogs.Info("Укажите название программы или путь к EXE."); return; }
        if (AllowLaunch && !_dialogs.Confirm("Пробный запуск программы", $"Программа «{(string.IsNullOrWhiteSpace(AppExe) ? AppName : AppExe)}» будет запущена от имени текущего пользователя для проверки. Продолжить?"))
            AllowLaunch = false;

        IsRunning = true;
        _cts = new CancellationTokenSource();
        var progress = new Progress<DiagnosticProgress>(p =>
        {
            ProgressMax = Math.Max(1, p.Total);
            ProgressValue = p.Index;
            StatusText = p.Message;
        });
        try
        {
            await _session.RunScenarioAsync(Definition.Scenario, BuildInputs(), progress, _cts.Token);
            StatusText = "Диагностика завершена";
        }
        catch (OperationCanceledException)
        {
            StatusText = "Диагностика отменена";
        }
        catch (Exception ex)
        {
            StatusText = "Ошибка: " + ex.Message;
        }
        finally
        {
            IsRunning = false;
            HasRun = true;
            ProgressValue = ProgressMax;
            Refresh();
        }
    }

    private bool CanCancel() => IsRunning;

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private void Cancel() => _cts?.Cancel();

    private bool CanExport() => !IsRunning && _session.Results.Count > 0;

    [RelayCommand(CanExecute = nameof(CanExport))]
    private async Task ExportReportAsync()
    {
        try
        {
            var files = await _session.ExportReportAsync(redact: false);
            StatusText = "Отчёт сохранён: " + string.Join(", ", files);
            var html = files.FirstOrDefault(f => f.EndsWith(".html", StringComparison.OrdinalIgnoreCase));
            if (html is not null) _dialogs.OpenFile(html);
        }
        catch (Exception ex) { _dialogs.Error("Не удалось сохранить отчёт: " + ex.Message); }
    }

    [RelayCommand(CanExecute = nameof(CanExport))]
    private async Task BuildPackageAsync()
    {
        try
        {
            var zip = await _session.BuildPackageAsync();
            StatusText = "Пакет диагностики: " + zip;
            _dialogs.ShowInFolder(zip);
        }
        catch (Exception ex) { _dialogs.Error("Не удалось собрать пакет: " + ex.Message); }
    }

    [RelayCommand]
    private void Back()
    {
        _cts?.Cancel();
        _goHome();
    }

    private async Task ExecuteActionAsync(ActionViewModel a)
    {
        if (IsRunning) return;
        var parameter = a.Parameter;
        if (a.Action.Parameter == "service" && parameter is null)
        {
            parameter = _dialogs.AskService(OperationExecutor.AllowedServices.OrderBy(s => s).ToList());
            if (parameter is null) return;
        }
        IsRunning = true;
        StatusText = $"Выполняется: {a.Action.Title}…";
        try
        {
            var run = await _session.RemediateAsync(a.Action.Id, parameter, CancellationToken.None);
            var rec = run.Record;
            StatusText = $"{a.Action.Title}: {HtmlReportGenerator.OutcomeText(rec.Outcome)}";
            if (rec.Outcome == RemediationOutcome.Failed)
                _dialogs.Error($"{a.Action.Title}\n\n{rec.Error}\n\n{Trim(rec.Output)}");
            else if (rec.Outcome == RemediationOutcome.Unknown && a.Action.Kind != RemediationKind.OpenTool && !string.IsNullOrWhiteSpace(rec.Output))
                _dialogs.ShowText(a.Action.Title, rec.Output);
        }
        catch (Exception ex)
        {
            _dialogs.Error(ex.Message);
        }
        finally
        {
            IsRunning = false;
            Refresh();
        }
    }

    private static string Trim(string s) => s.Length > 1500 ? s[..1500] + "…" : s;

    /// <summary>Re-reads results and findings from the session (after a run or a remediation).</summary>
    public void Refresh()
    {
        var order = Definition.Modules.ToList();
        var results = _session.Results
            .OrderBy(r => order.IndexOf(r.Id) is var i && i < 0 ? int.MaxValue : i)
            .ToList();
        Modules.Clear();
        foreach (var r in results) Modules.Add(new ResultViewModel(r));

        Findings.Clear();
        foreach (var f in _session.Findings)
            Findings.Add(new FindingViewModel(f, BuildActions(f, results), ShowDetails));

        var s = SeverityEngine.Summarize(results, _session.Findings);
        OkCount = s.OkCount;
        WarningCount = s.WarningCount;
        ProblemCount = s.ProblemCount;
        BuildDashboard(new ResultSet(results));
        OnPropertyChanged(nameof(HasNoFindings));
        ExportReportCommand.NotifyCanExecuteChanged();
        BuildPackageCommand.NotifyCanExecuteChanged();
    }

    private IEnumerable<ActionViewModel> BuildActions(Finding f, List<DiagnosticResult> results)
    {
        var set = new ResultSet(results);
        foreach (var id in f.RemediationIds.Distinct())
        {
            var action = RemediationCatalog.Find(id);
            if (action is null) continue;
            string? parameter = null;
            if (action.Parameter == "service")
            {
                parameter = f.RelatedCheckIds.Select(c => set.Evidence(c, "service")).FirstOrDefault(v => !string.IsNullOrEmpty(v))
                            ?? set.Get(C.ServicesCritical)?.Evidence.Select(e => e.Key).FirstOrDefault(k => OperationExecutor.AllowedServices.Contains(k));
                if (parameter is not null && !OperationExecutor.AllowedServices.Contains(parameter)) parameter = null;
            }
            yield return new ActionViewModel(action, parameter, ExecuteActionAsync);
        }
    }

    private void ShowDetails(FindingViewModel f) => _dialogs.ShowFindingDetails(f.Finding, _kb.FindFor(f.Finding));

    private void BuildDashboard(ResultSet s)
    {
        Dashboard.Clear();
        void Tile(string label, string checkId, Func<DiagnosticResult, string>? value = null)
        {
            var r = s.Get(checkId);
            if (r is null) return;
            Dashboard.Add(new DashboardTile(label, value?.Invoke(r) ?? (r.Status == DiagnosticStatus.Ok ? "OK" : r.Summary), r.Status));
        }

        switch (Definition.Scenario)
        {
            case ProblemScenario.Domain or ProblemScenario.CannotLogin:
                DashboardTitle = "🏢 Состояние домена";
                Tile("Domain", C.DomainMembership, r => r.GetEvidence("domain") ?? r.Summary);
                Tile("Domain Controller", C.DomainDcDiscovery, r => r.GetEvidence("dc") ?? r.Summary);
                Tile("Logon Server", C.DomainLogonServer, r => r.GetEvidence("logonServer") ?? r.Summary);
                Tile("Secure Channel", C.DomainSecureChannel);
                Tile("DNS (SRV)", C.DnsSrvLdap);
                Tile("Kerberos", C.DomainKerberos);
                Tile("Time Sync", C.DomainTime);
                Tile("Group Policy", C.DomainGpo);
                break;
            case ProblemScenario.SlowComputer or ProblemScenario.SlowBoot:
                DashboardTitle = "🐌 Сводка производительности";
                Tile("CPU", C.PerfCpu, r => (r.GetEvidence("cpuPercent") ?? "?") + "%");
                Tile("RAM", C.PerfRam, r => (r.GetEvidence("usedPercent") ?? "?") + "%");
                Tile("Disk C:", C.PerfDisk, r => (r.GetEvidence("usedPercent") ?? "?") + "%");
                Tile("Uptime", C.PerfUptime, r => (r.GetEvidence("days") ?? "?") + " дн.");
                Tile("Автозагрузка", C.PerfStartup);
                Tile("Загрузка ОС", C.PerfBoot);
                break;
            case ProblemScenario.NoInternet or ProblemScenario.WiFi or ProblemScenario.Dns:
                DashboardTitle = "🌐 Цепочка подключения";
                Tile("Адаптер", C.NetAdapters);
                Tile("IP-адрес", C.NetIPv4);
                Tile("Шлюз", C.NetGatewayPing);
                Tile("Интернет по IP", C.NetInternetIp);
                Tile("DNS", C.DnsResolveExternal);
                Tile("HTTP", C.NetHttp);
                Tile("Wi-Fi", C.WifiStage);
                break;
            default:
                DashboardTitle = "";
                break;
        }
    }
}
