using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Reporting;

namespace FirstAidAdmin.App.Views;

/// <summary>Small code-built dialogs sharing the application theme.</summary>
public abstract class DialogBase : Window
{
    protected readonly StackPanel Body = new() { Margin = new Thickness(20) };
    protected readonly StackPanel Buttons = new() { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(20, 0, 20, 16) };

    protected DialogBase(string title, double width = 560)
    {
        Title = title;
        Width = width;
        SizeToContent = SizeToContent.Height;
        MaxHeight = 760;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        SetResourceReference(BackgroundProperty, "CardBrush");
        var root = new DockPanel();
        DockPanel.SetDock(Buttons, Dock.Bottom);
        root.Children.Add(Buttons);
        root.Children.Add(new ScrollViewer { Content = Body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto });
        Content = root;
    }

    protected TextBlock Text(string text, double size = 14, FontWeight? weight = null, string brush = "TextBrush", double bottom = 6)
    {
        var t = new TextBlock { Text = text, FontSize = size, FontWeight = weight ?? FontWeights.Normal, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, bottom) };
        t.SetResourceReference(TextBlock.ForegroundProperty, brush);
        Body.Children.Add(t);
        return t;
    }

    protected void Section(string header, string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        Text(header, 13, FontWeights.SemiBold, "MutedBrush", 2);
        Text(text, 14, null, "TextBrush", 10);
    }

    protected Button AddButton(string caption, bool primary, Action onClick)
    {
        var b = new Button { Content = caption, MinWidth = 110 };
        b.SetResourceReference(StyleProperty, primary ? "PrimaryButton" : "SecondaryButton");
        b.Click += (_, _) => onClick();
        Buttons.Children.Add(b);
        return b;
    }

    protected Border Badge(string text, string brush)
    {
        var t = new TextBlock { Text = text, Foreground = Brushes.White, FontWeight = FontWeights.Bold, FontSize = 12 };
        var b = new Border { Child = t, CornerRadius = new CornerRadius(8), Padding = new Thickness(8, 2, 8, 2), Margin = new Thickness(0, 0, 8, 8), HorizontalAlignment = HorizontalAlignment.Left };
        b.SetResourceReference(Border.BackgroundProperty, brush);
        return b;
    }
}

/// <summary>Confirmation before any system-changing action. HIGH risk shows an explicit warning.</summary>
public sealed class ConfirmDialog : DialogBase
{
    public ConfirmDialog(RemediationAction action, string? parameter) : base("Подтверждение действия")
    {
        Text(action.Title + (parameter is null ? "" : $" ({parameter})"), 18, FontWeights.Bold);
        var badges = new WrapPanel();
        badges.Children.Add(Badge($"Risk: {action.Risk.ToString().ToUpperInvariant()}", action.Risk switch { RiskLevel.High => "ErrBrush", RiskLevel.Medium => "WarnBrush", _ => "OkBrush" }));
        if (action.RequiresAdmin) badges.Children.Add(Badge("UAC: права администратора", "InfoBrush"));
        if (action.RequiresReboot) badges.Children.Add(Badge("Может потребоваться перезагрузка", "WarnBrush"));
        if (action.IsLongRunning) badges.Children.Add(Badge("Длительная операция", "SkipBrush"));
        Body.Children.Add(badges);
        if (action.Risk == RiskLevel.High)
            Text("⚠ Операция может изменить состояние системы.", 15, FontWeights.Bold, "ErrBrush", 10);
        Section("Что будет сделано", action.Description);
        Section("Что изменится", action.WhatChanges);
        Section("Команда", action.CommandPreview.Replace("<name>", parameter ?? "<name>"));
        Section("Обратимость", action.Reversible ? "Действие обратимо или не меняет систему." : "Действие не отменяется автоматически.");
        if (action.RequiresAdmin)
            Text("Windows покажет стандартный запрос UAC. Программа не обходит UAC и выполняет только эту операцию.", 12, null, "MutedBrush");
        AddButton(action.Risk == RiskLevel.High ? "Продолжить" : "Выполнить", true, () => { DialogResult = true; });
        AddButton("Отмена", false, () => { DialogResult = false; });
    }
}

