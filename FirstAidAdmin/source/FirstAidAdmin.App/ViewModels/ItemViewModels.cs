using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Remediation;

namespace FirstAidAdmin.App.ViewModels;

public sealed class TileViewModel
{
    public TileViewModel(ScenarioDefinition def, Action<ScenarioDefinition> open, string? titleOverride = null)
    {
        Definition = def;
        Title = titleOverride ?? def.Title;
        Command = new CommunityToolkit.Mvvm.Input.RelayCommand(() => open(def));
    }

    public ScenarioDefinition Definition { get; }
    public string Icon => Definition.Icon;
    public string Title { get; }
    public string Description => Definition.Description;
    public System.Windows.Input.ICommand Command { get; }
}

/// <summary>A diagnostic result (module or check) shown in the results tree.</summary>
public sealed class ResultViewModel
{
    public ResultViewModel(DiagnosticResult r)
    {
        Result = r;
        Children = new ObservableCollection<ResultViewModel>(r.Checks.Select(c => new ResultViewModel(c)));
        Evidence = r.Evidence.Where(e => !string.IsNullOrWhiteSpace(e.Value)).Select(e => $"{e.Key}: {e.Value}").ToList();
    }

    public DiagnosticResult Result { get; }
    public string Name => Result.Name;
    public string Summary => Result.Summary;
    public DiagnosticStatus Status => Result.Status;
    public string Icon => SeverityEngine.Icon(Result.Status);
    public string StatusText => SeverityEngine.Russian(Result.Status);
    public string? Recommendation => Result.Recommendation;
    public string? Details => Result.Details;
    public string Duration => Result.Duration > TimeSpan.Zero ? $"{Result.Duration.TotalSeconds:F1} с" : "";
    public bool RequiresAdmin => Result.RequiresAdmin;
    public IReadOnlyList<string> Evidence { get; }
    public bool HasDetails => Evidence.Count > 0 || !string.IsNullOrWhiteSpace(Details);
    public ObservableCollection<ResultViewModel> Children { get; }
    public bool IsExpanded => Result.IsProblem || Result.IsWarning;
}

public sealed class ActionViewModel
{
    public ActionViewModel(RemediationAction action, string? parameter, Func<ActionViewModel, Task> execute)
    {
        Action = action;
        Parameter = parameter;
        Command = new CommunityToolkit.Mvvm.Input.AsyncRelayCommand(() => execute(this));
    }

    public RemediationAction Action { get; }
    public string? Parameter { get; }
    public string Title => Action.Kind == RemediationKind.OpenTool ? Action.Title : $"🔧 {Action.Title}{(Parameter is null ? "" : $" ({Parameter})")}";
    public RiskLevel Risk => Action.Risk;
    public string RiskText => $"Risk: {Action.Risk.ToString().ToUpperInvariant()}";
    public string Tooltip => $"{Action.Description}\nЧто изменится: {Action.WhatChanges}\nКоманда: {Action.CommandPreview}" +
                             (Action.RequiresAdmin ? "\nТребуются права администратора (UAC)" : "") +
                             (Action.RequiresReboot ? "\nМожет потребоваться перезагрузка" : "");
    public CommunityToolkit.Mvvm.Input.IAsyncRelayCommand Command { get; }
}

/// <summary>Finding card: what happened, how serious, why we think so, what to do.</summary>
public sealed class FindingViewModel
{
    public FindingViewModel(Finding f, IEnumerable<ActionViewModel> actions, Action<FindingViewModel> showDetails)
    {
        Finding = f;
        Actions = new ObservableCollection<ActionViewModel>(actions);
        DetailsCommand = new CommunityToolkit.Mvvm.Input.RelayCommand(() => showDetails(this));
    }

    public Finding Finding { get; }
    public string Title => $"{SeverityEngine.Icon(Finding.Severity)} {Finding.Title}";
    public Severity Severity => Finding.Severity;
    public string SeverityText => $"Серьёзность: {Finding.Severity.ToString().ToUpperInvariant()}";
    public string ConfidenceText => $"Уверенность: {SeverityEngine.Russian(Finding.Confidence).ToUpperInvariant()}";
    public string WhatWasFound => Finding.WhatWasFound;
    public string ProbableCause => Finding.ProbableCause;
    public string Recommendation => Finding.Recommendation;
    public IReadOnlyList<string> Basis => Finding.Basis.Select(b => (b.Supports ? "✓ " : "✗ ") + b.Text).ToList();
    public bool HasBasis => Finding.Basis.Count > 0;
    public string RebootText => Finding.MayRequireReboot ? "⟳ После исправления может потребоваться перезагрузка" : "";
    public ObservableCollection<ActionViewModel> Actions { get; }
    public bool HasActions => Actions.Count > 0;
    public System.Windows.Input.ICommand DetailsCommand { get; }
}

public sealed class DashboardTile
{
    public DashboardTile(string label, string value, DiagnosticStatus status)
    {
        Label = label;
        Value = value;
        Status = status;
    }

    public string Label { get; }
    public string Value { get; }
    public DiagnosticStatus Status { get; }
    public string Icon => SeverityEngine.Icon(Status);
}

public partial class TimelineItem : ObservableObject
{
    public TimelineItem(TimelineEntry e)
    {
        Time = e.Timestamp.ToLocalTime().ToString("HH:mm:ss");
        Message = e.Message;
        Kind = e.Kind;
    }

    public string Time { get; }
    public string Message { get; }
    public string Kind { get; }
}
