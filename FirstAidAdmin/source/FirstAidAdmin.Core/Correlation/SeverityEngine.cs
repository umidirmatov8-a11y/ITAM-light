using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Correlation;

/// <summary>Normalises statuses/severities and computes aggregate status and the executive summary.</summary>
public static class SeverityEngine
{
    public static int Rank(DiagnosticStatus s) => s switch
    {
        DiagnosticStatus.Critical => 5,
        DiagnosticStatus.Error => 4,
        DiagnosticStatus.Warning => 3,
        DiagnosticStatus.Ok => 2,
        DiagnosticStatus.Info => 1,
        _ => 0
    };

    public static DiagnosticStatus Worst(IEnumerable<DiagnosticStatus> statuses)
    {
        var list = statuses.ToList();
        if (list.Count == 0) return DiagnosticStatus.Info;
        return list.OrderByDescending(Rank).First();
    }

    /// <summary>Sets a module's status to the worst of its checks (when it has checks) and fixes severities.</summary>
    public static void Normalize(DiagnosticResult result)
    {
        foreach (var c in result.Checks) Normalize(c);
        if (result.Checks.Count > 0)
        {
            var worst = Worst(result.Checks.Select(c => c.Status));
            // A module whose own status is worse (e.g. module crashed) keeps it.
            if (Rank(worst) > Rank(result.Status) || result.Status == DiagnosticStatus.Info)
                result.Status = worst;
        }
        var expected = DiagnosticResult.SeverityFor(result.Status);
        if (result.Severity < expected) result.Severity = expected;
        if (result.Status is DiagnosticStatus.Ok or DiagnosticStatus.Info or DiagnosticStatus.Skipped)
            result.Severity = Severity.Low;
    }

    /// <summary>Leaf checks only (modules with checks are containers).</summary>
    public static IEnumerable<DiagnosticResult> Leaves(IEnumerable<DiagnosticResult> results)
    {
        foreach (var r in results)
        {
            if (r.Checks.Count == 0) { yield return r; continue; }
            foreach (var l in Leaves(r.Checks)) yield return l;
        }
    }

    public static ExecutiveSummary Summarize(IEnumerable<DiagnosticResult> results, IEnumerable<Finding> findings)
    {
        var leaves = Leaves(results)
            // event groups are children of event checks; count the parent check only
            .Where(l => !l.Id.StartsWith("events.group.", StringComparison.OrdinalIgnoreCase))
            .ToList();
        var parentsOfGroups = results.SelectMany(r => r.Flatten())
            .Where(r => r.Checks.Count > 0 && r.Checks.All(c => c.Id.StartsWith("events.group.", StringComparison.OrdinalIgnoreCase)))
            .ToList();
        leaves.AddRange(parentsOfGroups);

        var summary = new ExecutiveSummary
        {
            OkCount = leaves.Count(l => l.Status == DiagnosticStatus.Ok),
            WarningCount = leaves.Count(l => l.Status == DiagnosticStatus.Warning),
            ProblemCount = leaves.Count(l => l.Status is DiagnosticStatus.Error or DiagnosticStatus.Critical),
            InfoCount = leaves.Count(l => l.Status == DiagnosticStatus.Info),
            SkippedCount = leaves.Count(l => l.Status == DiagnosticStatus.Skipped),
            OverallStatus = Worst(leaves.Select(l => l.Status))
        };

        var ordered = findings.OrderByDescending(f => f.Severity).ThenByDescending(f => f.Confidence).ToList();
        foreach (var f in ordered.Where(f => f.Severity >= Severity.High))
            summary.CriticalFindings.Add(f.Title);
        foreach (var f in ordered.Where(f => !string.IsNullOrWhiteSpace(f.Recommendation)))
            if (!summary.Recommendations.Contains(f.Recommendation))
                summary.Recommendations.Add(f.Recommendation);
        return summary;
    }

    public static string Icon(DiagnosticStatus s) => s switch
    {
        DiagnosticStatus.Ok => "🟢",
        DiagnosticStatus.Warning => "🟡",
        DiagnosticStatus.Error => "🔴",
        DiagnosticStatus.Critical => "⛔",
        DiagnosticStatus.Skipped => "⚪",
        _ => "🔵"
    };

    public static string Icon(Severity s) => s switch
    {
        Severity.Critical => "⛔",
        Severity.High => "🔴",
        Severity.Medium => "🟡",
        _ => "🔵"
    };

    public static string Russian(Confidence c) => c switch
    {
        Confidence.High => "высокая",
        Confidence.Medium => "средняя",
        _ => "низкая"
    };

    public static string Russian(DiagnosticStatus s) => s switch
    {
        DiagnosticStatus.Ok => "Норма",
        DiagnosticStatus.Warning => "Предупреждение",
        DiagnosticStatus.Error => "Ошибка",
        DiagnosticStatus.Critical => "Критично",
        DiagnosticStatus.Skipped => "Пропущено",
        _ => "Информация"
    };

    public static string Russian(RiskLevel r) => r switch
    {
        RiskLevel.High => "ВЫСОКИЙ",
        RiskLevel.Medium => "СРЕДНИЙ",
        _ => "НИЗКИЙ"
    };
}
