namespace FirstAidAdmin.Core.Models;

public sealed record TimelineEntry(DateTimeOffset Timestamp, string Kind, string Message);

/// <summary>A support case: everything (checks, actions, exports) is attached to it.</summary>
public sealed class SupportCase
{
    /// <summary>Format: yyyyMMdd-NNNN (displayed as "CASE #20261003-0012").</summary>
    public string Id { get; set; } = "";
    public string Computer { get; set; } = "";
    public string User { get; set; } = "";
    public string Problem { get; set; } = "";
    public ProblemScenario? Scenario { get; set; }
    public string? Notes { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.Now;
    public DateTimeOffset? ClosedAt { get; set; }
    public List<TimelineEntry> Timeline { get; set; } = new();
    public List<DiagnosticResult> Results { get; set; } = new();
    public List<Finding> Findings { get; set; } = new();
    public List<RemediationRecord> RemediationHistory { get; set; } = new();

    public string DisplayId => $"CASE #{Id}";
    public string FileStem => $"Case-{Id}";
}
