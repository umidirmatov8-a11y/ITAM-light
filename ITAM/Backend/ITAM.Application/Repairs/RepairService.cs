using System.ComponentModel.DataAnnotations;
using System.Linq.Expressions;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Domain.Temporal;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Repairs;

public sealed class RepairQuery : PagedRequest
{
    public Guid? StatusId { get; set; }
    public RepairStage? Stage { get; set; }
    public Guid? AssetId { get; set; }
    public Guid? ServiceCenterId { get; set; }
    public Guid? RegionId { get; set; }
    public bool? OpenOnly { get; set; }
    public bool? Overdue { get; set; }
    public DateTime? From { get; set; }
    public DateTime? To { get; set; }
}

public sealed class RepairInput
{
    [Required] public Guid AssetId { get; set; }
    public DateTime? OpenedAt { get; set; }
    [Required, MaxLength(4000)] public string Problem { get; set; } = string.Empty;
    [MaxLength(4000)] public string? Diagnosis { get; set; }
    [MaxLength(4000)] public string? RepairDescription { get; set; }
    [MaxLength(4000)] public string? Parts { get; set; }
    public Guid? ServiceCenterId { get; set; }
    public DateTime? SentAt { get; set; }
    public DateOnly? ExpectedReturnDate { get; set; }
    [MaxLength(256)] public string? Technician { get; set; }
    [Range(0, 999999999999)] public decimal? Cost { get; set; }
    [MaxLength(8)] public string? Currency { get; set; }
    public bool IsWarranty { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public Dictionary<string, JsonElement>? CustomFields { get; set; }
    public uint? Version { get; set; }
}

public sealed class RepairStatusRequest
{
    [Required] public Guid StatusId { get; set; }
    public DateTime? ChangedAt { get; set; }
    [MaxLength(2000)] public string? Comment { get; set; }
    /// <summary>Status of the asset after the repair is returned (default: previous state).</summary>
    public Guid? ReturnStatusId { get; set; }
}

public sealed record RepairListItem(Guid Id, string Number, Guid AssetId, string InventoryNumber, string AssetName, Guid StatusId, string StatusName,
    string? StatusColor, RepairStage Stage, DateTime OpenedAt, DateTime? SentAt, string? ServiceCenterName, string Problem, decimal? Cost, string? Currency,
    bool IsWarranty, DateOnly? ExpectedReturnDate, DateTime? ActualReturnAt, string? Technician, string? RegionName, bool IsOverdue);

public sealed record RepairDto(Guid Id, string Number, Guid AssetId, string InventoryNumber, string AssetName, string? SerialNumber,
    Guid StatusId, string StatusName, string? StatusColor, RepairStage Stage, DateTime OpenedAt, DateTime RecordedAt, DateTime? SentAt,
    Guid? ServiceCenterId, string? ServiceCenterName, string Problem, string? Diagnosis, string? RepairDescription, string? Parts,
    decimal? Cost, string? Currency, bool IsWarranty, DateOnly? ExpectedReturnDate, DateTime? ActualReturnAt, string? Technician, string? Comment,
    Guid? EmployeeId, string? EmployeeName, JsonElement? CustomFields, uint Version, IReadOnlyList<RepairHistoryDto> History);

public sealed record RepairHistoryDto(Guid Id, string StatusName, DateTime ChangedAt, DateTime RecordedAt, string? RecordedByName, string? Comment);

public sealed class RepairService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly AssetTemporalStore _temporal;
    private readonly INumberingService _numbering;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly ICustomFieldValidator _customFields;
    private readonly ISnapshotService _snapshots;

    public RepairService(IAppDbContext db, IRegionScope scope, ICurrentUser user, IClock clock, AssetTemporalStore temporal,
        INumberingService numbering, IAuditService audit, AuditContext auditCtx, ICustomFieldValidator customFields, ISnapshotService snapshots)
    {
        _db = db; _scope = scope; _user = user; _clock = clock; _temporal = temporal; _numbering = numbering; _audit = audit;
        _auditCtx = auditCtx; _customFields = customFields; _snapshots = snapshots;
    }

    private static readonly Dictionary<string, Expression<Func<Repair, object?>>> Sorts = new()
    {
        ["number"] = r => r.Number,
        ["openedAt"] = r => r.OpenedAt,
        ["statusName"] = r => r.Status!.SortOrder,
        ["inventoryNumber"] = r => r.Asset!.InventoryNumber,
        ["cost"] = r => r.Cost,
        ["expectedReturnDate"] = r => r.ExpectedReturnDate,
    };

