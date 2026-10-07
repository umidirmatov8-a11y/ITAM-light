using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Access;

public sealed class AccessQuery : PagedRequest
{
    public Guid? EmployeeId { get; set; }
    public Guid? AccessSystemId { get; set; }
    public AccessStatus? Status { get; set; }
    public Guid? RegionId { get; set; }
    public bool? ReviewOverdue { get; set; }
    /// <summary>Accesses of terminated employees that are still active (security finding).</summary>
    public bool? OrphanedOnly { get; set; }
}

public sealed class AccessInput
{
    [Required] public Guid EmployeeId { get; set; }
    [Required] public Guid AccessSystemId { get; set; }
    public Guid? AccessLevelId { get; set; }
    [MaxLength(256)] public string? Username { get; set; }
    [MaxLength(256)] public string? Role { get; set; }
    public DateTime? GrantedAt { get; set; }
    public AccessStatus Status { get; set; } = AccessStatus.Active;
    public Guid? ResponsibleEmployeeId { get; set; }
    [MaxLength(128)] public string? RequestReference { get; set; }
    public DateOnly? ReviewDueDate { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public Dictionary<string, JsonElement>? CustomFields { get; set; }
}

public sealed class AccessRevokeRequest
{
    public DateTime? RevokedAt { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
}

public sealed class AccessReviewRequest
{
    public DateOnly? NextReviewDate { get; set; }
    [MaxLength(1000)] public string? Comment { get; set; }
}

public sealed record AccessDto(Guid Id, Guid EmployeeId, string EmployeeName, string? EmployeeNumber, string? DepartmentName, string? RegionName,
    Guid AccessSystemId, string SystemName, Guid? AccessLevelId, string? LevelName, string? Username, string? Role,
    DateTime GrantedAt, DateTime? RevokedAt, DateTime RecordedAt, AccessStatus Status, Guid? ResponsibleEmployeeId, string? ResponsibleName,
    string? RequestReference, DateOnly? ReviewDueDate, DateTime? LastReviewedAt, string? Comment, string? RevokeReason, JsonElement? CustomFields,
    bool EmployeeTerminated);

public sealed class AccessService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly ICustomFieldValidator _customFields;

    public AccessService(IAppDbContext db, IRegionScope scope, IClock clock, IAuditService audit, AuditContext auditCtx, ICustomFieldValidator customFields)
    {
        _db = db; _scope = scope; _clock = clock; _audit = audit; _auditCtx = auditCtx; _customFields = customFields;
    }

    private IQueryable<EmployeeAccess> Visible() => _scope.Apply(_db.EmployeeAccesses.AsQueryable(), a => a.Employee!.RegionId);

    private static readonly System.Linq.Expressions.Expression<Func<EmployeeAccess, AccessDto>> Projection = a => new AccessDto(a.Id, a.EmployeeId,
        a.Employee!.FullName, a.Employee.EmployeeNumber, a.Employee.Department != null ? a.Employee.Department.Name : null,
        a.Employee.Region != null ? a.Employee.Region.Name : null, a.AccessSystemId, a.AccessSystem!.Name, a.AccessLevelId,
        a.AccessLevel != null ? a.AccessLevel.Name : null, a.Username, a.Role, a.GrantedAt, a.RevokedAt, a.RecordedAt, a.Status,
        a.ResponsibleEmployeeId, null, a.RequestReference, a.ReviewDueDate, a.LastReviewedAt, a.Comment, a.RevokeReason, null,
        a.Employee.Status != null && (a.Employee.Status.Kind == EmployeeStatusKind.Terminated || a.Employee.Status.Kind == EmployeeStatusKind.Archived));

    public IQueryable<EmployeeAccess> Filtered(AccessQuery q)
    {
        var query = Visible().AsNoTracking();
        if (q.EmployeeId is not null) query = query.Where(a => a.EmployeeId == q.EmployeeId);
        if (q.AccessSystemId is not null) query = query.Where(a => a.AccessSystemId == q.AccessSystemId);
        if (q.Status is not null) query = query.Where(a => a.Status == q.Status);
        if (q.RegionId is not null) query = query.Where(a => a.Employee!.RegionId == q.RegionId);
        if (q.ReviewOverdue == true)
        {
            var today = DateOnly.FromDateTime(_clock.UtcNow);
            query = query.Where(a => a.Status == AccessStatus.Active && a.ReviewDueDate < today);
        }
        if (q.OrphanedOnly == true)
            query = query.Where(a => a.Status != AccessStatus.Revoked && (a.Employee!.Status!.Kind == EmployeeStatusKind.Terminated || a.Employee.Status.Kind == EmployeeStatusKind.Archived));
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(a => EF.Functions.ILike(a.Employee!.FullName, like) || (a.Username != null && EF.Functions.ILike(a.Username, like))
                                     || EF.Functions.ILike(a.AccessSystem!.Name, like) || (a.RequestReference != null && EF.Functions.ILike(a.RequestReference, like)));
        }
        return query;
    }

    public async Task<PagedResult<AccessDto>> ListAsync(AccessQuery q, CancellationToken ct)
    {
        var sorts = new Dictionary<string, System.Linq.Expressions.Expression<Func<EmployeeAccess, object?>>>
        {
            ["grantedAt"] = a => a.GrantedAt, ["employeeName"] = a => a.Employee!.FullName, ["systemName"] = a => a.AccessSystem!.Name,
            ["status"] = a => a.Status, ["reviewDueDate"] = a => a.ReviewDueDate,
        };
        if (q.Sort is null) { q.Sort = "grantedAt"; q.Order = "desc"; }
        return await Filtered(q).SortBy(q, sorts, "grantedAt").ToPagedAsync(q, Projection, ct);
    }

