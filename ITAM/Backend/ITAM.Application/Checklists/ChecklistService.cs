using System.ComponentModel.DataAnnotations;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Checklists;

public sealed class ChecklistTemplateInput
{
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    [MaxLength(2000)] public string? Description { get; set; }
    public ChecklistKind Kind { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? PositionId { get; set; }
    public Guid? RegionId { get; set; }
    public bool IsDefault { get; set; }
    public List<ChecklistTemplateItemInput> Items { get; set; } = new();
}

public sealed class ChecklistTemplateItemInput
{
    [Required, MaxLength(512)] public string Title { get; set; } = string.Empty;
    [MaxLength(2000)] public string? Description { get; set; }
    public ChecklistActionType ActionType { get; set; }
    public Guid? TargetId { get; set; }
    public bool IsRequired { get; set; } = true;
}

public sealed record ChecklistTemplateDto(Guid Id, string Name, string? Description, ChecklistKind Kind, Guid? DepartmentId, string? DepartmentName,
    Guid? PositionId, string? PositionName, Guid? RegionId, string? RegionName, bool IsDefault, bool IsArchived, IReadOnlyList<ChecklistTemplateItemDto> Items);

public sealed record ChecklistTemplateItemDto(Guid Id, string Title, string? Description, ChecklistActionType ActionType, Guid? TargetId, string? TargetName, bool IsRequired, int SortOrder);

public sealed record ChecklistDto(Guid Id, Guid EmployeeId, string EmployeeName, string Title, ChecklistKind Kind, ChecklistStatus Status,
    DateTime StartedAt, DateOnly? DueDate, DateTime? CompletedAt, string? Comment, int Done, int Total, IReadOnlyList<ChecklistItemDto> Items);

public sealed record ChecklistItemDto(Guid Id, string Title, string? Description, ChecklistActionType ActionType, Guid? TargetId, string? TargetName,
    bool IsRequired, bool IsDone, bool IsAuto, DateTime? DoneAt, string? DoneByName, string? Comment);

public sealed record ChecklistListItem(Guid Id, Guid EmployeeId, string EmployeeName, string? DepartmentName, string? RegionName, string Title,
    ChecklistKind Kind, ChecklistStatus Status, DateTime StartedAt, DateOnly? DueDate, DateTime? CompletedAt, int ManualDone, int Total);

public sealed class ChecklistQuery : PagedRequest
{
    public ChecklistKind? Kind { get; set; }
    public ChecklistStatus? Status { get; set; }
    public Guid? RegionId { get; set; }
    public Guid? EmployeeId { get; set; }
}

public sealed class ChecklistItemUpdate
{
    public bool IsDone { get; set; }
    [MaxLength(2000)] public string? Comment { get; set; }
}

/// <summary>Onboarding / offboarding checklists with manual and "smart" items whose state is computed from live data.</summary>
public sealed class ChecklistService
{
    private readonly IAppDbContext _db;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IRegionScope _scope;
    private readonly IAuditService _audit;

    public ChecklistService(IAppDbContext db, ICurrentUser user, IClock clock, IRegionScope scope, IAuditService audit)
    {
        _db = db; _user = user; _clock = clock; _scope = scope; _audit = audit;
    }

    private static bool IsAuto(ChecklistActionType t) => t != ChecklistActionType.Manual;

    // ---------------- Templates ----------------

    public async Task<IReadOnlyList<ChecklistTemplateDto>> TemplatesAsync(ChecklistKind? kind, bool includeArchived, CancellationToken ct)
    {
        var q = _db.ChecklistTemplates.AsNoTracking().Include(t => t.Items).AsQueryable();
        if (kind is not null) q = q.Where(t => t.Kind == kind);
        if (!includeArchived) q = q.Where(t => !t.IsArchived);
        var list = await q.OrderBy(t => t.Kind).ThenBy(t => t.Name).ToListAsync(ct);
        var result = new List<ChecklistTemplateDto>();
        foreach (var t in list) result.Add(await ToDto(t, ct));
        return result;
    }

