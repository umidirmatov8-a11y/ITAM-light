using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using FirstAidAdmin.App.Services;
using FirstAidAdmin.Application;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Reporting;

namespace FirstAidAdmin.App.ViewModels;

public sealed partial class MainViewModel : ObservableObject
{
    private readonly DiagnosticSession _session;
    private readonly IDialogService _dialogs;
    private readonly KnowledgeBaseService _kb;
    private readonly ISettingsStore _settingsStore;
    private readonly ICaseStore _cases;
    private readonly IThemeService _theme;

    public MainViewModel(DiagnosticSession session, IDialogService dialogs, KnowledgeBaseService kb, ISettingsStore settingsStore, ICaseStore cases, IThemeService theme)
    {
        _session = session;
        _dialogs = dialogs;
        _kb = kb;
        _settingsStore = settingsStore;
        _cases = cases;
        _theme = theme;
        Home = new HomeViewModel(session.Settings, OpenScenario);
        Case = new CaseViewModel(session, cases, dialogs);
        Settings = new SettingsViewModel(session.Settings, settingsStore, theme, () => Home.Rebuild());
        _current = Home;
        _session.TimelineChanged += (_, _) => OnCaseChanged();
    }

    public HomeViewModel Home { get; }
    public CaseViewModel Case { get; }
    public SettingsViewModel Settings { get; }

    [ObservableProperty] private object _current;
    [ObservableProperty] private string _systemLine = "";
    [ObservableProperty] private string _adminBadge = "";
    [ObservableProperty] private bool _isAdmin;
    [ObservableProperty] private string _networkBadge = "";
    [ObservableProperty] private string _caseBadge = "";

    public string AppVersion => "v" + AppInfo.Version;

    /// <summary>Fast startup: OS, host, user, admin, basic network only.</summary>
    public void Initialize()
    {
        var s = _session.RefreshSystem();
        SystemLine = $"💻 {s.MachineName}   👤 {s.QualifiedUser}   🪟 {s.OsDescription}{(s.IsDomainJoined ? $"   🏢 {s.DomainName}" : "")}";
        IsAdmin = s.IsAdmin;
        AdminBadge = s.IsAdmin ? "🛡 Администратор" : "👤 Обычный пользователь";
        NetworkBadge = s.NetworkAvailable ? $"🌐 Сеть: {s.PrimaryIPv4 ?? "подключена"}" : "🌐 Сеть: нет подключения";
        OnCaseChanged();
    }

    private void OnCaseChanged()
    {
        var c = _session.CurrentCase;
        var text = c is null ? "" : $"📁 {c.DisplayId}";
        if (System.Windows.Application.Current?.Dispatcher is { } d && !d.CheckAccess()) d.BeginInvoke(() => CaseBadge = text);
        else CaseBadge = text;
    }

    private void OpenScenario(ScenarioDefinition def)
    {
        var vm = new RunViewModel(def, _session, _dialogs, _kb, GoHome);
        Current = vm;
        // Scenarios without required inputs start immediately: the admin chose the problem, the program picks the checks.
        if (!vm.HasInputs) vm.StartCommand.Execute(null);
    }

    [RelayCommand] private void GoHome() => Current = Home;
    [RelayCommand] private void OpenCase() { Case.Refresh(); Current = Case; }
    [RelayCommand] private void OpenSettings() => Current = Settings;
    [RelayCommand] private void ToggleMode()
    {
        _session.Settings.General.Mode = _session.Settings.General.Mode == UiMode.HelpDesk ? UiMode.Administrator : UiMode.HelpDesk;
        Home.Rebuild();
        Current = Home;
        try { _settingsStore.Save(_session.Settings); } catch { }
    }
    [RelayCommand] private void ToggleTheme()
    {
        _session.Settings.General.Theme = _session.Settings.General.Theme == AppTheme.Light ? AppTheme.Dark : AppTheme.Light;
        _theme.Apply(_session.Settings.General.Theme);
        try { _settingsStore.Save(_session.Settings); } catch { }
    }
}

