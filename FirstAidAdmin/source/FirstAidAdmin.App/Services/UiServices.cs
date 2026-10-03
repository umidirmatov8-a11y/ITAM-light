using System.Diagnostics;
using System.Windows;
using FirstAidAdmin.App.Views;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;

namespace FirstAidAdmin.App.Services;

public interface IDialogService
{
    void Info(string message);
    void Error(string message);
    bool Confirm(string title, string message);
    void ShowText(string title, string text);
    void ShowFindingDetails(Finding finding, KnowledgeEntry? entry);
    string? AskService(IReadOnlyList<string> allowed);
    void OpenFile(string path);
    void ShowInFolder(string path);
}

public interface IThemeService
{
    void Apply(AppTheme theme);
}

public sealed class ThemeService : IThemeService
{
    public void Apply(AppTheme theme)
    {
        var app = System.Windows.Application.Current;
        if (app is null) return;
        var dicts = app.Resources.MergedDictionaries;
        var old = dicts.FirstOrDefault(d => d.Source is not null && d.Source.OriginalString.Contains("/Themes/") && !d.Source.OriginalString.EndsWith("Styles.xaml"));
        var uri = new Uri($"pack://application:,,,/FirstAidAdmin;component/Themes/{theme}.xaml", UriKind.Absolute);
        var fresh = new ResourceDictionary { Source = uri };
        if (old is not null) dicts[dicts.IndexOf(old)] = fresh;
        else dicts.Insert(0, fresh);
    }
}

public sealed class DialogService : IDialogService
{
    private static Window? Owner => System.Windows.Application.Current?.Windows.OfType<Window>().FirstOrDefault(w => w.IsActive) ?? System.Windows.Application.Current?.MainWindow;

    public void Info(string message) => MessageBox.Show(Owner!, message, "Первая помощь сисадмина", MessageBoxButton.OK, MessageBoxImage.Information);
    public void Error(string message) => MessageBox.Show(Owner!, message, "Первая помощь сисадмина", MessageBoxButton.OK, MessageBoxImage.Warning);
    public bool Confirm(string title, string message) => MessageBox.Show(Owner!, message, title, MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes;

    public void ShowText(string title, string text) => new TextDialog(title, text) { Owner = Owner }.ShowDialog();

    public void ShowFindingDetails(Finding finding, KnowledgeEntry? entry) => new FindingDetailsDialog(finding, entry) { Owner = Owner }.ShowDialog();

    public string? AskService(IReadOnlyList<string> allowed)
    {
        var dlg = new ServiceDialog(allowed) { Owner = Owner };
        return dlg.ShowDialog() == true ? dlg.Selected : null;
    }

    public void OpenFile(string path)
    {
        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true })?.Dispose(); }
        catch (Exception ex) { Error(ex.Message); }
    }

    public void ShowInFolder(string path)
    {
        try { Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{path}\"") { UseShellExecute = true })?.Dispose(); }
        catch (Exception ex) { Error(ex.Message); }
    }
}

/// <summary>Explicit consent for every system-changing action (HIGH risk gets a separate warning) and post-fix feedback.</summary>
public sealed class WpfConfirmationService : IConfirmationService
{
    public Task<bool> ConfirmAsync(RemediationAction action, string? parameter)
        => OnUi(() =>
        {
            var w = System.Windows.Application.Current?.MainWindow;
            var dlg = new ConfirmDialog(action, parameter) { Owner = w };
            return dlg.ShowDialog() == true;
        });

    public Task<UserFeedback> AskFeedbackAsync(RemediationAction action, RemediationOutcome outcome)
        => OnUi(() =>
        {
            var dlg = new FeedbackDialog(action, outcome) { Owner = System.Windows.Application.Current?.MainWindow };
            dlg.ShowDialog();
            return dlg.Feedback;
        });

    private static Task<T> OnUi<T>(Func<T> f)
    {
        var d = System.Windows.Application.Current?.Dispatcher;
        if (d is null) return Task.FromResult(default(T)!);
        return d.CheckAccess() ? Task.FromResult(f()) : d.InvokeAsync(f).Task;
    }
}