    public IQueryable<Repair> Visible() => _scope.Apply(_db.Repairs.AsQueryable(), r => r.Asset!.RegionId);

    public IQueryable<Repair> Filtered(RepairQuery q)
    {
        var query = Visible().AsNoTracking();
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(r => EF.Functions.ILike(r.Number, like) || EF.Functions.ILike(r.Asset!.InventoryNumber, like)
                                     || EF.Functions.ILike(r.Problem, like) || (r.Asset.SerialNumber != null && EF.Functions.ILike(r.Asset.SerialNumber, like)));
        }
        if (q.StatusId is not null) query = query.Where(r => r.StatusId == q.StatusId);
        if (q.Stage is not null) query = query.Where(r => r.Status!.Stage == q.Stage);
        if (q.AssetId is not null) query = query.Where(r => r.AssetId == q.AssetId);
        if (q.ServiceCenterId is not null) query = query.Where(r => r.ServiceCenterId == q.ServiceCenterId);
        if (q.RegionId is not null) query = query.Where(r => r.Asset!.RegionId == q.RegionId);
        if (q.OpenOnly == true) query = query.Where(r => r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled);
        if (q.Overdue == true)
        {
            var today = DateOnly.FromDateTime(_clock.UtcNow);
            query = query.Where(r => r.ExpectedReturnDate < today && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled);
        }
        if (q.From is not null) query = query.Where(r => r.OpenedAt >= q.From);
        if (q.To is not null) query = query.Where(r => r.OpenedAt <= q.To);
        return query;
    }

    public async Task<PagedResult<RepairListItem>> ListAsync(RepairQuery q, CancellationToken ct)
    {
        var today = DateOnly.FromDateTime(_clock.UtcNow);
        return await Filtered(q).SortBy(q, Sorts, "openedAt").ToPagedAsync(q, r => new RepairListItem(r.Id, r.Number, r.AssetId,
            r.Asset!.InventoryNumber, r.Asset.Name, r.StatusId, r.Status!.Name, r.Status.Color, r.Status.Stage, r.OpenedAt, r.SentAt,
            r.ServiceCenter != null ? r.ServiceCenter.Name : null, r.Problem, r.Cost, r.Currency, r.IsWarranty, r.ExpectedReturnDate, r.ActualReturnAt,
            r.Technician, r.Asset.Region != null ? r.Asset.Region.Name : null,
            r.ExpectedReturnDate < today && r.Status.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled), ct);
    }

    public async Task<RepairDto> GetAsync(Guid id, CancellationToken ct)
    {
        var r = await Visible().AsNoTracking().Include(x => x.Asset).Include(x => x.Status).Include(x => x.ServiceCenter).Include(x => x.History)
                    .FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Ремонт", id);
        var employee = r.EmployeeId is null ? null : await _db.Employees.IgnoreQueryFilters().Where(e => e.Id == r.EmployeeId).Select(e => e.FullName).FirstOrDefaultAsync(ct);
        return new RepairDto(r.Id, r.Number, r.AssetId, r.Asset!.InventoryNumber, r.Asset.Name, r.Asset.SerialNumber, r.StatusId, r.Status!.Name, r.Status.Color,
            r.Status.Stage, r.OpenedAt, r.RecordedAt, r.SentAt, r.ServiceCenterId, r.ServiceCenter?.Name, r.Problem, r.Diagnosis, r.RepairDescription, r.Parts,
            r.Cost, r.Currency, r.IsWarranty, r.ExpectedReturnDate, r.ActualReturnAt, r.Technician, r.Comment, r.EmployeeId, employee,
            Json.ToElement(r.CustomFields), r.Version,
            r.History.OrderByDescending(h => h.ChangedAt).ThenByDescending(h => h.RecordedAt)
                .Select(h => new RepairHistoryDto(h.Id, h.StatusName, h.ChangedAt, h.RecordedAt, h.RecordedByName, h.Comment)).ToList());
    }

    private async Task<RepairStatus> StatusForStageAsync(RepairStage stage, CancellationToken ct)
        => await _db.RepairStatuses.Where(s => s.Stage == stage && !s.IsArchived).OrderByDescending(s => s.IsSystem).ThenBy(s => s.SortOrder).FirstOrDefaultAsync(ct)
           ?? throw new BusinessException("STATUS_NOT_CONFIGURED", $"Не настроен статус ремонта {stage}");

    public async Task<RepairDto> CreateAsync(RepairInput input, CancellationToken ct)
    {
        var asset = await _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId).FirstOrDefaultAsync(a => a.Id == input.AssetId, ct)
                    ?? throw new NotFoundException("Актив", input.AssetId);
        if (await _db.Repairs.AnyAsync(r => r.AssetId == asset.Id && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled, ct))
            throw new ConflictException(ErrorCodes.AssetInRepair, "По активу уже есть открытый ремонт");
        var openedAt = input.OpenedAt?.ToUniversalTime() ?? _clock.UtcNow;

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var backdated = await _temporal.CheckEffectiveDateAsync(asset.Id, openedAt, ct);
        var before = await _temporal.StateAtAsync(asset.Id, openedAt, ct);
        var created = await StatusForStageAsync(input.SentAt is null ? RepairStage.Created : RepairStage.Sent, ct);
        var repair = new Repair
        {
            Number = await _numbering.NextAsync(c => c.RepairFormat, "repair", ct: ct),
            AssetId = asset.Id,
            StatusId = created.Id,
            OpenedAt = openedAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = before.EmployeeId,
            PreviousStatusId = before.StatusId,
            RegionId = asset.RegionId,
            AssetSnapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
        };
        ApplyInput(repair, input);
        repair.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Repair, null, input.CustomFields, ct);
        _db.Repairs.Add(repair);

        var inRepair = await _temporal.DefaultStatusAsync(AssetStateKind.InRepair, ct);
        var evt = _temporal.NewEvent(asset, AssetEventType.RepairOpened, openedAt, new AssetStateDelta { StatusId = inRepair },
            OperationType.Repair, repair.Id, null, $"Отправлен в ремонт ({repair.Number})",
            new { repair = repair.Number, problem = repair.Problem, serviceCenter = await SupplierNameAsync(repair.ServiceCenterId, ct) });
        await _temporal.ApplyAsync(asset, evt, null, ct);
        repair.OpenEventId = evt.Id;
        AddHistory(repair, created, openedAt, "Ремонт создан");
        using (_auditCtx.Suppress())
        {
            _audit.Log("asset.repair.open", nameof(Asset), asset.Id, asset.InventoryNumber,
                new { status = await _snapshots.StatusNameAsync(before.StatusId, ct) },
                new { status = "В ремонте", repair = repair.Number, backdated }, input.Problem);
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        return await GetAsync(repair.Id, ct);
    }

    /// <summary>Used by the return operation: the return event already moved the asset into repair.</summary>
    public async Task<Repair> CreateFromReturnAsync(Asset asset, Guid? employeeId, Guid? previousStatusId, string? problem, DateTime openedAt, Guid openEventId, CancellationToken ct)
    {
        var created = await StatusForStageAsync(RepairStage.Created, ct);
        var repair = new Repair
        {
            Number = await _numbering.NextAsync(c => c.RepairFormat, "repair", ct: ct),
            AssetId = asset.Id,
            StatusId = created.Id,
            OpenedAt = openedAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = employeeId,
            PreviousStatusId = previousStatusId,
            RegionId = asset.RegionId,
            Problem = string.IsNullOrWhiteSpace(problem) ? "Неисправность выявлена при возврате" : problem,
            OpenEventId = openEventId,
            AssetSnapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
        };
        _db.Repairs.Add(repair);
        AddHistory(repair, created, openedAt, "Создан при возврате оборудования");
        return repair;
    }

    private void AddHistory(Repair repair, RepairStatus status, DateTime changedAt, string? comment)
        => _db.RepairStatusHistory.Add(new RepairStatusHistory
        {
            RepairId = repair.Id,
            StatusId = status.Id,
            StatusName = status.Name,
            ChangedAt = changedAt,
            RecordedAt = _clock.UtcNow,
            RecordedById = _user.UserId,
            RecordedByName = _user.DisplayName ?? _user.UserName,
            Comment = comment,
        });

    private static void ApplyInput(Repair r, RepairInput i)
    {
        r.Problem = i.Problem.Trim();
        r.Diagnosis = i.Diagnosis;
        r.RepairDescription = i.RepairDescription;
        r.Parts = i.Parts;
        r.ServiceCenterId = i.ServiceCenterId;
        r.SentAt = i.SentAt?.ToUniversalTime();
        r.ExpectedReturnDate = i.ExpectedReturnDate;
        r.Technician = i.Technician;
        r.Cost = i.Cost;
        r.Currency = i.Currency;
        r.IsWarranty = i.IsWarranty;
        r.Comment = i.Comment;
    }

    private async Task<string?> SupplierNameAsync(Guid? id, CancellationToken ct)
        => id is null ? null : await _db.Suppliers.Where(s => s.Id == id).Select(s => s.Name).FirstOrDefaultAsync(ct);

    public async Task<RepairDto> UpdateAsync(Guid id, RepairInput input, CancellationToken ct)
    {
        var r = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Ремонт", id);
        if (input.Version is not null && input.Version != r.Version)
            throw new ConflictException(ErrorCodes.ConcurrentModification, "Ремонт был изменён другим пользователем. Обновите страницу.");
        ApplyInput(r, input);
        r.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Repair, null, input.CustomFields, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<RepairDto> ChangeStatusAsync(Guid id, RepairStatusRequest req, CancellationToken ct)
    {
        var r = await Visible().Include(x => x.Status).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Ремонт", id);
        if (r.Status!.IsClosed) throw new BusinessException("REPAIR_CLOSED", "Ремонт уже закрыт");
        var status = await _db.RepairStatuses.FirstOrDefaultAsync(s => s.Id == req.StatusId && !s.IsArchived, ct) ?? throw new NotFoundException("Статус ремонта", req.StatusId);
        var changedAt = req.ChangedAt?.ToUniversalTime() ?? _clock.UtcNow;
        if (changedAt < r.OpenedAt) throw new BusinessException(ErrorCodes.TemporalConflict, "Дата смены статуса раньше даты открытия ремонта");
        if (changedAt > _clock.UtcNow.AddMinutes(5)) throw new BusinessException(ErrorCodes.FutureDate, "Дата не может быть в будущем");

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var oldStatus = r.Status.Name;
        r.StatusId = status.Id;
        if (status.Stage == RepairStage.Sent && r.SentAt is null) r.SentAt = changedAt;
        AddHistory(r, status, changedAt, req.Comment);
        var asset = await _db.Assets.FirstAsync(a => a.Id == r.AssetId, ct);

        if (status.Stage is RepairStage.Returned or RepairStage.Cancelled)
        {
            if (status.Stage == RepairStage.Returned) r.ActualReturnAt = changedAt;
            var kinds = await _temporal.KindsAsync(ct);
            var state = await _temporal.StateAtAsync(asset.Id, changedAt, ct);
            if (state.Kind == AssetStateKind.InRepair)
            {
                await _temporal.CheckEffectiveDateAsync(asset.Id, changedAt, ct);
                Guid target;
                if (req.ReturnStatusId is not null)
                {
                    var k = kinds(req.ReturnStatusId.Value);
                    if (k is AssetStateKind.Assigned && state.EmployeeId is null || k is AssetStateKind.InRepair)
                        throw new ValidationFailedException("Недопустимый статус после ремонта");
                    target = req.ReturnStatusId.Value;
                }
                else if (state.EmployeeId is not null) target = await _temporal.DefaultStatusAsync(AssetStateKind.Assigned, ct);
                else if (r.PreviousStatusId is { } prev && kinds(prev) is AssetStateKind.InStock or AssetStateKind.Reserved) target = prev;
                else target = await _temporal.DefaultStatusAsync(AssetStateKind.InStock, ct);
                r.ReturnStatusId = target;
                var evt = _temporal.NewEvent(asset, AssetEventType.RepairClosed, changedAt, new AssetStateDelta { StatusId = target },
                    OperationType.Repair, r.Id, null,
                    status.Stage == RepairStage.Returned ? $"Возвращён из ремонта ({r.Number})" : $"Ремонт отменён ({r.Number})",
                    new { repair = r.Number, cost = r.Cost, diagnosis = r.Diagnosis, description = r.RepairDescription });
                await _temporal.ApplyAsync(asset, evt, null, ct);
                r.CloseEventId = evt.Id;
            }
        }
        else
        {
            _temporal.AddInfoEvent(asset.Id, AssetEventType.RepairUpdated, changedAt, $"Ремонт {r.Number}: {status.Name}", new { comment = req.Comment }, r.Id);
        }
        using (_auditCtx.Suppress())
        {
            _audit.Log("repair.status", nameof(Repair), r.Id, r.Number, new { status = oldStatus }, new { status = status.Name, changedAt }, req.Comment);
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task<IReadOnlyList<RepairListItem>> ForAssetAsync(Guid assetId, CancellationToken ct)
        => (await ListAsync(new RepairQuery { AssetId = assetId, PageSize = 500 }, ct)).Items;
}
