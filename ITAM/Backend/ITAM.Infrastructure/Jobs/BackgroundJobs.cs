using ITAM.Application.Admin;
using ITAM.Application.Common;
using ITAM.Application.Notifications;
using ITAM.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ITAM.Infrastructure.Jobs;

/// <summary>Base for periodic jobs: each run gets its own DI scope with system privileges.</summary>
public abstract class PeriodicJob : BackgroundService
{
    private readonly IServiceScopeFactory _scopes;
    protected readonly ILogger Log;

    protected PeriodicJob(IServiceScopeFactory scopes, ILogger log) { _scopes = scopes; Log = log; }

    protected abstract TimeSpan InitialDelay { get; }
    protected abstract TimeSpan Interval { get; }
    protected abstract Task RunAsync(IServiceProvider sp, CancellationToken ct);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try { await Task.Delay(InitialDelay, stoppingToken); } catch (OperationCanceledException) { return; }
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = _scopes.CreateScope();
                scope.ServiceProvider.GetRequiredService<SystemContext>().Enabled = true;
                var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
                if (await db.Database.CanConnectAsync(stoppingToken) && await db.Users.IgnoreQueryFilters().AnyAsync(stoppingToken))
                    await RunAsync(scope.ServiceProvider, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex)
            {
                Log.LogError(ex, "Background job {Job} failed", GetType().Name);
            }
            try { await Task.Delay(Interval, stoppingToken); } catch (OperationCanceledException) { break; }
        }
    }
}

public sealed class NotificationJob : PeriodicJob
{
    public NotificationJob(IServiceScopeFactory scopes, ILogger<NotificationJob> log) : base(scopes, log) { }
    protected override TimeSpan InitialDelay => TimeSpan.FromSeconds(30);
    protected override TimeSpan Interval => TimeSpan.FromHours(1);

    protected override async Task RunAsync(IServiceProvider sp, CancellationToken ct)
    {
        var created = await sp.GetRequiredService<NotificationService>().GenerateAsync(ct);
        if (created > 0) Log.LogInformation("Notification rules created {Count} notifications", created);
    }
}

public sealed class BackupSchedulerJob : PeriodicJob
{
    public BackupSchedulerJob(IServiceScopeFactory scopes, ILogger<BackupSchedulerJob> log) : base(scopes, log) { }
    protected override TimeSpan InitialDelay => TimeSpan.FromMinutes(2);
    protected override TimeSpan Interval => TimeSpan.FromMinutes(5);

    protected override async Task RunAsync(IServiceProvider sp, CancellationToken ct)
    {
        if (await sp.GetRequiredService<BackupService>().RunScheduledIfDueAsync(sp.GetRequiredService<NotificationService>(), ct))
            Log.LogInformation("Scheduled backup executed");
    }
}

public sealed class MaintenanceJob : PeriodicJob
{
    public MaintenanceJob(IServiceScopeFactory scopes, ILogger<MaintenanceJob> log) : base(scopes, log) { }
    protected override TimeSpan InitialDelay => TimeSpan.FromMinutes(5);
    protected override TimeSpan Interval => TimeSpan.FromHours(12);

    protected override async Task RunAsync(IServiceProvider sp, CancellationToken ct)
    {
        var db = sp.GetRequiredService<AppDbContext>();
        var cutoff = DateTime.UtcNow.AddDays(-30);
        var removed = await db.UserSessions.Where(s => s.ExpiresAt < cutoff || (s.RevokedAt != null && s.RevokedAt < cutoff)).ExecuteDeleteAsync(ct);
        var readCutoff = DateTime.UtcNow.AddDays(-180);
        await db.Notifications.Where(n => n.IsResolved && n.ResolvedAt < readCutoff).ExecuteDeleteAsync(ct);
        if (removed > 0) Log.LogInformation("Removed {Count} expired sessions", removed);
    }
}