    public async Task<ChecklistTemplateDto> TemplateAsync(Guid id, CancellationToken ct)
    {
        var t = await _db.ChecklistTemplates.AsNoTracking().Include(x => x.Items).FirstOrDefaultAsync(x => x.Id == id, ct)
                ?? throw new NotFoundException("Шаблон чек-листа", id);
        return await ToDto(t, ct);
    }

    private async Task<ChecklistTemplateDto> ToDto(ChecklistTemplate t, CancellationToken ct)
    {
        var items = new List<ChecklistTemplateItemDto>();
        foreach (var i in t.Items.OrderBy(i => i.SortOrder))
            items.Add(new ChecklistTemplateItemDto(i.Id, i.Title, i.Description, i.ActionType, i.TargetId, await TargetNameAsync(i.ActionType, i.TargetId, ct), i.IsRequired, i.SortOrder));
        return new ChecklistTemplateDto(t.Id, t.Name, t.Description, t.Kind, t.DepartmentId,
            t.DepartmentId is null ? null : await _db.Departments.Where(d => d.Id == t.DepartmentId).Select(d => d.Name).FirstOrDefaultAsync(ct),
            t.PositionId, t.PositionId is null ? null : await _db.Positions.Where(d => d.Id == t.PositionId).Select(d => d.Name).FirstOrDefaultAsync(ct),
            t.RegionId, t.RegionId is null ? null : await _db.Regions.Where(d => d.Id == t.RegionId).Select(d => d.Name).FirstOrDefaultAsync(ct),
            t.IsDefault, t.IsArchived, items);
    }

    private async Task<string?> TargetNameAsync(ChecklistActionType type, Guid? id, CancellationToken ct) => id is null ? null : type switch
    {
        ChecklistActionType.IssueAssetType => await _db.AssetTypes.Where(x => x.Id == id).Select(x => x.Name).FirstOrDefaultAsync(ct),
        ChecklistActionType.GrantAccess => await _db.AccessSystems.Where(x => x.Id == id).Select(x => x.Name).FirstOrDefaultAsync(ct),
        ChecklistActionType.AssignSoftware => await _db.Software.Where(x => x.Id == id).Select(x => x.Name).FirstOrDefaultAsync(ct),
        _ => null
    };

    public async Task<ChecklistTemplateDto> SaveTemplateAsync(Guid? id, ChecklistTemplateInput input, CancellationToken ct)
    {
        ChecklistTemplate t;
        if (id is null)
        {
            t = new ChecklistTemplate();
            _db.ChecklistTemplates.Add(t);
        }
        else
        {
            t = await _db.ChecklistTemplates.Include(x => x.Items).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон чек-листа", id);
            _db.ChecklistTemplateItems.RemoveRange(t.Items);
            t.Items.Clear();
        }
        t.Name = input.Name.Trim();
        t.Description = input.Description;
        t.Kind = input.Kind;
        t.DepartmentId = input.DepartmentId;
        t.PositionId = input.PositionId;
        t.RegionId = input.RegionId;
        t.IsDefault = input.IsDefault;
        var order = 0;
        foreach (var i in input.Items)
        {
            if (i.ActionType is ChecklistActionType.IssueAssetType or ChecklistActionType.GrantAccess or ChecklistActionType.AssignSoftware && i.TargetId is null)
                throw new ValidationFailedException($"Пункт «{i.Title}»: выберите объект (тип актива / систему / ПО)");
            var item = new ChecklistTemplateItem { TemplateId = t.Id, Title = i.Title.Trim(), Description = i.Description, ActionType = i.ActionType, TargetId = i.TargetId, IsRequired = i.IsRequired, SortOrder = order++ };
            t.Items.Add(item);
            _db.ChecklistTemplateItems.Add(item);
        }
        if (t.IsDefault)
            await _db.ChecklistTemplates.Where(x => x.Kind == t.Kind && x.Id != t.Id && x.IsDefault)
                .ExecuteUpdateAsync(s => s.SetProperty(x => x.IsDefault, false), ct);
        await _db.SaveChangesAsync(ct);
        return await TemplateAsync(t.Id, ct);
    }

