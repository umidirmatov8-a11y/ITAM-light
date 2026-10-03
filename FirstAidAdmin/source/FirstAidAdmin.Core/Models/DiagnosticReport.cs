namespace FirstAidAdmin.Core.Models;

public sealed class SystemSnapshot
{
    public string MachineName { get; set; } = "";
    public string UserName { get; set; } = "";
    public string UserDomain { get; set; } = "";
    public string OsDescription { get; set; } = "";
    public string OsVersion { get; set; } = "";
    public string Architecture { get; set; } = "";
    public bool IsWindows { get; set; }
    public bool IsAdmin { get; set; }
    public bool IsDomainJoined { get; set; }
    public string? DomainName { get; set; }
    public string? LogonServer { get; set; }
    public TimeSpan Uptime { get; set; }
    public int ProcessorCount { get; set; }
    public bool NetworkAvailable { get; set; }
    public string? PrimaryIPv4 { get; set; }

    public string QualifiedUser => string.IsNullOrEmpty(UserDomain) ? UserName : $"{UserDomain}\\{UserName}";
}

public sealed class ExecutiveSummary
{
    public int OkCount { get; set; }
    public int WarningCount { get; set; }
    public int ProblemCount { get; set; }
    public int InfoCount { get; set; }
    public int SkippedCount { get; set; }
    public DiagnosticStatus OverallStatus { get; set; }
    public List<string> CriticalFindings { get; set; } = new();
    public List<string> Recommendations { get; set; } = new();
}

/// <summary>Everything a report needs. Produced by the session and consumed by report generators.</summary>
public sealed class DiagnosticReport
{
    public string Title { get; set; } = "Отчёт диагностики";
    public string AppVersion { get; set; } = "";
    public DateTimeOffset GeneratedAt { get; set; } = DateTimeOffset.Now;
    public ProblemScenario? Scenario { get; set; }
    public SystemSnapshot System { get; set; } = new();
    public SupportCase? Case { get; set; }
    public List<DiagnosticResult> Results { get; set; } = new();
    public List<Finding> Findings { get; set; } = new();
    public List<RemediationRecord> RemediationHistory { get; set; } = new();
    public List<TimelineEntry> Timeline { get; set; } = new();
    public ExecutiveSummary Summary { get; set; } = new();
    public string AnalysisProvider { get; set; } = "LocalRuleEngine";
}
