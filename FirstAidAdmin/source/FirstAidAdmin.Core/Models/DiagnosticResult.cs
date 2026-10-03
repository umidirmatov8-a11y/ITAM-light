using System.Text.Json.Serialization;

namespace FirstAidAdmin.Core.Models;

/// <summary>A single fact collected during diagnostics (the "why" behind a status).</summary>
public sealed record EvidenceItem(string Key, string Value, string? Note = null);

/// <summary>
/// Unified structured result. A module returns one result whose <see cref="Checks"/>
/// contain the individual checks (e.g. "network.gateway.ping").
/// </summary>
public sealed class DiagnosticResult
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public DiagnosticCategory Category { get; set; }
    public DiagnosticStatus Status { get; set; } = DiagnosticStatus.Info;
    public Severity Severity { get; set; } = Severity.Low;
    public string Summary { get; set; } = "";
    public string? Details { get; set; }
    public List<EvidenceItem> Evidence { get; set; } = new();
    public string? Recommendation { get; set; }
    /// <summary>Ids of remediation actions from the remediation catalog that may help.</summary>
    public List<string> Remediation { get; set; } = new();
    public TimeSpan Duration { get; set; }
    public bool RequiresAdmin { get; set; }
    public DateTimeOffset Timestamp { get; set; } = DateTimeOffset.Now;
    public List<DiagnosticResult> Checks { get; set; } = new();

    [JsonIgnore]
    public bool IsProblem => Status is DiagnosticStatus.Error or DiagnosticStatus.Critical;

    [JsonIgnore]
    public bool IsWarning => Status == DiagnosticStatus.Warning;

    public static DiagnosticResult Create(string id, string name, DiagnosticCategory category,
        DiagnosticStatus status, string summary, Severity? severity = null)
        => new()
        {
            Id = id,
            Name = name,
            Category = category,
            Status = status,
            Summary = summary,
            Severity = severity ?? SeverityFor(status)
        };

    public static Severity SeverityFor(DiagnosticStatus status) => status switch
    {
        DiagnosticStatus.Critical => Severity.Critical,
        DiagnosticStatus.Error => Severity.High,
        DiagnosticStatus.Warning => Severity.Medium,
        _ => Severity.Low
    };

    public DiagnosticResult WithEvidence(string key, object? value, string? note = null)
    {
        Evidence.Add(new EvidenceItem(key, value?.ToString() ?? "", note));
        return this;
    }

    public DiagnosticResult WithRecommendation(string recommendation, params string[] remediationIds)
    {
        if (!string.IsNullOrWhiteSpace(recommendation)) Recommendation = recommendation;
        foreach (var id in remediationIds)
            if (!Remediation.Contains(id)) Remediation.Add(id);
        return this;
    }

    public DiagnosticResult WithDetails(string? details)
    {
        Details = details;
        return this;
    }

    public string? GetEvidence(string key)
        => Evidence.LastOrDefault(e => string.Equals(e.Key, key, StringComparison.OrdinalIgnoreCase))?.Value;

    /// <summary>All checks including this one, depth first.</summary>
    public IEnumerable<DiagnosticResult> Flatten()
    {
        yield return this;
        foreach (var c in Checks)
            foreach (var f in c.Flatten())
                yield return f;
    }
}
