using System.Collections.Concurrent;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace FirstAidAdmin.Core.Abstractions;

/// <summary>Every diagnostic module (built-in or plugin) implements this interface.</summary>
public interface IDiagnosticModule
{
    string Id { get; }
    string Name { get; }
    Task<DiagnosticResult> RunAsync(DiagnosticContext context, CancellationToken cancellationToken);
}

/// <summary>Optional metadata a module may expose.</summary>
public interface IDiagnosticModuleInfo
{
    DiagnosticCategory Category { get; }
    /// <summary>Takes minutes (SFC/DISM). Excluded from quick scenarios.</summary>
    bool IsLongRunning { get; }
    /// <summary>Input keys the module uses (e.g. "rdp.target").</summary>
    IReadOnlyList<string> InputKeys { get; }
}

/// <summary>Well-known input keys for scenarios that need user input.</summary>
public static class InputKeys
{
    public const string RdpTarget = "rdp.target";
    public const string RdpPort = "rdp.port";
    public const string AppName = "app.name";
    public const string AppExe = "app.exe";
    public const string AppAllowLaunch = "app.allowLaunch";
    public const string SharePath = "share.path";
    public const string ServiceName = "service.name";
    public const string PrinterHost = "printer.host";
}

public sealed class DiagnosticProgress
{
    public string ModuleId { get; init; } = "";
    public string ModuleName { get; init; } = "";
    public int Index { get; init; }
    public int Total { get; init; }
    public DiagnosticResult? Result { get; init; }
    public string Message { get; init; } = "";
}

/// <summary>Shared state and services for a diagnostic run.</summary>
public sealed class DiagnosticContext
{
    public AppSettings Settings { get; init; } = new();
    public SystemSnapshot System { get; init; } = new();
    public IReadOnlyDictionary<string, string> Inputs { get; init; } = new Dictionary<string, string>();
    public ILogger Logger { get; init; } = NullLogger.Instance;
    public IProgress<DiagnosticProgress>? Progress { get; init; }
    /// <summary>Results already produced in this run (modules may use them, e.g. DNS uses adapter DNS servers).</summary>
    public ConcurrentDictionary<string, DiagnosticResult> PreviousResults { get; } = new(StringComparer.OrdinalIgnoreCase);
    /// <summary>Arbitrary data shared between modules within the run.</summary>
    public ConcurrentDictionary<string, object> Shared { get; } = new(StringComparer.OrdinalIgnoreCase);

    public string? Input(string key) => Inputs.TryGetValue(key, out var v) && !string.IsNullOrWhiteSpace(v) ? v.Trim() : null;
    public TimeSpan CommandTimeout => TimeSpan.FromSeconds(Math.Max(5, Settings.Diagnostics.CommandTimeoutSeconds));
}
