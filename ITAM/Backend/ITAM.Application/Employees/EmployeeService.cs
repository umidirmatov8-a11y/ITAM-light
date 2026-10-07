using System.Linq.Expressions;
using ITAM.Application.Checklists;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Employees;

public sealed class EmployeeService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly IDepartmentScope _deptScope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly ICustomFieldValidator _customFields;
    private readonly INumberingService _numbering;
    private readonly ChecklistService _checklists;

    public EmployeeService(IAppDbContext db, IRegionScope scope, IDepartmentScope deptScope, ICurrentUser user, IClock clock,
        IAuditService audit, AuditContext auditCtx, ICustomFieldValidator customFields, INumberingService numbering, ChecklistService checklists)
    {
        _db = db; _scope = scope; _deptScope = deptScope; _user = user; _clock = clock; _audit = audit; _auditCtx = auditCtx;
        _customFields = customFields; _numbering = numbering; _checklists = checklists;
    }

    /// <summary>Employees visible to the current user (region + department scope).</summary>
    public async Task<IQueryable<Employee>> VisibleAsync(CancellationToken ct)
    {
        var q = _scope.Apply(_db.Employees.AsQueryable(), e => e.RegionId);
        var depts = await _deptScope.AllowedDepartmentsAsync(ct);
        if (depts is not null) q = q.Where(e => e.DepartmentId != null && depts.Contains(e.DepartmentId.Value));
        return q;
    }

    private static readonly Dictionary<string, Expression<Func<Employee, object?>>> Sorts = new()
    {
        ["fullName"] = e => e.FullName,
        ["employeeNumber"] = e => e.EmployeeNumber,
        ["departmentName"] = e => e.Department!.Name,
        ["positionName"] = e => e.Position!.Name,
        ["regionName"] = e => e.Region!.Name,
        ["statusName"] = e => e.Status!.Name,
        ["hireDate"] = e => e.HireDate,
        ["createdAt"] = e => e.CreatedAt,
        ["email"] = e => e.Email,
    };

    public async Task<IQueryable<Employee>> FilteredAsync(EmployeeQuery q, CancellationToken ct)
    {
        var query = (await VisibleAsync(ct)).AsNoTracking();
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(e => EF.Functions.ILike(e.FullName, like) || EF.Functions.ILike(e.EmployeeNumber, like)
                                     || (e.Login != null && EF.Functions.ILike(e.Login, like)) || (e.Email != null && EF.Functions.ILike(e.Email, like))
                                     || (e.Phone != null && EF.Functions.ILike(e.Phone, like)));
        }
        if (q.RegionId is not null) query = query.Where(e => e.RegionId == q.RegionId);
        if (q.DepartmentId is not null)
        {
            if (q.IncludeSubDepartments)
            {
                var ids = await DepartmentSubtreeAsync(q.DepartmentId.Value, ct);
                query = query.Where(e => e.DepartmentId != null && ids.Contains(e.DepartmentId.Value));
            }
            else query = query.Where(e => e.DepartmentId == q.DepartmentId);
        }
        if (q.PositionId is not null) query = query.Where(e => e.PositionId == q.PositionId);
        if (q.StatusId is not null) query = query.Where(e => e.StatusId == q.StatusId);
        if (q.StatusKind is not null) query = query.Where(e => e.Status!.Kind == q.StatusKind);
        if (q.ActiveOnly) query = query.Where(e => e.Status!.Kind != EmployeeStatusKind.Terminated && e.Status.Kind != EmployeeStatusKind.Archived);
        if (q.LocationId is not null) query = query.Where(e => e.LocationId == q.LocationId || e.RoomId == q.LocationId);
        if (q.ManagerId is not null) query = query.Where(e => e.ManagerId == q.ManagerId);
        if (q.HiredFrom is not null) query = query.Where(e => e.HireDate >= q.HiredFrom);
        if (q.HiredTo is not null) query = query.Where(e => e.HireDate <= q.HiredTo);
        if (q.HasAssets is not null)
            query = q.HasAssets.Value
                ? query.Where(e => _db.Assets.Any(a => a.EmployeeId == e.Id))
                : query.Where(e => !_db.Assets.Any(a => a.EmployeeId == e.Id));
        return query;
    }

    public async Task<List<Guid>> DepartmentSubtreeAsync(Guid root, CancellationToken ct)
    {
        var all = await _db.Departments.AsNoTracking().Select(d => new { d.Id, d.ParentId }).ToListAsync(ct);
        var result = new HashSet<Guid> { root };
        bool added;
        do
        {
            added = false;
            foreach (var d in all)
                if (d.ParentId is not null && result.Contains(d.ParentId.Value) && result.Add(d.Id)) added = true;
        } while (added);
        return result.ToList();
    }

    public async Task<PagedResult<EmployeeListItem>> ListAsync(EmployeeQuery q, CancellationToken ct)
    {
        var query = (await FilteredAsync(q, ct)).SortBy(q, Sorts, "fullName");
        return await query.ToPagedAsync(q, ListProjection(), ct);
    }

    public Expression<Func<Employee, EmployeeListItem>> ListProjection()
        => e => new EmployeeListItem(e.Id, e.EmployeeNumber, e.FullName, e.Login, e.Email, e.Phone,
            e.PositionId, e.Position != null ? e.Position.Name : null,
            e.DepartmentId, e.Department != null ? e.Department.Name : null,
            e.RegionId, e.Region != null ? e.Region.Name : null,
            e.LocationId, e.Location != null ? e.Location.Name : null,
            e.StatusId, e.Status != null ? e.Status.Name : null, e.Status != null ? e.Status.Color : null,
            e.Status != null ? e.Status.Kind : EmployeeStatusKind.Active,
            e.HireDate, e.TerminationDate, _db.Assets.Count(a => a.EmployeeId == e.Id), e.PhotoFileId);

    public async Task<EmployeeDto> GetAsync(Guid id, CancellationToken ct)
    {
        var e = await (await VisibleAsync(ct)).AsNoTracking()
            .Include(x => x.Position).Include(x => x.Department).Include(x => x.Region).Include(x => x.Location)
            .Include(x => x.Room).Include(x => x.Manager).Include(x => x.Status)
            .FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Сотрудник", id);
        var assets = await _db.Assets.CountAsync(a => a.EmployeeId == id, ct);
        var licenses = await _db.LicenseAssignments.CountAsync(l => l.EmployeeId == id && l.RevokedAt == null, ct);
        var accesses = await _db.EmployeeAccesses.CountAsync(a => a.EmployeeId == id && a.Status != AccessStatus.Revoked, ct);
        return new EmployeeDto(e.Id, e.EmployeeNumber, e.LastName, e.FirstName, e.MiddleName, e.FullName, e.Login, e.Email, e.Phone,
            e.PositionId, e.Position?.Name, e.DepartmentId, e.Department?.Name, e.Department?.FullPath,
            e.RegionId, e.Region?.Name, e.LocationId, e.Location?.FullPath ?? e.Location?.Name, e.RoomId, e.Room?.Name,
            e.ManagerId, e.Manager?.FullName, e.HireDate, e.TerminationDate,
            e.StatusId, e.Status?.Name, e.Status?.Color, e.Status?.Kind ?? EmployeeStatusKind.Active,
            e.Comment, e.PhotoFileId, Json.ToElement(e.CustomFields), e.ExternalId, e.CreatedAt, e.UpdatedAt, e.Version,
            assets, licenses, accesses);
    }

    public async Task<EmployeeDto> CreateAsync(EmployeeInput input, CancellationToken ct)
    {
        _scope.EnsureAccess(input.RegionId);
        await ValidateReferencesAsync(input, null, ct);
        var employee = new Employee();
        Apply(employee, input);
        employee.EmployeeNumber = string.IsNullOrWhiteSpace(input.EmployeeNumber)
            ? await _numbering.NextAsync(c => c.EmployeeNumberFormat, "employee", ct: ct)
            : input.EmployeeNumber.Trim();
        if (await _db.Employees.AnyAsync(x => x.EmployeeNumber == employee.EmployeeNumber, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Табельный номер {employee.EmployeeNumber} уже используется");
        employee.StatusId = input.StatusId ?? await DefaultStatusAsync(EmployeeStatusKind.Active, ct);
        employee.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Employee, null, input.CustomFields, ct);
        _db.Employees.Add(employee);

        var effective = input.HireDate is { } hd ? hd.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc) : _clock.UtcNow;
        _db.EmployeeOrgHistory.Add(await BuildOrgHistoryAsync(employee, effective, "Приём на работу", ct));
        await _db.SaveChangesAsync(ct);

        if (input.StartOnboarding)
            await _checklists.StartAsync(employee.Id, ChecklistKind.Onboarding, input.OnboardingTemplateId, ct);
        return await GetAsync(employee.Id, ct);
    }

    public async Task<EmployeeDto> UpdateAsync(Guid id, EmployeeInput input, CancellationToken ct)
    {
        var employee = await (await VisibleAsync(ct)).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException("Сотрудник", id);
        if (input.Version is not null && input.Version != employee.Version)
            throw new ConflictException(ErrorCodes.ConcurrentModification, "Карточка сотрудника была изменена другим пользователем. Обновите страницу.");
        _scope.EnsureAccess(input.RegionId);
        await ValidateReferencesAsync(input, id, ct);

        var orgChanged = employee.DepartmentId != input.DepartmentId || employee.PositionId != input.PositionId
                         || employee.RegionId != input.RegionId || employee.LocationId != input.LocationId || employee.ManagerId != input.ManagerId;
        Apply(employee, input);
        if (!string.IsNullOrWhiteSpace(input.EmployeeNumber) && input.EmployeeNumber.Trim() != employee.EmployeeNumber)
        {
            if (await _db.Employees.AnyAsync(x => x.EmployeeNumber == input.EmployeeNumber.Trim() && x.Id != id, ct))
                throw new ConflictException(ErrorCodes.Duplicate, $"Табельный номер {input.EmployeeNumber} уже используется");
            employee.EmployeeNumber = input.EmployeeNumber.Trim();
        }
        if (input.StatusId is not null && input.StatusId != employee.StatusId)
        {
            var kind = await _db.EmployeeStatuses.Where(s => s.Id == input.StatusId).Select(s => (EmployeeStatusKind?)s.Kind).FirstOrDefaultAsync(ct)
                       ?? throw new ValidationFailedException("Неизвестный статус");
            if (kind == EmployeeStatusKind.Terminated)
                throw new BusinessException("USE_TERMINATION", "Для увольнения используйте операцию «Уволить»");
            employee.StatusId = input.StatusId.Value;
        }
        employee.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Employee, null, input.CustomFields, ct);

        if (orgChanged)
        {
            var effective = input.OrgChangeEffectiveAt?.ToUniversalTime() ?? _clock.UtcNow;
            await CloseOrgHistoryAsync(id, effective, ct);
            _db.EmployeeOrgHistory.Add(await BuildOrgHistoryAsync(employee, effective, input.OrgChangeReason ?? "Изменение оргструктуры", ct));
        }
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    private static void Apply(Employee e, EmployeeInput i)
    {
        e.LastName = i.LastName.Trim();
        e.FirstName = i.FirstName.Trim();
        e.MiddleName = string.IsNullOrWhiteSpace(i.MiddleName) ? null : i.MiddleName.Trim();
        e.FullName = Employee.ComposeFullName(e.LastName, e.FirstName, e.MiddleName);
        e.Login = string.IsNullOrWhiteSpace(i.Login) ? null : i.Login.Trim();
        e.Email = string.IsNullOrWhiteSpace(i.Email) ? null : i.Email.Trim();
        e.Phone = string.IsNullOrWhiteSpace(i.Phone) ? null : i.Phone.Trim();
        e.PositionId = i.PositionId;
        e.DepartmentId = i.DepartmentId;
        e.RegionId = i.RegionId;
        e.LocationId = i.LocationId;
        e.RoomId = i.RoomId;
        e.ManagerId = i.ManagerId;
        e.HireDate = i.HireDate;
        e.Comment = i.Comment;
    }

    private async Task ValidateReferencesAsync(EmployeeInput i, Guid? selfId, CancellationToken ct)
    {
        var errors = new Dictionary<string, string[]>();
        if (!await _db.Regions.AnyAsync(r => r.Id == i.RegionId, ct)) errors["regionId"] = new[] { "Регион не найден" };
        if (i.DepartmentId is not null && !await _db.Departments.AnyAsync(d => d.Id == i.DepartmentId, ct)) errors["departmentId"] = new[] { "Подразделение не найдено" };
        if (i.PositionId is not null && !await _db.Positions.AnyAsync(d => d.Id == i.PositionId, ct)) errors["positionId"] = new[] { "Должность не найдена" };
        if (i.LocationId is not null && !await _db.Locations.AnyAsync(d => d.Id == i.LocationId, ct)) errors["locationId"] = new[] { "Офис не найден" };
        if (i.RoomId is not null && !await _db.Locations.AnyAsync(d => d.Id == i.RoomId, ct)) errors["roomId"] = new[] { "Кабинет не найден" };
        if (i.ManagerId is not null)
        {
            if (i.ManagerId == selfId) errors["managerId"] = new[] { "Сотрудник не может быть своим руководителем" };
            else if (!await _db.Employees.AnyAsync(d => d.Id == i.ManagerId, ct)) errors["managerId"] = new[] { "Руководитель не найден" };
        }
        if (errors.Count > 0) throw new ValidationFailedException("Проверьте заполнение полей", errors);
    }

    public async Task<Guid> DefaultStatusAsync(EmployeeStatusKind kind, CancellationToken ct)
        => await _db.EmployeeStatuses.Where(s => s.Kind == kind && !s.IsArchived).OrderByDescending(s => s.IsSystem).ThenBy(s => s.SortOrder)
               .Select(s => (Guid?)s.Id).FirstOrDefaultAsync(ct)
           ?? throw new BusinessException("STATUS_NOT_CONFIGURED", $"Не настроен статус сотрудника вида {kind}");

    private async Task<EmployeeOrgHistory> BuildOrgHistoryAsync(Employee e, DateTime effective, string? reason, CancellationToken ct)
    {
        var snapshot = new
        {
            department = e.DepartmentId is null ? null : await _db.Departments.Where(d => d.Id == e.DepartmentId).Select(d => d.FullPath ?? d.Name).FirstOrDefaultAsync(ct),
            position = e.PositionId is null ? null : await _db.Positions.Where(d => d.Id == e.PositionId).Select(d => d.Name).FirstOrDefaultAsync(ct),
            region = await _db.Regions.Where(d => d.Id == e.RegionId).Select(d => d.Name).FirstOrDefaultAsync(ct),
            location = e.LocationId is null ? null : await _db.Locations.Where(d => d.Id == e.LocationId).Select(d => d.FullPath ?? d.Name).FirstOrDefaultAsync(ct),
            manager = e.ManagerId is null ? null : await _db.Employees.Where(d => d.Id == e.ManagerId).Select(d => d.FullName).FirstOrDefaultAsync(ct),
            status = await _db.EmployeeStatuses.Where(d => d.Id == e.StatusId).Select(d => d.Name).FirstOrDefaultAsync(ct),
        };
        return new EmployeeOrgHistory
        {
            EmployeeId = e.Id,
            EffectiveFrom = effective,
            RecordedAt = _clock.UtcNow,
            RecordedById = _user.UserId,
            DepartmentId = e.DepartmentId,
            PositionId = e.PositionId,
            RegionId = e.RegionId,
            LocationId = e.LocationId,
            ManagerId = e.ManagerId,
            StatusId = e.StatusId == Guid.Empty ? null : e.StatusId,
            Snapshot = Json.Serialize(snapshot),
            Reason = reason
        };
    }

    private async Task CloseOrgHistoryAsync(Guid employeeId, DateTime effective, CancellationToken ct)
    {
        var open = await _db.EmployeeOrgHistory.Where(h => h.EmployeeId == employeeId && h.EffectiveTo == null).ToListAsync(ct);
        foreach (var h in open) h.EffectiveTo = effective < h.EffectiveFrom ? h.EffectiveFrom : effective;
    }

    public async Task<IReadOnlyList<EmployeeOrgHistoryDto>> OrgHistoryAsync(Guid id, CancellationToken ct)
    {
        await EnsureVisibleAsync(id, ct);
        var rows = await _db.EmployeeOrgHistory.AsNoTracking().Where(h => h.EmployeeId == id).OrderByDescending(h => h.EffectiveFrom).ToListAsync(ct);
        return rows.Select(h =>
        {
            var s = Json.ToDictionary(h.Snapshot);
            string? S(string k) => s is not null && s.TryGetValue(k, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.String ? v.GetString() : null;
            return new EmployeeOrgHistoryDto(h.Id, h.EffectiveFrom, h.EffectiveTo, h.RecordedAt, S("department"), S("position"), S("region"),
                S("location"), S("manager"), S("status"), h.Reason);
        }).ToList();
    }

    public async Task EnsureVisibleAsync(Guid id, CancellationToken ct)
    {
        if (!await (await VisibleAsync(ct)).AnyAsync(e => e.Id == id, ct)) throw new NotFoundException("Сотрудник", id);
    }

    public async Task<OpenItemsDto> OpenItemsAsync(Guid id, CancellationToken ct)
    {
        await EnsureVisibleAsync(id, ct);
        var assets = await _db.Assets.AsNoTracking().Where(a => a.EmployeeId == id)
            .Select(a => new OpenAssetItem(a.Id, a.InventoryNumber, a.Name, a.AssetType!.Name,
                _db.Assignments.Where(x => x.AssetId == a.Id && x.EmployeeId == id && x.EffectiveTo == null && !x.IsCancelled).Select(x => (DateTime?)x.EffectiveFrom).FirstOrDefault(),
                _db.Assignments.Where(x => x.AssetId == a.Id && x.EmployeeId == id && x.EffectiveTo == null && !x.IsCancelled).Select(x => (Guid?)x.Id).FirstOrDefault()))
            .ToListAsync(ct);
        var licenses = await _db.LicenseAssignments.AsNoTracking().Where(l => l.EmployeeId == id && l.RevokedAt == null)
            .Select(l => new OpenLicenseItem(l.Id, l.LicenseId, l.License!.Name, l.License.Software != null ? l.License.Software.Name : null, l.AssignedAt))
            .ToListAsync(ct);
        var accesses = await _db.EmployeeAccesses.AsNoTracking().Where(a => a.EmployeeId == id && a.Status != AccessStatus.Revoked)
            .Select(a => new OpenAccessItem(a.Id, a.AccessSystem!.Name, a.Username, a.AccessLevel != null ? a.AccessLevel.Name : null, a.Status, a.GrantedAt))
            .ToListAsync(ct);
        var repairs = await _db.Repairs.AsNoTracking()
            .Where(r => r.EmployeeId == id && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled)
            .Select(r => new OpenRepairItem(r.Id, r.Number, r.Asset!.InventoryNumber, r.Status!.Name, r.OpenedAt)).ToListAsync(ct);
        var docs = await _db.GeneratedDocuments.AsNoTracking()
            .Where(d => d.EmployeeId == id && !d.IsVoided && d.EmployeeSignatureStatus == SignatureStatus.Pending)
            .Select(d => new OpenDocumentItem(d.Id, d.Number, d.Title, d.CreatedAt)).ToListAsync(ct);
        var checklists = await _db.EmployeeChecklists.AsNoTracking().Where(c => c.EmployeeId == id && c.Status == ChecklistStatus.InProgress)
            .Select(c => new OpenChecklistItem(c.Id, c.Title, c.Kind, c.Items.Count(i => i.IsDone), c.Items.Count)).ToListAsync(ct);
        return new OpenItemsDto(assets, licenses, accesses, repairs, docs, checklists);
    }

    public async Task<EmployeeDto> TerminateAsync(Guid id, TerminateRequest req, CancellationToken ct)
    {
        var employee = await (await VisibleAsync(ct)).Include(e => e.Status).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException("Сотрудник", id);
        var open = await OpenItemsAsync(id, ct);
        if (open.Total > 0 && !req.Force)
            throw new ConflictException(ErrorCodes.OpenItems,
                $"У сотрудника есть незакрытые позиции: оборудование {open.Assets.Count}, лицензии {open.Licenses.Count}, доступы {open.Accesses.Count}, ремонты {open.Repairs.Count}",
                open);
        var oldStatus = employee.Status?.Name;
        employee.TerminationDate = req.TerminationDate;
        employee.StatusId = await DefaultStatusAsync(EmployeeStatusKind.Terminated, ct);
        var effective = req.TerminationDate.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc);
        await CloseOrgHistoryAsync(id, effective, ct);
        _db.EmployeeOrgHistory.Add(await BuildOrgHistoryAsync(employee, effective, req.Reason ?? "Увольнение", ct));
        using (_auditCtx.Suppress())
        {
            _audit.Log("employee.terminate", nameof(Employee), id, employee.FullName,
                new { status = oldStatus }, new { status = "Уволен", terminationDate = req.TerminationDate, openItems = open.Total, forced = req.Force && open.Total > 0 },
                req.Reason);
            await _db.SaveChangesAsync(ct);
        }
        if (req.StartOffboarding && !await _db.EmployeeChecklists.AnyAsync(c => c.EmployeeId == id && c.Kind == ChecklistKind.Offboarding && c.Status == ChecklistStatus.InProgress, ct))
            await _checklists.StartAsync(id, ChecklistKind.Offboarding, req.OffboardingTemplateId, ct);
        return await GetAsync(id, ct);
    }

    public async Task ArchiveAsync(Guid id, CancellationToken ct)
    {
        var employee = await (await VisibleAsync(ct)).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException("Сотрудник", id);
        var open = await OpenItemsAsync(id, ct);
        if (open.Assets.Count > 0 || open.Licenses.Count > 0 || open.Accesses.Count > 0)
            throw new ConflictException(ErrorCodes.HasDependencies, "Нельзя архивировать сотрудника с активным оборудованием, лицензиями или доступами", open);
        employee.StatusId = await DefaultStatusAsync(EmployeeStatusKind.Archived, ct);
        await _db.SaveChangesAsync(ct);
    }

    /// <summary>Soft delete. Allowed only when the employee has no history at all (otherwise archive).</summary>
    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var employee = await (await VisibleAsync(ct)).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException("Сотрудник", id);
        var hasHistory = await _db.Assignments.AnyAsync(a => a.EmployeeId == id, ct)
                         || await _db.LicenseAssignments.AnyAsync(a => a.EmployeeId == id, ct)
                         || await _db.EmployeeAccesses.AnyAsync(a => a.EmployeeId == id, ct)
                         || await _db.GeneratedDocuments.AnyAsync(a => a.EmployeeId == id, ct)
                         || await _db.Assets.AnyAsync(a => a.EmployeeId == id || a.ResponsibleEmployeeId == id, ct);
        if (hasHistory)
            throw new ConflictException(ErrorCodes.HasDependencies, "У сотрудника есть история операций — удаление запрещено, используйте архивирование");
        _db.Employees.Remove(employee); // converted to soft delete
        await _db.SaveChangesAsync(ct);
    }

    public async Task<BulkResult> BulkAsync(EmployeeBulkRequest req, CancellationToken ct)
    {
        var errors = new List<BulkError>();
        var ok = 0;
        var employees = await (await VisibleAsync(ct)).Where(e => req.Ids.Contains(e.Id)).ToListAsync(ct);
        foreach (var missing in req.Ids.Except(employees.Select(e => e.Id)))
            errors.Add(new BulkError(missing, null, "NOT_FOUND", "Не найден или вне вашей области доступа"));
        foreach (var e in employees)
        {
            try
            {
                switch (req.Action)
                {
                    case "changeRegion":
                        if (req.Value is null || !await _db.Regions.AnyAsync(r => r.Id == req.Value, ct)) throw new ValidationFailedException("Регион не найден");
                        _scope.EnsureAccess(req.Value);
                        if (e.RegionId != req.Value) { e.RegionId = req.Value.Value; await AddBulkHistory(e, "Массовая смена региона", ct); }
                        break;
                    case "changeDepartment":
                        if (req.Value is not null && !await _db.Departments.AnyAsync(r => r.Id == req.Value, ct)) throw new ValidationFailedException("Подразделение не найдено");
                        if (e.DepartmentId != req.Value) { e.DepartmentId = req.Value; await AddBulkHistory(e, "Массовая смена подразделения", ct); }
                        break;
                    case "changePosition":
                        if (req.Value is not null && !await _db.Positions.AnyAsync(r => r.Id == req.Value, ct)) throw new ValidationFailedException("Должность не найдена");
                        if (e.PositionId != req.Value) { e.PositionId = req.Value; await AddBulkHistory(e, "Массовая смена должности", ct); }
                        break;
                    case "changeStatus":
                        var kind = await _db.EmployeeStatuses.Where(s => s.Id == req.Value).Select(s => (EmployeeStatusKind?)s.Kind).FirstOrDefaultAsync(ct)
                                   ?? throw new ValidationFailedException("Статус не найден");
                        if (kind is EmployeeStatusKind.Terminated or EmployeeStatusKind.Archived && await _db.Assets.AnyAsync(a => a.EmployeeId == e.Id, ct))
                            throw new ConflictException(ErrorCodes.HasDependencies, "За сотрудником числится оборудование");
                        e.StatusId = req.Value!.Value;
                        break;
                    case "archive":
                        if (await _db.Assets.AnyAsync(a => a.EmployeeId == e.Id, ct))
                            throw new ConflictException(ErrorCodes.HasDependencies, "За сотрудником числится оборудование");
                        e.StatusId = await DefaultStatusAsync(EmployeeStatusKind.Archived, ct);
                        break;
                    default:
                        throw new ValidationFailedException("Неизвестное действие");
                }
                ok++;
            }
            catch (BusinessException ex)
            {
                errors.Add(new BulkError(e.Id, e.FullName, ex.Code, ex.Message));
                _db.Employees.Entry(e).State = EntityState.Unchanged;
            }
        }
        await _db.SaveChangesAsync(ct);
        return new BulkResult(ok, errors);
    }

    private async Task AddBulkHistory(Employee e, string reason, CancellationToken ct)
    {
        var now = _clock.UtcNow;
        await CloseOrgHistoryAsync(e.Id, now, ct);
        _db.EmployeeOrgHistory.Add(await BuildOrgHistoryAsync(e, now, reason, ct));
    }

    public async Task<IReadOnlyList<TimelineItem>> TimelineAsync(Guid id, CancellationToken ct)
    {
        await EnsureVisibleAsync(id, ct);
        var items = new List<TimelineItem>();
        var emp = await _db.Employees.AsNoTracking().Where(e => e.Id == id).Select(e => new { e.HireDate, e.TerminationDate, e.CreatedAt }).FirstAsync(ct);
        if (emp.HireDate is not null)
            items.Add(new TimelineItem(emp.HireDate.Value.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc), emp.CreatedAt, "hire", "Приём на работу", null, null, null, Color: "green"));
        foreach (var h in await OrgHistoryAsync(id, ct))
            if (h.Reason != "Приём на работу")
                items.Add(new TimelineItem(h.EffectiveFrom, h.RecordedAt, "org", h.Reason ?? "Изменение оргструктуры",
                    string.Join(", ", new[] { h.Department, h.Position, h.Region, h.Location }.Where(x => x is not null)), null, null));

        var assignments = await _db.Assignments.AsNoTracking().Where(a => a.EmployeeId == id)
            .Select(a => new { a.EffectiveFrom, a.EffectiveTo, a.RecordedAt, a.IsCancelled, a.Asset!.InventoryNumber, a.Asset.Name, a.AssetId, a.Batch!.Number, a.CloseReason }).ToListAsync(ct);
        foreach (var a in assignments)
        {
            items.Add(new TimelineItem(a.EffectiveFrom, a.RecordedAt, "assign", $"Выдано: {a.InventoryNumber}", $"{a.Name} ({a.Number})",
                $"/assets/{a.AssetId}", null, (a.RecordedAt - a.EffectiveFrom).TotalHours > 24, a.IsCancelled, "blue"));
        }
        var returns = await _db.AssetReturns.AsNoTracking().Where(a => a.EmployeeId == id)
            .Select(a => new { a.EffectiveAt, a.RecordedAt, a.IsCancelled, a.Asset!.InventoryNumber, a.Asset.Name, a.AssetId, a.Batch!.Number }).ToListAsync(ct);
        foreach (var r in returns)
            items.Add(new TimelineItem(r.EffectiveAt, r.RecordedAt, "return", $"Возвращено: {r.InventoryNumber}", $"{r.Name} ({r.Number})",
                $"/assets/{r.AssetId}", null, (r.RecordedAt - r.EffectiveAt).TotalHours > 24, r.IsCancelled, "orange"));
        var licenses = await _db.LicenseAssignments.AsNoTracking().Where(l => l.EmployeeId == id)
            .Select(l => new { l.AssignedAt, l.RevokedAt, l.RecordedAt, l.License!.Name, l.LicenseId }).ToListAsync(ct);
        foreach (var l in licenses)
        {
            items.Add(new TimelineItem(l.AssignedAt, l.RecordedAt, "license", $"Назначена лицензия: {l.Name}", null, $"/licenses/{l.LicenseId}", null, Color: "purple"));
            if (l.RevokedAt is not null) items.Add(new TimelineItem(l.RevokedAt.Value, null, "license-revoke", $"Отозвана лицензия: {l.Name}", null, $"/licenses/{l.LicenseId}", null, Color: "gray"));
        }
        var accesses = await _db.EmployeeAccesses.AsNoTracking().Where(a => a.EmployeeId == id)
            .Select(a => new { a.GrantedAt, a.RevokedAt, a.RecordedAt, System = a.AccessSystem!.Name, a.Username }).ToListAsync(ct);
        foreach (var a in accesses)
        {
            items.Add(new TimelineItem(a.GrantedAt, a.RecordedAt, "access", $"Выдан доступ: {a.System}", a.Username, null, null, Color: "cyan"));
            if (a.RevokedAt is not null) items.Add(new TimelineItem(a.RevokedAt.Value, null, "access-revoke", $"Отозван доступ: {a.System}", a.Username, null, null, Color: "gray"));
        }
        var docs = await _db.GeneratedDocuments.AsNoTracking().Where(d => d.EmployeeId == id)
            .Select(d => new { d.CreatedAt, d.Number, d.Title, d.Id, d.IsVoided }).ToListAsync(ct);
        foreach (var d in docs)
            items.Add(new TimelineItem(d.CreatedAt, d.CreatedAt, "document", $"Документ {d.Number}", d.Title, $"/documents?id={d.Id}", null, IsCancelled: d.IsVoided));
        var checklists = await _db.EmployeeChecklists.AsNoTracking().Where(c => c.EmployeeId == id)
            .Select(c => new { c.StartedAt, c.CompletedAt, c.Title, c.Kind }).ToListAsync(ct);
        foreach (var c in checklists)
        {
            items.Add(new TimelineItem(c.StartedAt, c.StartedAt, "checklist", $"Начат {(c.Kind == ChecklistKind.Onboarding ? "онбординг" : "офбординг")}", c.Title, null, null));
            if (c.CompletedAt is not null) items.Add(new TimelineItem(c.CompletedAt.Value, c.CompletedAt, "checklist-done", $"Завершён {(c.Kind == ChecklistKind.Onboarding ? "онбординг" : "офбординг")}", c.Title, null, null, Color: "green"));
        }
        if (emp.TerminationDate is not null)
            items.Add(new TimelineItem(emp.TerminationDate.Value.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc), null, "terminate", "Увольнение", null, null, null, Color: "red"));
        return items.OrderByDescending(i => i.Date).ToList();
    }

    public async Task<IReadOnlyList<Assets.AssetListItem>> CurrentAssetsAsync(Guid id, Assets.AssetService assets, CancellationToken ct)
    {
        await EnsureVisibleAsync(id, ct);
        return await _db.Assets.AsNoTracking().Where(a => a.EmployeeId == id).OrderBy(a => a.InventoryNumber).Select(assets.ListProjection()).ToListAsync(ct);
    }
}