    public async Task ArchiveTemplateAsync(Guid id, bool archived, CancellationToken ct)
    {
        var t = await _db.ChecklistTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон чек-листа", id);
        t.IsArchived = archived;
        await _db.SaveChangesAsync(ct);
    }

    // ---------------- Instances ----------------

    public async Task<ChecklistDto> StartAsync(Guid employeeId, ChecklistKind kind, Guid? templateId, CancellationToken ct)
    {
        var emp = await _scope.Apply(_db.Employees.AsQueryable(), e => e.RegionId).FirstOrDefaultAsync(e => e.Id == employeeId, ct)
                  ?? throw new NotFoundException("Сотрудник", employeeId);
        ChecklistTemplate? template;
        if (templateId is not null)
            template = await _db.ChecklistTemplates.Include(t => t.Items).FirstOrDefaultAsync(t => t.Id == templateId && t.Kind == kind, ct)
                       ?? throw new NotFoundException("Шаблон чек-листа", templateId);
        else
        {
            // Most specific template wins: department + position + region > ... > default.
            var candidates = await _db.ChecklistTemplates.Include(t => t.Items)
                .Where(t => t.Kind == kind && !t.IsArchived
                            && (t.DepartmentId == null || t.DepartmentId == emp.DepartmentId)
                            && (t.PositionId == null || t.PositionId == emp.PositionId)
                            && (t.RegionId == null || t.RegionId == emp.RegionId))
                .ToListAsync(ct);
            template = candidates
                .OrderByDescending(t => (t.DepartmentId != null ? 4 : 0) + (t.PositionId != null ? 2 : 0) + (t.RegionId != null ? 1 : 0))
                .ThenByDescending(t => t.IsDefault).FirstOrDefault();
        }

        var checklist = new EmployeeChecklist
        {
            EmployeeId = employeeId,
            TemplateId = template?.Id,
            Kind = kind,
            Title = template?.Name ?? (kind == ChecklistKind.Onboarding ? "Онбординг" : "Офбординг"),
            Status = ChecklistStatus.InProgress,
            StartedAt = _clock.UtcNow,
            DueDate = DateOnly.FromDateTime(_clock.UtcNow.AddDays(kind == ChecklistKind.Onboarding ? 5 : 3)),
        };
        var items = template?.Items.OrderBy(i => i.SortOrder)
                        .Select(i => (i.Title, i.Description, i.ActionType, i.TargetId, i.IsRequired)).ToList()
                    ?? DefaultItems(kind);
        var order = 0;
        foreach (var i in items)
            checklist.Items.Add(new EmployeeChecklistItem
            {
                Title = i.Title, Description = i.Description, ActionType = i.ActionType, TargetId = i.TargetId, IsRequired = i.IsRequired, SortOrder = order++
            });
        _db.EmployeeChecklists.Add(checklist);
        _audit.Log($"checklist.{kind.ToString().ToLowerInvariant()}.start", nameof(Employee), employeeId, emp.FullName, null, new { checklist.Title });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(checklist.Id, ct);
    }

    public static List<(string Title, string? Description, ChecklistActionType ActionType, Guid? TargetId, bool IsRequired)> DefaultItems(ChecklistKind kind)
        => kind == ChecklistKind.Onboarding
            ? new()
            {
                ("Создать учётную запись AD", null, ChecklistActionType.Manual, null, true),
                ("Создать почтовый ящик", null, ChecklistActionType.Manual, null, true),
                ("Выдать оборудование", null, ChecklistActionType.Manual, null, true),
                ("Выдать доступы", null, ChecklistActionType.Manual, null, false),
                ("Подписать документы", null, ChecklistActionType.SignDocuments, null, true),
            }
            : new()
            {
                ("Вернуть всё оборудование", null, ChecklistActionType.ReturnAllAssets, null, true),
                ("Отозвать лицензии", null, ChecklistActionType.RevokeAllLicenses, null, true),
                ("Отозвать доступы (AD, Email, VPN и др.)", null, ChecklistActionType.RevokeAllAccess, null, true),
                ("Закрыть ремонты", null, ChecklistActionType.CloseRepairs, null, false),
                ("Подписать документы", null, ChecklistActionType.SignDocuments, null, false),
                ("Сформировать итоговый документ", null, ChecklistActionType.GenerateDocument, null, true),
            };