public sealed partial class HomeViewModel : ObservableObject
{
    private static readonly ProblemScenario[] AdminPrimary =
    {
        ProblemScenario.NoInternet, ProblemScenario.SlowComputer, ProblemScenario.CannotLogin, ProblemScenario.Rdp,
        ProblemScenario.Printer, ProblemScenario.WindowsUpdate, ProblemScenario.Disk, ProblemScenario.WindowsErrors,
        ProblemScenario.WiFi, ProblemScenario.Dns, ProblemScenario.Domain, ProblemScenario.ApplicationNotWorking
    };

    private static readonly ProblemScenario[] AdminSecondary =
    {
        ProblemScenario.NetworkShare, ProblemScenario.ServiceNotWorking, ProblemScenario.SlowBoot, ProblemScenario.Security
    };

    private static readonly (ProblemScenario Scenario, string Title)[] HelpDesk =
    {
        (ProblemScenario.NoInternet, "Нет интернета"), (ProblemScenario.SlowComputer, "Компьютер тормозит"),
        (ProblemScenario.ApplicationNotWorking, "Не работает программа"), (ProblemScenario.CannotLogin, "Не могу войти"),
        (ProblemScenario.Printer, "Не работает принтер"), (ProblemScenario.Rdp, "Не работает RDP"), (ProblemScenario.FullDiagnostics, "Другое")
    };

    private readonly AppSettings _settings;
    private readonly Action<ScenarioDefinition> _open;

    public HomeViewModel(AppSettings settings, Action<ScenarioDefinition> open)
    {
        _settings = settings;
        _open = open;
        FirstResponse = new TileViewModel(ScenarioCatalog.Get(ProblemScenario.FirstResponse), open);
        Full = new TileViewModel(ScenarioCatalog.Get(ProblemScenario.FullDiagnostics), open);
        Rebuild();
    }

    public ObservableCollection<TileViewModel> Primary { get; } = new();
    public ObservableCollection<TileViewModel> Secondary { get; } = new();
    public TileViewModel FirstResponse { get; }
    public TileViewModel Full { get; }

    [ObservableProperty] private bool _isHelpDesk;
    [ObservableProperty] private string _heading = "";
    [ObservableProperty] private string _modeText = "";

    public void Rebuild()
    {
        Primary.Clear();
        Secondary.Clear();
        IsHelpDesk = _settings.General.Mode == UiMode.HelpDesk;
        if (IsHelpDesk)
        {
            Heading = "ЧТО ГОВОРИТ ПОЛЬЗОВАТЕЛЬ?";
            ModeText = "Режим: Help Desk";
            foreach (var (s, title) in HelpDesk) Primary.Add(new TileViewModel(ScenarioCatalog.Get(s), _open, title));
        }
        else
        {
            Heading = "ЧТО ПРОИЗОШЛО?";
            ModeText = "Режим: Администратор";
            foreach (var s in AdminPrimary) Primary.Add(new TileViewModel(ScenarioCatalog.Get(s), _open));
            foreach (var s in AdminSecondary) Secondary.Add(new TileViewModel(ScenarioCatalog.Get(s), _open));
        }
    }
}

public sealed partial class CaseViewModel : ObservableObject
{
    private readonly DiagnosticSession _session;
    private readonly ICaseStore _cases;
    private readonly IDialogService _dialogs;

    public CaseViewModel(DiagnosticSession session, ICaseStore cases, IDialogService dialogs)
    {
        _session = session;
        _cases = cases;
        _dialogs = dialogs;
        _session.TimelineChanged += (_, e) =>
        {
            var d = System.Windows.Application.Current?.Dispatcher;
            if (d is null || d.CheckAccess()) Timeline.Add(new TimelineItem(e));
            else d.BeginInvoke(() => Timeline.Add(new TimelineItem(e)));
        };
    }

    [ObservableProperty] private string _problem = "";
    [ObservableProperty] private string _computer = "";
    [ObservableProperty] private string _user = "";
    [ObservableProperty] private string _caseTitle = "";
    [ObservableProperty] private bool _hasCase;
    [ObservableProperty] private SupportCase? _selectedCase;