public sealed class FeedbackDialog : DialogBase
{
    public UserFeedback Feedback { get; private set; } = UserFeedback.None;

    public FeedbackDialog(RemediationAction action, RemediationOutcome outcome) : base("Результат исправления", 480)
    {
        Text(action.Title, 16, FontWeights.Bold);
        Text("Повторная проверка: " + HtmlReportGenerator.OutcomeText(outcome), 15, FontWeights.SemiBold,
            outcome switch { RemediationOutcome.Resolved => "OkBrush", RemediationOutcome.Persists => "WarnBrush", RemediationOutcome.Failed => "ErrBrush", _ => "TextBrush" }, 14);
        if (action.RequiresReboot) Text("⟳ Для завершения может потребоваться перезагрузка.", 13, null, "WarnBrush");
        Text("Проблема решена?", 16, FontWeights.SemiBold);
        AddButton("Да", true, () => { Feedback = UserFeedback.Yes; DialogResult = true; });
        AddButton("Нет", false, () => { Feedback = UserFeedback.No; DialogResult = true; });
        AddButton("Не знаю", false, () => { Feedback = UserFeedback.DontKnow; DialogResult = true; });
    }
}

public sealed class TextDialog : DialogBase
{
    public TextDialog(string title, string text) : base(title, 760)
    {
        var box = new TextBox
        {
            Text = text, IsReadOnly = true, TextWrapping = TextWrapping.Wrap, FontFamily = new FontFamily("Consolas"), FontSize = 12,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, MaxHeight = 520, MinHeight = 200
        };
        Body.Children.Add(box);
        AddButton("Копировать", false, () => Clipboard.SetText(text));
        AddButton("Закрыть", true, Close);
    }
}

/// <summary>"Подробнее": the full reasoning behind a finding plus the knowledge base article.</summary>
public sealed class FindingDetailsDialog : DialogBase
{
    public FindingDetailsDialog(Finding f, KnowledgeEntry? kb) : base("Подробнее", 680)
    {
        Text($"{SeverityEngine.Icon(f.Severity)} {f.Title}", 18, FontWeights.Bold);
        Text($"Серьёзность: {f.Severity.ToString().ToUpperInvariant()}    Уверенность: {SeverityEngine.Russian(f.Confidence).ToUpperInvariant()}", 13, null, "MutedBrush", 10);
        Section("Что обнаружено", f.WhatWasFound);
        if (f.Basis.Count > 0) Section("Основания", string.Join("\n", f.Basis.Select(b => (b.Supports ? "✓ " : "✗ ") + b.Text)));
        Section("Вероятная причина", f.ProbableCause);
        Section("Рекомендация", f.Recommendation);
        if (f.MayRequireReboot) Section("Перезагрузка", "После исправления может потребоваться перезагрузка.");
        if (f.RelatedCheckIds.Count > 0) Section("Связанные проверки", string.Join(", ", f.RelatedCheckIds));
        if (kb is not null)
        {
            Text("📚 База знаний: " + kb.Problem, 15, FontWeights.Bold, "AccentBrush", 8);
            Section("Симптомы", string.Join("\n", kb.Symptoms.Select(s => "• " + s)));
            Section("Признаки", string.Join("\n", kb.Evidence.Select(s => "• " + s)));
            Section("Возможные причины", string.Join("\n", kb.PossibleCauses.Select(s => "• " + s)));
            Section("Что сделать", string.Join("\n", kb.Recommendations.Select((s, i) => $"{i + 1}. {s}")));
        }
        AddButton("Закрыть", true, Close);
    }
}

public sealed class ServiceDialog : DialogBase
{
    private readonly ComboBox _combo;
    public string? Selected => _combo.SelectedItem as string ?? (string.IsNullOrWhiteSpace(_combo.Text) ? null : _combo.Text);

    public ServiceDialog(IReadOnlyList<string> allowed) : base("Выбор службы", 420)
    {
        Text("Выберите службу (только из разрешённого списка):");
        _combo = new ComboBox { ItemsSource = allowed, SelectedIndex = 0, Margin = new Thickness(0, 4, 0, 4) };
        Body.Children.Add(_combo);
        AddButton("OK", true, () => DialogResult = true);
        AddButton("Отмена", false, () => DialogResult = false);
    }
}
