using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;

namespace FirstAidAdmin.Core.Analysis;

/// <summary>Default analysis provider: the local rule-based correlation engine. Works fully offline.</summary>
public sealed class LocalRuleEngine : IAnalysisProvider
{
    private readonly CorrelationEngine _engine;
    public LocalRuleEngine(CorrelationEngine engine) => _engine = engine;

    public string Name => "LocalRuleEngine";
    public bool IsAvailable => true;

    public Task<AnalysisResult> AnalyzeAsync(DiagnosticReport report)
    {
        var findings = _engine.Analyze(report.Results);
        var summary = SeverityEngine.Summarize(report.Results, findings);
        return Task.FromResult(new AnalysisResult { Provider = Name, Findings = findings, Summary = summary });
    }
}

/// <summary>
/// Placeholder for a future optional AI assistant. It is disabled by default, performs no network calls,
/// and the application never depends on it. When disabled it returns an empty result.
/// </summary>
public sealed class OptionalAIProvider : IAnalysisProvider
{
    private readonly AppSettings _settings;
    public OptionalAIProvider(AppSettings settings) => _settings = settings;

    public string Name => "OptionalAIProvider";
    public bool IsAvailable => false; // not implemented in v2.0 by design (offline first)

    public Task<AnalysisResult> AnalyzeAsync(DiagnosticReport report)
        => Task.FromResult(new AnalysisResult
        {
            Provider = Name,
            Notes = _settings.Ai.Enabled
                ? "AI-ассистент запланирован в следующей версии; анализ выполнен локальными правилами."
                : "AI-ассистент отключён (по умолчанию)."
        });
}
