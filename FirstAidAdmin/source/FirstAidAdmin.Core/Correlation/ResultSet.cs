using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Correlation;

/// <summary>Flattened, id-indexed view of all results of a run used by correlation rules.</summary>
public sealed class ResultSet
{
    private readonly Dictionary<string, DiagnosticResult> _byId = new(StringComparer.OrdinalIgnoreCase);

    public ResultSet(IEnumerable<DiagnosticResult> results)
    {
        Modules = results.ToList();
        foreach (var r in Modules.SelectMany(m => m.Flatten()))
            _byId[r.Id] = r; // last wins (re-tests replace earlier results)
    }

    public IReadOnlyList<DiagnosticResult> Modules { get; }
    public IEnumerable<DiagnosticResult> All => _byId.Values;

    public DiagnosticResult? Get(string id) => _byId.TryGetValue(id, out var r) ? r : null;
    public DiagnosticStatus? StatusOf(string id) => Get(id)?.Status;

    /// <summary>The check ran and produced a meaningful status (not skipped / missing).</summary>
    public bool Ran(string id) => Get(id) is { Status: not DiagnosticStatus.Skipped };
    public bool IsOk(string id) => StatusOf(id) == DiagnosticStatus.Ok;
    public bool Failed(string id) => StatusOf(id) is DiagnosticStatus.Error or DiagnosticStatus.Critical;
    public bool Warn(string id) => StatusOf(id) == DiagnosticStatus.Warning;
    public bool FailedOrWarn(string id) => Failed(id) || Warn(id);
    public bool AnyFailed(params string[] ids) => ids.Any(Failed);
    public bool AnyOk(params string[] ids) => ids.Any(IsOk);

    public string? Evidence(string id, string key) => Get(id)?.GetEvidence(key);

    public double? EvidenceNumber(string id, string key)
        => double.TryParse(Evidence(id, key), System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture, out var v) ? v : null;

    public string Summary(string id) => Get(id)?.Summary ?? "";
}