    public async Task<PagedResult<ChecklistListItem>> ListAsync(ChecklistQuery q, CancellationToken ct)
    {
        var query = _scope.Apply(_db.EmployeeChecklists.AsNoTracking(), c => c.Employee!.RegionId);
        if (q.Kind is not null) query = query.Where(c => c.Kind == q.Kind);
        if (q.Status is not null) query = query.Where(c => c.Status == q.Status);
        if (q.RegionId is not null) query = query.Where(c => c.Employee!.RegionId == q.RegionId);
        if (q.EmployeeId is not null) query = query.Where(c => c.EmployeeId == q.EmployeeId);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(c => EF.Functions.ILike(c.Employee!.FullName, like) || EF.Functions.ILike(c.Title, like));
        }
        query = query.OrderByDescending(c => c.StartedAt);
        return await query.ToPagedAsync(q, c => new ChecklistListItem(c.Id, c.EmployeeId, c.Employee!.FullName,
            c.Employee.Department != null ? c.Employee.Department.Name : null, c.Employee.Region != null ? c.Employee.Region.Name : null,
            c.Title, c.Kind, c.Status, c.StartedAt, c.DueDate, c.CompletedAt, c.Items.Count(i => i.IsDone), c.Items.Count), ct);
    }

    public async Task<IReadOnlyList<ChecklistDto>> ForEmployeeAsync(Guid employeeId, CancellationToken ct)
    {
        var ids = await _db.EmployeeChecklists.AsNoTracking().Where(c => c.EmployeeId == employeeId)
            .OrderByDescending(c => c.StartedAt).Select(c => c.Id).ToListAsync(ct);
        var result = new List<ChecklistDto>();
        foreach (var id in ids) result.Add(await GetAsync(id, ct));
        return result;
    }

    public async Task<ChecklistDto> GetAsync(Guid id, CancellationToken ct)
    {
        var c = await _db.EmployeeChecklists.AsNoTracking().Include(x => x.Items).Include(x => x.Employee)
                    .FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Чек-лист", id);
        _scope.EnsureAccess(c.Employee!.RegionId);
        var auto = await AutoStateAsync(c, ct);
        var items = new List<ChecklistItemDto>();
        foreach (var i in c.Items.OrderBy(i => i.SortOrder))
        {
            var isAuto = IsAuto(i.ActionType);
            var done = isAuto ? auto.GetValueOrDefault(i.Id) || i.IsDone : i.IsDone;
            items.Add(new ChecklistItemDto(i.Id, i.Title, i.Description, i.ActionType, i.TargetId, await TargetNameAsync(i.ActionType, i.TargetId, ct),
                i.IsRequired, done, isAuto, i.DoneAt, i.DoneByName, i.Comment));
        }
        return new ChecklistDto(c.Id, c.EmployeeId, c.Employee.FullName, c.Title, c.Kind, c.Status, c.StartedAt, c.DueDate, c.CompletedAt, c.Comment,
            items.Count(i => i.IsDone), items.Count, items);
    }

