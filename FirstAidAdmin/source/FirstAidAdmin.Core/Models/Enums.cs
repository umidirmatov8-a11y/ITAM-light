namespace FirstAidAdmin.Core.Models;

/// <summary>Result status of a single diagnostic check.</summary>
public enum DiagnosticStatus
{
    Ok,
    Warning,
    Error,
    Critical,
    Info,
    Skipped
}

/// <summary>How serious a result or finding is.</summary>
public enum Severity
{
    Low,
    Medium,
    High,
    Critical
}

/// <summary>How sure the correlation engine is about a probable cause. Never "certain".</summary>
public enum Confidence
{
    Low,
    Medium,
    High
}

/// <summary>Risk level of an action that changes the system.</summary>
public enum RiskLevel
{
    Low,
    Medium,
    High
}

public enum DiagnosticCategory
{
    System,
    Network,
    Dns,
    WiFi,
    Domain,
    ActiveDirectory,
    Rdp,
    Printer,
    WindowsUpdate,
    Storage,
    WindowsHealth,
    Security,
    Performance,
    EventLog,
    Services,
    Application,
    NetworkShare
}

/// <summary>Problems a help-desk user can report. Each maps to a set of diagnostic modules.</summary>
public enum ProblemScenario
{
    NoInternet,
    SlowComputer,
    CannotLogin,
    Rdp,
    Printer,
    WindowsUpdate,
    Disk,
    WindowsErrors,
    WiFi,
    Dns,
    Domain,
    ApplicationNotWorking,
    NetworkShare,
    ServiceNotWorking,
    SlowBoot,
    Security,
    FirstResponse,
    FullDiagnostics
}

public enum RemediationOutcome
{
    NotExecuted,
    Cancelled,
    Failed,
    Resolved,
    Persists,
    Unknown
}

public enum UserFeedback
{
    None,
    Yes,
    No,
    DontKnow
}
