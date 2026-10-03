using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Abstractions;

public sealed class AnalysisResult
{
    public string Provider { get; init; } = "";
    public List<Finding> Findings { get; init; } = new();
    public ExecutiveSummary Summary { get; init; } = new();
    public string? Notes { get; init; }
}

/// <summary>Analyses a report. Default implementation is the local rule engine (100% offline).</summary>
public interface IAnalysisProvider
{
    string Name { get; }
    bool IsAvailable { get; }
    Task<AnalysisResult> AnalyzeAsync(DiagnosticReport report);
}

/// <summary>Asks the administrator for explicit consent before a system-changing action.</summary>
public interface IConfirmationService
{
    Task<bool> ConfirmAsync(RemediationAction action, string? parameter);
    Task<UserFeedback> AskFeedbackAsync(RemediationAction action, RemediationOutcome outcome);
}

/// <summary>
/// Runs an allow-listed operation with administrator rights through Windows UAC
/// (FirstAidAdmin.Helper.exe started with the "runas" verb). No UAC bypass of any kind.
/// </summary>
public interface IElevationService
{
    bool IsElevated { get; }
    bool IsHelperAvailable { get; }
    Task<OperationResult> RunElevatedAsync(string operationId, string? parameter, CancellationToken cancellationToken);
}

/// <summary>Executes allow-listed operations in the current process (used directly or by the helper).</summary>
public interface IOperationExecutor
{
    bool IsKnownOperation(string operationId);
    Task<OperationResult> ExecuteAsync(string operationId, string? parameter, CancellationToken cancellationToken);
}

/// <summary>Records every external command that was executed (exported as commands.log).</summary>
public interface ICommandLog
{
    void Record(CommandResult result);
    IReadOnlyList<CommandResult> Entries { get; }
    string Render(int maxOutputChars = 4000);
}

public interface ICaseStore
{
    SupportCase Create(string problem, ProblemScenario? scenario, string computer, string user);
    void Save(SupportCase supportCase);
    SupportCase? Load(string id);
    IReadOnlyList<SupportCase> List(int max = 50);
    string CaseFolder(string id);
}

public interface ISettingsStore
{
    Core.Settings.AppSettings Load();
    void Save(Core.Settings.AppSettings settings);
    string SettingsPath { get; }
}

/// <summary>
/// Abstraction for "where diagnostics run". Only the local target exists today.
/// A future authenticated Remote Diagnostic Agent can implement it without changing the core.
/// </summary>
public interface IDiagnosticTarget
{
    string DisplayName { get; }
    bool IsLocal { get; }
    Task<DiagnosticResult> RunModuleAsync(IDiagnosticModule module, DiagnosticContext context, CancellationToken cancellationToken);
}

public interface IReportGenerator
{
    string Format { get; }
    string FileExtension { get; }
    string Generate(DiagnosticReport report);
}

/// <summary>PDF export is planned. The interface exists so it can be added without touching callers.</summary>
public interface IPdfExporter
{
    bool IsSupported { get; }
    Task ExportAsync(DiagnosticReport report, string path, CancellationToken cancellationToken);
}