    /// <summary>Computes completion of smart items from live data.</summary>
    private async Task<Dictionary<Guid, bool>> AutoStateAsync(EmployeeChecklist c, CancellationToken ct)
    {
        var emp = c.EmployeeId;
        var result = new Dictionary<Guid, bool>();
        foreach (var i in c.Items.Where(i => IsAuto(i.ActionType)))
        {
            result[i.Id] = i.ActionType switch
            {
                ChecklistActionType.IssueAssetType => await _db.Assets.AnyAsync(a => a.EmployeeId == emp && a.AssetTypeId == i.TargetId, ct),
                ChecklistActionType.GrantAccess => await _db.EmployeeAccesses.AnyAsync(a => a.EmployeeId == emp && a.AccessSystemId == i.TargetId && a.Status == AccessStatus.Active, ct),
                ChecklistActionType.AssignSoftware => await _db.LicenseAssignments.AnyAsync(a => a.EmployeeId == emp && a.RevokedAt == null && a.License!.SoftwareId == i.TargetId, ct),
                ChecklistActionType.SignDocuments => !await _db.GeneratedDocuments.AnyAsync(d => d.EmployeeId == emp && !d.IsVoided && d.EmployeeSignatureStatus == SignatureStatus.Pending, ct),
                ChecklistActionType.ReturnAllAssets => !await _db.Assets.AnyAsync(a => a.EmployeeId == emp, ct),
                ChecklistActionType.RevokeAllAccess => !await _db.EmployeeAccesses.AnyAsync(a => a.EmployeeId == emp && a.Status != AccessStatus.Revoked, ct),
                ChecklistActionType.RevokeAllLicenses => !await _db.LicenseAssignments.AnyAsync(a => a.EmployeeId == emp && a.RevokedAt == null, ct),
                ChecklistActionType.CloseRepairs => !await _db.Repairs.AnyAsync(r => r.EmployeeId == emp && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled, ct),
                ChecklistActionType.GenerateDocument => await _db.GeneratedDocuments.AnyAsync(d => d.SourceType == "EmployeeChecklist" && d.SourceId == c.Id && !d.IsVoided, ct),
                _ => false
            };
        }
        return result;
    }

    public async Task<ChecklistDto> UpdateItemAsync(Guid checklistId, Guid itemId, ChecklistItemUpdate req, CancellationToken ct)
    {
        var c = await _db.EmployeeChecklists.Include(x => x.Items).Include(x => x.Employee).FirstOrDefaultAsync(x => x.Id == checklistId, ct)
                ?? throw new NotFoundException("Чек-лист", checklistId);
        _scope.EnsureAccess(c.Employee!.RegionId);
        if (c.Status != ChecklistStatus.InProgress) throw new BusinessException("CHECKLIST_CLOSED", "Чек-лист уже закрыт");
        var item = c.Items.FirstOrDefault(i => i.Id == itemId) ?? throw new NotFoundException("Пункт чек-листа", itemId);
        item.IsDone = req.IsDone;
        item.Comment = req.Comment;
        item.DoneAt = req.IsDone ? _clock.UtcNow : null;
        item.DoneById = req.IsDone ? _user.UserId : null;
        item.DoneByName = req.IsDone ? _user.DisplayName ?? _user.UserName : null;
        _audit.Log("checklist.item", nameof(EmployeeChecklist), c.Id, c.Title, null, new { item = item.Title, done = req.IsDone, req.Comment });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(checklistId, ct);
    }

    public async Task<ChecklistDto> CompleteAsync(Guid id, bool force, CancellationToken ct)
    {
        var dto = await GetAsync(id, ct);
        var missing = dto.Items.Where(i => i.IsRequired && !i.IsDone).Select(i => i.Title).ToList();
        if (missing.Count > 0 && !force)
            throw new ConflictException("CHECKLIST_INCOMPLETE", "Не выполнены обязательные пункты: " + string.Join("; ", missing), missing);
        var c = await _db.EmployeeChecklists.FirstAsync(x => x.Id == id, ct);
        c.Status = ChecklistStatus.Completed;
        c.CompletedAt = _clock.UtcNow;
        c.CompletedById = _user.UserId;
        _audit.Log("checklist.complete", nameof(EmployeeChecklist), id, c.Title, null, new { forced = missing.Count > 0, missing });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<ChecklistDto> CancelAsync(Guid id, string? reason, CancellationToken ct)
    {
        var c = await _db.EmployeeChecklists.Include(x => x.Employee).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Чек-лист", id);
        _scope.EnsureAccess(c.Employee!.RegionId);
        c.Status = ChecklistStatus.Cancelled;
        c.Comment = reason;
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }
}
