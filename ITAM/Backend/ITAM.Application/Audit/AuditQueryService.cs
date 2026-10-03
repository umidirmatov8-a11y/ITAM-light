using System.Text.Json;
using ITAM.Application.Common;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Audit;

public sealed class AuditQuery : PagedRequest
{
    public Guid? UserId { get; set; }
    public string? Action { get; set; }
    public string? EntityType { get; set; }
    public Guid? EntityId { get; set; }
    public DateTime? From { get; set; }
    public DateTime? To { get; set; }
    public bool? Success { get; set; }
    public string? IpAddress { get; set; }
}

public sealed record AuditLogDto(long Id, DateTime Timestamp, Guid? UserId, string? UserName, string? IpAddress, string? UserAgent, string Action,
    string? EntityType, Guid? EntityId, string? EntityName, JsonElement? OldValues, JsonElement? NewValues, string? Comment, string? CorrelationId, bool Success);

/// <summary>Read-only access to the audit trail. There is intentionally no update/delete API.</summary>
public sealed class AuditQueryService
{
    private readonly IAppDbContext _db;

    public AuditQueryService(IAppDbContext db) => _db = db;

    public IQueryable<ITAM.Domain.Entities.AuditLog> Filtered(AuditQuery q)
    {
        var query = _db.AuditLogs.AsNoTracking().AsQueryable();
        if (q.UserId is not null) query = query.Where(a => a.UserId == q.UserId);
        if (!string.IsNullOrWhiteSpace(q.Action)) query = query.Where(a => a.Action.StartsWith(q.Action));
        if (!string.IsNullOrWhiteSpace(q.EntityType)) query = query.Where(a => a.EntityType == q.EntityType);
        if (q.EntityId is not null) query = query.Where(a => a.EntityId == q.EntityId);
        if (q.From is not null) query = query.Where(a => a.Timestamp >= q.From.Value.ToUniversalTime());
        if (q.To is not null) query = query.Where(a => a.Timestamp <= q.To.Value.ToUniversalTime());
        if (q.Success is not null) query = query.Where(a => a.Success == q.Success);
        if (!string.IsNullOrWhiteSpace(q.IpAddress)) query = query.Where(a => a.IpAddress == q.IpAddress);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(a => (a.EntityName != null && EF.Functions.ILike(a.EntityName, like)) || (a.UserName != null && EF.Functions.ILike(a.UserName, like))
                                     || EF.Functions.ILike(a.Action, like) || (a.Comment != null && EF.Functions.ILike(a.Comment, like)));
        }
        return query;
    }

    public async Task<PagedResult<AuditLogDto>> ListAsync(AuditQuery q, CancellationToken ct)
    {
        var query = Filtered(q);
        query = q.Sort == "timestamp" && !q.Desc ? query.OrderBy(a => a.Id) : query.OrderByDescending(a => a.Id);
        var total = await query.CountAsync(ct);
        var rows = await query.Skip((q.SafePage - 1) * q.SafePageSize).Take(q.SafePageSize).ToListAsync(ct);
        return new PagedResult<AuditLogDto>(rows.Select(ToDto).ToList(), total, q.SafePage, q.SafePageSize);
    }

    public static AuditLogDto ToDto(ITAM.Domain.Entities.AuditLog a) => new(a.Id, a.Timestamp, a.UserId, a.UserName, a.IpAddress, a.UserAgent, a.Action,
        a.EntityType, a.EntityId, a.EntityName, Json.ToElement(a.OldValues), Json.ToElement(a.NewValues), a.Comment, a.CorrelationId, a.Success);

    public async Task<IReadOnlyList<string>> ActionsAsync(CancellationToken ct)
        => await _db.AuditLogs.AsNoTracking().Select(a => a.Action).Distinct().OrderBy(a => a).Take(500).ToListAsync(ct);

    public async Task<IReadOnlyList<AuditLogDto>> ForEntityAsync(string entityType, Guid entityId, CancellationToken ct)
        => (await _db.AuditLogs.AsNoTracking().Where(a => a.EntityId == entityId && (a.EntityType == entityType || entityType == "*"))
            .OrderByDescending(a => a.Id).Take(500).ToListAsync(ct)).Select(ToDto).ToList();
}
