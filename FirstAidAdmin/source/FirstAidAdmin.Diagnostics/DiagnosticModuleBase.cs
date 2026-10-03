using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Diagnostics;

/// <summary>Common plumbing for built-in modules: creates the root result and its child checks.</summary>
public abstract class DiagnosticModuleBase : IDiagnosticModule, IDiagnosticModuleInfo
{
    public abstract string Id { get; }
    public abstract string Name { get; }
    public abstract DiagnosticCategory Category { get; }
    public virtual bool IsLongRunning => false;
    public virtual IReadOnlyList<string> InputKeys => Array.Empty<string>();

    public async Task<DiagnosticResult> RunAsync(DiagnosticContext context, CancellationToken cancellationToken)
    {
        var root = DiagnosticResult.Create(Id, Name, Category, DiagnosticStatus.Info, "");
        await ExecuteAsync(root, context, cancellationToken).ConfigureAwait(false);
        if (string.IsNullOrEmpty(root.Summary)) root.Summary = DefaultSummary(root);
        return root;
    }

    protected abstract Task ExecuteAsync(DiagnosticResult root, DiagnosticContext context, CancellationToken cancellationToken);

    protected DiagnosticResult Check(DiagnosticResult root, string id, string name, DiagnosticStatus status, string summary, Severity? severity = null)
    {
        var c = DiagnosticResult.Create(id, name, Category, status, summary, severity);
        root.Checks.Add(c);
        return c;
    }

    protected DiagnosticResult Skipped(DiagnosticResult root, string id, string name, string reason, bool requiresAdmin = false)
    {
        var c = Check(root, id, name, DiagnosticStatus.Skipped, reason);
        c.RequiresAdmin = requiresAdmin;
        return c;
    }

    public static string DefaultSummary(DiagnosticResult root)
    {
        if (root.Checks.Count == 0) return root.Status == DiagnosticStatus.Skipped ? "Пропущено" : "Нет данных";
        var problems = root.Checks.Count(c => c.IsProblem);
        var warnings = root.Checks.Count(c => c.IsWarning);
        var ok = root.Checks.Count(c => c.Status == DiagnosticStatus.Ok);
        if (problems == 0 && warnings == 0) return $"Проблем не обнаружено (проверок в норме: {ok})";
        return $"Проблем: {problems}, предупреждений: {warnings}, в норме: {ok}";
    }

    protected static string Gb(long bytes) => $"{bytes / 1024d / 1024 / 1024:F1} ГБ";
    protected static string Mb(long bytes) => $"{bytes / 1024d / 1024:F0} МБ";
}
