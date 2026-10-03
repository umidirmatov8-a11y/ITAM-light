namespace FirstAidAdmin.Core.Models;

public enum RemediationKind
{
    /// <summary>Runs an operation (possibly through the elevated helper).</summary>
    Operation,
    /// <summary>Only opens a standard Windows tool for the administrator.</summary>
    OpenTool
}

/// <summary>Description of a fix the administrator may choose to run. Never runs automatically.</summary>
public sealed class RemediationAction
{
    public string Id { get; init; } = "";
    public string Title { get; init; } = "";
    public string Description { get; init; } = "";
    /// <summary>What will change on the system after running the action.</summary>
    public string WhatChanges { get; init; } = "";
    public RiskLevel Risk { get; init; }
    public bool RequiresAdmin { get; init; }
    public bool RequiresReboot { get; init; }
    public bool Reversible { get; init; }
    public RemediationKind Kind { get; init; } = RemediationKind.Operation;
    /// <summary>Human-readable equivalent command (shown to the admin and logged).</summary>
    public string CommandPreview { get; init; } = "";
    /// <summary>Modules to re-run after execution to verify the fix.</summary>
    public IReadOnlyList<string> RetestModuleIds { get; init; } = Array.Empty<string>();
    /// <summary>Check ids whose status decides whether the problem was resolved.</summary>
    public IReadOnlyList<string> VerifyCheckIds { get; init; } = Array.Empty<string>();
    /// <summary>Long-running operations (SFC, DISM) are shown with a warning.</summary>
    public bool IsLongRunning { get; init; }
    /// <summary>Optional parameter name (e.g. "service") the operation accepts.</summary>
    public string? Parameter { get; init; }
}

public sealed class OperationResult
{
    public bool Success { get; set; }
    public int ExitCode { get; set; }
    public string Output { get; set; } = "";
    public string? Error { get; set; }
    public TimeSpan Duration { get; set; }

    public static OperationResult Ok(string output, int exitCode = 0) => new() { Success = true, Output = output, ExitCode = exitCode };
    public static OperationResult Fail(string error, string output = "", int exitCode = -1) => new() { Success = false, Error = error, Output = output, ExitCode = exitCode };
}

public sealed class RemediationRecord
{
    public string ActionId { get; set; } = "";
    public string Title { get; set; } = "";
    public RiskLevel Risk { get; set; }
    public DateTimeOffset StartedAt { get; set; }
    public TimeSpan Duration { get; set; }
    public bool Confirmed { get; set; }
    public bool Elevated { get; set; }
    public RemediationOutcome Outcome { get; set; }
    public string Output { get; set; } = "";
    public string? Error { get; set; }
    public string? Parameter { get; set; }
    public UserFeedback Feedback { get; set; }
    public List<string> RetestSummary { get; set; } = new();
}
