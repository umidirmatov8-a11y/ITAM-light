using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Correlation;

public interface ICorrelationRule
{
    string Id { get; }
    /// <summary>Returns zero or more findings. Must not throw for missing checks.</summary>
    IEnumerable<Finding> Evaluate(ResultSet set);
}

/// <summary>Rule defined by a delegate - keeps the rule catalog compact and readable.</summary>
public sealed class DelegateRule : ICorrelationRule
{
    private readonly Func<ResultSet, Finding?> _evaluate;
    public DelegateRule(string id, Func<ResultSet, Finding?> evaluate) { Id = id; _evaluate = evaluate; }
    public string Id { get; }
    public IEnumerable<Finding> Evaluate(ResultSet set)
    {
        var f = _evaluate(set);
        if (f is null) yield break;
        f.Id = string.IsNullOrEmpty(f.Id) ? Id : f.Id;
        f.RuleId = Id;
        yield return f;
    }
}

/// <summary>
/// Diagnostic Correlation Engine: looks at all results together and produces findings
/// (probable causes with confidence). Rule based, fully offline.
/// </summary>
public sealed class CorrelationEngine
{
    private readonly IReadOnlyList<ICorrelationRule> _rules;

    public CorrelationEngine() : this(CorrelationRules.All()) { }
    public CorrelationEngine(IEnumerable<ICorrelationRule> rules) => _rules = rules.ToList();

    public IReadOnlyList<ICorrelationRule> Rules => _rules;

    public List<Finding> Analyze(IEnumerable<DiagnosticResult> results)
    {
        var list = results.ToList();
        foreach (var r in list) SeverityEngine.Normalize(r);
        var set = new ResultSet(list);
        var findings = new List<Finding>();

        foreach (var rule in _rules)
        {
            try
            {
                foreach (var f in rule.Evaluate(set))
                    if (findings.All(x => x.Id != f.Id)) findings.Add(f);
            }
            catch
            {
                // A faulty rule must never break the analysis.
            }
        }

        // Checks explained by any rule (including superseded ones) do not need a separate finding.
        var covered = new HashSet<string>(findings.SelectMany(f => f.RelatedCheckIds), StringComparer.OrdinalIgnoreCase);
        covered.UnionWith(CorrelationRules.ExplainedChecks(set));

        // Suppress findings explicitly superseded by a more specific (root-cause) one.
        var superseded = new HashSet<string>(findings.SelectMany(f => CorrelationRules.Supersedes(f.Id)));
        findings.RemoveAll(f => superseded.Contains(f.Id));

        // Any failed check not explained by a correlated finding becomes a simple finding.
        foreach (var check in set.All.Where(c => c.IsProblem && (c.Checks.Count == 0 || c.Checks.All(x => x.Id.StartsWith("events.group.", StringComparison.OrdinalIgnoreCase))) && !covered.Contains(c.Id)
                                                  && !c.Id.StartsWith("events.group.", StringComparison.OrdinalIgnoreCase)))
        {
            findings.Add(new Finding
            {
                Id = "check:" + check.Id,
                Title = check.Name,
                Category = check.Category,
                Severity = check.Severity,
                Confidence = Confidence.Medium,
                WhatWasFound = check.Summary,
                ProbableCause = check.Details ?? "Проверка завершилась с ошибкой.",
                Recommendation = check.Recommendation ?? "Изучите подробности проверки.",
                RemediationIds = check.Remediation.ToList(),
                RelatedCheckIds = { check.Id },
                IsCorrelated = false
            }.Support(check.Summary));
        }

        return findings
            .OrderByDescending(f => f.Severity)
            .ThenByDescending(f => f.IsCorrelated)
            .ThenByDescending(f => f.Confidence)
            .ToList();
    }
}
