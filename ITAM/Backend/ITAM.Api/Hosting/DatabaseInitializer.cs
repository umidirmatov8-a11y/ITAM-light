using ITAM.Infrastructure.Persistence;

namespace ITAM.Api.Hosting;

/// <summary>Applies migrations and seeds reference data at start-up; keeps retrying in the background if PostgreSQL is not up yet.</summary>
public sealed class DatabaseInitializer : IHostedService
{
    private readonly IServiceScopeFactory _scopes;
    private readonly IConfiguration _config;
    private readonly ILogger<DatabaseInitializer> _log;
    private CancellationTokenSource? _retry;

    public static volatile bool Ready;
    public static string? LastError;

    public DatabaseInitializer(IServiceScopeFactory scopes, IConfiguration config, ILogger<DatabaseInitializer> log)
    {
        _scopes = scopes; _config = config; _log = log;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        if (!_config.GetValue("Itam:AutoMigrate", true)) { Ready = true; return; }
        for (var attempt = 1; attempt <= 6; attempt++)
        {
            if (await TryInitializeAsync(cancellationToken)) return;
            await Task.Delay(TimeSpan.FromSeconds(Math.Min(10, attempt * 2)), cancellationToken);
        }
        _log.LogError("Database is not reachable; the server starts anyway and keeps retrying every 30 seconds");
        _retry = new CancellationTokenSource();
        _ = Task.Run(async () =>
        {
            while (!_retry.IsCancellationRequested && !Ready)
            {
                try { await Task.Delay(TimeSpan.FromSeconds(30), _retry.Token); } catch (OperationCanceledException) { return; }
                await TryInitializeAsync(_retry.Token);
            }
        });
    }

    private async Task<bool> TryInitializeAsync(CancellationToken ct)
    {
        try
        {
            using var scope = _scopes.CreateScope();
            await scope.ServiceProvider.GetRequiredService<DataSeeder>().MigrateAndSeedAsync(ct);
            Ready = true;
            LastError = null;
            return true;
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            LastError = ex.Message;
            _log.LogWarning("Database initialization failed: {Error}", ex.Message);
            return false;
        }
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        _retry?.Cancel();
        return Task.CompletedTask;
    }
}
