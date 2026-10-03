using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Application.Cli;

/// <summary>Used by the CLI and tests: never confirms, so nothing is ever changed without a human decision in the UI.</summary>
public sealed class NonInteractiveConfirmationService : IConfirmationService
{
    public Task<bool> ConfirmAsync(RemediationAction action, string? parameter) => Task.FromResult(false);
    public Task<UserFeedback> AskFeedbackAsync(RemediationAction action, RemediationOutcome outcome) => Task.FromResult(UserFeedback.None);
}
