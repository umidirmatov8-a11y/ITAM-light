using ITAM.Domain.Entities;

namespace ITAM.Application.Common;

/// <summary>Per-request audit settings shared between services and the SaveChanges audit hook.</summary>
public sealed class AuditContext
{
    private int _suppress;
    public bool SuppressAutomatic => _suppress > 0;
    public string CorrelationId { get; set; } = Guid.NewGuid().ToString("N")[..12];

    /// <summary>Business operations write one explicit, human-readable audit record instead of raw row diffs.</summary>
    public IDisposable Suppress()
    {
        _suppress++;
        return new Releaser(() => _suppress--);
    }

    private sealed class Releaser(Action release) : IDisposable
    {
        private bool _done;
        public void Dispose() { if (!_done) { _done = true; release(); } }
    }
}

public interface IAuditService
{
    /// <summary>Adds an audit record to the current unit of work (saved together with the business change).</summary>
    void Log(string action, string? entityType, Guid? entityId, string? entityName, object? oldValues = null, object? newValues = null, string? comment = null);
    /// <summary>Writes an audit record immediately (security events: login, failed login, logout).</summary>
    Task LogNowAsync(string action, string? entityType, Guid? entityId, string? entityName, object? oldValues = null, object? newValues = null, string? comment = null, bool success = true, string? userName = null, Guid? userId = null, CancellationToken ct = default);
}

public sealed class AuditService : IAuditService
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly AuditContext _ctx;
    private readonly ITenantContext _tenant;

    public AuditService(IAppDbContext db, ICurrentUser user, IClock clock, AuditContext ctx, ITenantContext tenant)
    {
        _db = db; _user = user; _clock = clock; _ctx = ctx; _tenant = tenant;
    }

    private AuditLog Build(string action, string? entityType, Guid? entityId, string? entityName, object? oldValues, object? newValues, string? comment, bool success, string? userName, Guid? userId)
        => new()
        {
            OrganizationId = _tenant.OrganizationId,
            Timestamp = _clock.UtcNow,
            UserId = userId ?? _user.UserId,
            UserName = userName ?? _user.UserName ?? "system",
            IpAddress = _user.IpAddress,
            UserAgent = _user.UserAgent is { Length: > 300 } ua ? ua[..300] : _user.UserAgent,
            Action = action,
            EntityType = entityType,
            EntityId = entityId,
            EntityName = entityName,
            OldValues = ToJson(oldValues),
            NewValues = ToJson(newValues),
            Comment = comment,
            CorrelationId = _ctx.CorrelationId,
            Success = success
        };

    private static string? ToJson(object? v) => v switch
    {
        null => null,
        string s => Json.Serialize(new { value = s }),
        _ => Json.Serialize(v)
    };

    public void Log(string action, string? entityType, Guid? entityId, string? entityName, object? oldValues = null, object? newValues = null, string? comment = null)
        => _db.AuditLogs.Add(Build(action, entityType, entityId, entityName, oldValues, newValues, comment, true, null, null));

    public async Task LogNowAsync(string action, string? entityType, Guid? entityId, string? entityName, object? oldValues = null, object? newValues = null, string? comment = null, bool success = true, string? userName = null, Guid? userId = null, CancellationToken ct = default)
    {
        _db.AuditLogs.Add(Build(action, entityType, entityId, entityName, oldValues, newValues, comment, success, userName, userId));
        await _db.SaveChangesAsync(ct);
    }
}
