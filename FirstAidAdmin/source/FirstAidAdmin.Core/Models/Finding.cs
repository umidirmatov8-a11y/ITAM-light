namespace FirstAidAdmin.Core.Models;

/// <summary>One argument for or against a probable cause ("✓ Gateway доступен", "✗ DNS-запросы не проходят").</summary>
public sealed record FindingBasis(string Text, bool Supports);

/// <summary>
/// A correlated conclusion produced by the correlation engine from several results.
/// It is a hypothesis with a confidence level, never a certainty.
/// </summary>
public sealed class Finding
{
    public string Id { get; set; } = "";
    public string Title { get; set; } = "";
    public DiagnosticCategory Category { get; set; }
    public Severity Severity { get; set; } = Severity.Medium;
    public Confidence Confidence { get; set; } = Confidence.Medium;
    /// <summary>What was observed (facts).</summary>
    public string WhatWasFound { get; set; } = "";
    /// <summary>Probable cause (hypothesis).</summary>
    public string ProbableCause { get; set; } = "";
    public string Recommendation { get; set; } = "";
    public List<FindingBasis> Basis { get; set; } = new();
    public List<string> RemediationIds { get; set; } = new();
    public List<string> RelatedCheckIds { get; set; } = new();
    public string? KnowledgeBaseId { get; set; }
    public bool MayRequireReboot { get; set; }
    /// <summary>Produced by a correlation rule (true) or a single failed check (false).</summary>
    public bool IsCorrelated { get; set; } = true;
    public string? RuleId { get; set; }

    public Finding Support(string text) { Basis.Add(new FindingBasis(text, true)); return this; }
    public Finding Against(string text) { Basis.Add(new FindingBasis(text, false)); return this; }
}
