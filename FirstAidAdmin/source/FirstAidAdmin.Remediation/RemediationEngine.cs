using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Engine;
using FirstAidAdmin.Core.Models;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.Remediation;

public sealed class RemediationRun
{
    public RemediationRecord Record { get; init; } = new();
    public List<DiagnosticResult> RetestResults { get; init; } = new();
}

/// <summary>
/// Finding → Recommendation → Remediation → Confirmation → UAC → Action → Re-test.
/// Never runs anything without explicit confirmation from the administrator.
/// </summary>
public sealed class RemediationEngine
{
    private readonly IOperationExecutor _executor;
    private readonly IElevationService _elevation;
    private readonly IConfirmationService _confirmation;
    private readonly DiagnosticRunner _runner;

    public RemediationEngine(IOperationExecutor executor, IElevationService elevation, IConfirmationService confirmation, DiagnosticRunner runner)
    {
        _executor = executor;
        _elevation = elevation;
        _confirmation = confirmation;
        _runner = runner;
    }

    /// <summary>Evaluates verification checks after a re-test.</summary>
    public static RemediationOutcome Evaluate(RemediationAction action, IEnumerable<DiagnosticResult> retest)
    {
        if (action.VerifyCheckIds.Count == 0) return RemediationOutcome.Unknown;
        var set = new ResultSet(retest);
        var relevant = action.VerifyCheckIds.Where(set.Ran).ToList();
        if (relevant.Count == 0) return RemediationOutcome.Unknown;
        return relevant.Any(set.FailedOrWarn) ? RemediationOutcome.Persists : RemediationOutcome.Resolved;
    }

    public async Task<RemediationRun> ExecuteAsync(string actionId, string? parameter, DiagnosticContext retestContext, CancellationToken cancellationToken)
    {
        var action = RemediationCatalog.Find(actionId) ?? throw new ArgumentException($"Unknown remediation '{actionId}'", nameof(actionId));
        var record = new RemediationRecord
        {
            ActionId = action.Id,
            Title = action.Title,
            Risk = action.Risk,
            Parameter = parameter,
            StartedAt = DateTimeOffset.Now
        };
        var run = new RemediationRun { Record = record };

        var paramError = OperationExecutor.ValidateParameter(action, parameter);
        if (paramError is not null)
        {
            record.Outcome = RemediationOutcome.Failed;
            record.Error = paramError;
            return run;
        }

        // Explicit consent. Opening a standard tool changes nothing, so it does not need a dialog.
        if (action.Kind != RemediationKind.OpenTool)
        {
            var confirmed = await _confirmation.ConfirmAsync(action, parameter).ConfigureAwait(false);
            record.Confirmed = confirmed;
            if (!confirmed)
            {
                record.Outcome = RemediationOutcome.Cancelled;
                retestContext.Logger.LogInformation("Remediation {Action} cancelled by user", action.Id);
                return run;
            }
        }
        else
        {
            record.Confirmed = true;
        }

        OperationResult result;
        if (action.RequiresAdmin && !_elevation.IsElevated)
        {
            record.Elevated = true;
            result = await _elevation.RunElevatedAsync(action.Id, parameter, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            result = await _executor.ExecuteAsync(action.Id, parameter, cancellationToken).ConfigureAwait(false);
        }
        record.Duration = result.Duration;
        record.Output = Truncate(result.Output, 8000);
        record.Error = result.Error;
        retestContext.Logger.LogInformation("Remediation {Action} executed: success={Success} exit={ExitCode}", action.Id, result.Success, result.ExitCode);

        if (!result.Success)
        {
            record.Outcome = RemediationOutcome.Failed;
            return run;
        }

        if (action.RetestModuleIds.Count > 0)
        {
            var retest = await _runner.RunAsync(action.RetestModuleIds, retestContext, cancellationToken).ConfigureAwait(false);
            run.RetestResults.AddRange(retest);
            record.Outcome = Evaluate(action, retest);
            var set = new ResultSet(retest);
            foreach (var id in action.VerifyCheckIds.Where(set.Ran))
                record.RetestSummary.Add($"{SeverityEngine.Icon(set.StatusOf(id)!.Value)} {set.Get(id)!.Name}: {set.Summary(id)}");
        }
        else
        {
            record.Outcome = RemediationOutcome.Unknown;
        }

        if (action.Kind != RemediationKind.OpenTool)
            record.Feedback = await _confirmation.AskFeedbackAsync(action, record.Outcome).ConfigureAwait(false);
        return run;
    }

    private static string Truncate(string s, int max) => s.Length <= max ? s : s[..max] + "…";
}