    public ObservableCollection<TimelineItem> Timeline { get; } = new();
    public ObservableCollection<RemediationRecord> History { get; } = new();
    public ObservableCollection<SupportCase> PreviousCases { get; } = new();

    public void Refresh()
    {
        var s = _session.System;
        if (string.IsNullOrEmpty(Computer)) Computer = s.MachineName;
        if (string.IsNullOrEmpty(User)) User = s.QualifiedUser;
        var c = _session.CurrentCase;
        HasCase = c is not null;
        CaseTitle = c is null ? "Обращение не создано" : $"{c.DisplayId} — {c.Problem}  ({c.Computer}, {c.User}, {c.CreatedAt:dd.MM.yyyy HH:mm})";
        Timeline.Clear();
        foreach (var t in _session.Timeline) Timeline.Add(new TimelineItem(t));
        History.Clear();
        foreach (var h in _session.RemediationHistory) History.Add(h);
        PreviousCases.Clear();
        try { foreach (var pc in _cases.List(30)) PreviousCases.Add(pc); } catch { }
    }

    [RelayCommand]
    private void Create()
    {
        if (string.IsNullOrWhiteSpace(Problem)) { _dialogs.Info("Опишите проблему, например «Нет интернета»."); return; }
        if (_session.CurrentCase is not null && !_dialogs.Confirm("Новое обращение", "Текущее обращение будет закрыто. Продолжить?")) return;
        if (_session.CurrentCase is not null) _session.CloseCase();
        _session.CreateCase(Problem.Trim(), null, Computer, User);
        Problem = "";
        Refresh();
    }

    [RelayCommand]
    private void Close()
    {
        _session.CloseCase();
        Refresh();
    }

    [RelayCommand]
    private void Open()
    {
        if (SelectedCase is null) return;
        var loaded = _cases.Load(SelectedCase.Id);
        if (loaded is null) return;
        _session.OpenCase(loaded);
        Refresh();
    }

    [RelayCommand]
    private async Task ExportAsync()
    {
        try
        {
            var zip = await _session.BuildPackageAsync();
            _dialogs.ShowInFolder(zip);
            Refresh();
        }
        catch (Exception ex) { _dialogs.Error(ex.Message); }
    }
}

public sealed partial class SettingsViewModel : ObservableObject
{
    private readonly ISettingsStore _store;
    private readonly IThemeService _theme;
    private readonly Action _changed;

    public SettingsViewModel(AppSettings settings, ISettingsStore store, IThemeService theme, Action changed)
    {
        Settings = settings;
        _store = store;
        _theme = theme;
        _changed = changed;
    }

    public AppSettings Settings { get; }
    public IReadOnlyList<UiMode> Modes { get; } = Enum.GetValues<UiMode>();
    public IReadOnlyList<AppTheme> Themes { get; } = Enum.GetValues<AppTheme>();
    public IReadOnlyList<ReportFormat> Formats { get; } = Enum.GetValues<ReportFormat>();
    public IReadOnlyList<string> Languages { get; } = new[] { "ru" };
    public string SettingsPath => _store.SettingsPath;
    public string ReportFolderHint => Settings.ResolveReportFolder();

    public string InternetProbeIps
    {
        get => string.Join(", ", Settings.Diagnostics.InternetProbeIps);
        set => Settings.Diagnostics.InternetProbeIps = Split(value);
    }

    public string ReferenceDns
    {
        get => string.Join(", ", Settings.Diagnostics.ReferenceDnsServers);
        set => Settings.Diagnostics.ReferenceDnsServers = Split(value);
    }

    public string DisabledModules
    {
        get => string.Join(", ", Settings.Diagnostics.DisabledModules);
        set => Settings.Diagnostics.DisabledModules = Split(value);
    }

    private static List<string> Split(string v) => v.Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();

    [ObservableProperty] private string _status = "";

    [RelayCommand]
    private void Save()
    {
        try
        {
            _store.Save(Settings);
            _theme.Apply(Settings.General.Theme);
            _changed();
            Status = "Настройки сохранены: " + _store.SettingsPath;
        }
        catch (Exception ex) { Status = "Ошибка сохранения: " + ex.Message; }
    }
}