    public async Task<AccessDto> GetAsync(Guid id, CancellationToken ct)
    {
        var dto = await Visible().AsNoTracking().Where(a => a.Id == id).Select(Projection).FirstOrDefaultAsync(ct) ?? throw new NotFoundException("Доступ", id);
        var cf = await _db.EmployeeAccesses.Where(a => a.Id == id).Select(a => a.CustomFields).FirstOrDefaultAsync(ct);
        var responsible = dto.ResponsibleEmployeeId is null ? null : await _db.Employees.Where(e => e.Id == dto.ResponsibleEmployeeId).Select(e => e.FullName).FirstOrDefaultAsync(ct);
        return dto with { CustomFields = Json.ToElement(cf), ResponsibleName = responsible };
    }

    public async Task<AccessDto> SaveAsync(Guid? id, AccessInput input, CancellationToken ct)
    {
        var employee = await _scope.Apply(_db.Employees.Include(e => e.Status).AsQueryable(), e => e.RegionId).FirstOrDefaultAsync(e => e.Id == input.EmployeeId, ct)
                       ?? throw new NotFoundException("Сотрудник", input.EmployeeId);
        var system = await _db.AccessSystems.FirstOrDefaultAsync(s => s.Id == input.AccessSystemId, ct) ?? throw new NotFoundException("Система", input.AccessSystemId);
        if (input.AccessLevelId is not null && !await _db.AccessLevels.AnyAsync(l => l.Id == input.AccessLevelId && (l.AccessSystemId == null || l.AccessSystemId == system.Id), ct))
            throw new ValidationFailedException("Уровень доступа не относится к выбранной системе");
        EmployeeAccess a;
        if (id is null)
        {
            if (employee.Status?.Kind is EmployeeStatusKind.Terminated or EmployeeStatusKind.Archived)
                throw new BusinessException("EMPLOYEE_INACTIVE", "Нельзя выдать доступ уволенному сотруднику");
            a = new EmployeeAccess { RecordedAt = _clock.UtcNow };
            _db.EmployeeAccesses.Add(a);
        }
        else a = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Доступ", id);
        var grantedAt = input.GrantedAt?.ToUniversalTime() ?? (id is null ? _clock.UtcNow : a.GrantedAt);
        if (grantedAt > _clock.UtcNow.AddMinutes(5)) throw new BusinessException(ErrorCodes.FutureDate, "Дата не может быть в будущем");
        a.EmployeeId = employee.Id;
        a.AccessSystemId = system.Id;
        a.AccessLevelId = input.AccessLevelId;
        a.Username = input.Username;
        a.Role = input.Role;
        a.GrantedAt = grantedAt;
        if (input.Status != AccessStatus.Revoked) a.Status = input.Status;
        a.ResponsibleEmployeeId = input.ResponsibleEmployeeId;
        a.RequestReference = input.RequestReference;
        a.ReviewDueDate = input.ReviewDueDate ?? (system.ReviewIntervalMonths is { } m && id is null ? DateOnly.FromDateTime(grantedAt).AddMonths(m) : a.ReviewDueDate);
        a.Comment = input.Comment;
        a.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Access, null, input.CustomFields, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(a.Id, ct);
    }

    public async Task<AccessDto> RevokeAsync(Guid id, AccessRevokeRequest req, CancellationToken ct)
    {
        var a = await Visible().Include(x => x.Employee).Include(x => x.AccessSystem).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Доступ", id);
        if (a.Status == AccessStatus.Revoked) throw new BusinessException("ALREADY_REVOKED", "Доступ уже отозван");
        var at = req.RevokedAt?.ToUniversalTime() ?? _clock.UtcNow;
        if (at < a.GrantedAt) throw new BusinessException(ErrorCodes.TemporalConflict, "Дата отзыва раньше даты выдачи");
        a.Status = AccessStatus.Revoked;
        a.RevokedAt = at;
        a.RevokeReason = req.Reason;
        using (_auditCtx.Suppress())
        {
            _audit.Log("access.revoke", nameof(EmployeeAccess), a.Id, $"{a.Employee!.FullName}: {a.AccessSystem!.Name}", new { status = "Active" }, new { status = "Revoked", revokedAt = at }, req.Reason);
            await _db.SaveChangesAsync(ct);
        }
        return await GetAsync(id, ct);
    }

    public async Task<AccessDto> ReviewAsync(Guid id, AccessReviewRequest req, CancellationToken ct)
    {
        var a = await Visible().Include(x => x.AccessSystem).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Доступ", id);
        a.LastReviewedAt = _clock.UtcNow;
        a.ReviewDueDate = req.NextReviewDate ?? (a.AccessSystem!.ReviewIntervalMonths is { } m ? DateOnly.FromDateTime(_clock.UtcNow).AddMonths(m) : null);
        _audit.Log("access.review", nameof(EmployeeAccess), a.Id, a.AccessSystem!.Name, null, new { nextReview = a.ReviewDueDate }, req.Comment);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    /// <summary>Offboarding helper: revoke all active accesses of an employee.</summary>
    public async Task<int> RevokeAllAsync(Guid employeeId, DateTime? at, string? reason, CancellationToken ct)
    {
        var ids = await Visible().Where(a => a.EmployeeId == employeeId && a.Status != AccessStatus.Revoked).Select(a => a.Id).ToListAsync(ct);
        foreach (var id in ids) await RevokeAsync(id, new AccessRevokeRequest { RevokedAt = at, Reason = reason ?? "Офбординг" }, ct);
        return ids.Count;
    }
}
