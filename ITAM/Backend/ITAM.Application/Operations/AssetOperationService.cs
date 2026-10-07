using ITAM.Application.Common;
using ITAM.Application.Repairs;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Domain.Temporal;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace ITAM.Application.Operations;

/// <summary>
/// Issue / return / transfer / status operations. Every operation is an act (OperationBatch) with lines, produces temporal
/// events (EffectiveAt + RecordedAt), is validated by the temporal engine (backdated inserts included) and runs in one
/// transaction guarded by optimistic concurrency on each asset row.
/// </summary>
public sealed class AssetOperationService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly AssetTemporalStore _temporal;
    private readonly INumberingService _numbering;
    private readonly ISnapshotService _snapshots;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly RepairService _repairs;
    private readonly IDocumentGenerator _documents;
    private readonly ILogger<AssetOperationService> _log;

    public AssetOperationService(IAppDbContext db, IRegionScope scope, ICurrentUser user, IClock clock, AssetTemporalStore temporal,
        INumberingService numbering, ISnapshotService snapshots, IAuditService audit, AuditContext auditCtx, RepairService repairs,
        IDocumentGenerator documents, ILogger<AssetOperationService> log)
    {
        _db = db; _scope = scope; _user = user; _clock = clock; _temporal = temporal; _numbering = numbering; _snapshots = snapshots;
        _audit = audit; _auditCtx = auditCtx; _repairs = repairs; _documents = documents; _log = log;
    }

    private async Task<List<Asset>> LoadAssetsAsync(IEnumerable<Guid> ids, CancellationToken ct)
    {
        var list = ids.Distinct().ToList();
        var assets = await _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId).Where(a => list.Contains(a.Id)).ToListAsync(ct);
        var missing = list.Except(assets.Select(a => a.Id)).ToList();
        if (missing.Count > 0) throw new NotFoundException("Актив", string.Join(", ", missing));
        return assets.OrderBy(a => a.InventoryNumber).ToList();
    }

    private async Task<Employee> LoadEmployeeAsync(Guid id, bool requireActive, CancellationToken ct)
    {
        var e = await _scope.Apply(_db.Employees.Include(x => x.Status).AsQueryable(), x => x.RegionId).FirstOrDefaultAsync(x => x.Id == id, ct)
                ?? throw new NotFoundException("Сотрудник", id);
        if (requireActive && e.Status?.Kind is EmployeeStatusKind.Terminated or EmployeeStatusKind.Archived)
            throw new BusinessException("EMPLOYEE_INACTIVE", $"Сотрудник {e.FullName} уволен или в архиве — выдача невозможна");
        return e;
    }

    private DateTime Effective(DateTime? at) => at?.ToUniversalTime() ?? _clock.UtcNow;

    private async Task<Guid?> TryGenerateAsync(bool generate, Guid batchId, Guid? templateId, CancellationToken ct)
    {
        if (!generate) return null;
        if (!_user.Has(Permissions.DocumentsGenerate)) throw new ForbiddenException("Нет права на формирование документов");
        try
        {
            return await _documents.GenerateAsync(DocumentSources.OperationBatch, batchId, templateId, ct);
        }
        catch (BusinessException ex)
        {
            // The operation is already committed; the document can be generated later from the operation card.
            _log.LogWarning("Document generation failed for batch {Batch}: {Message}", batchId, ex.Message);
            return null;
        }
    }

    // ===================================================================== ISSUE

    public async Task<OperationResult> IssueAsync(IssueRequest req, CancellationToken ct)
    {
        var employee = await LoadEmployeeAsync(req.EmployeeId, true, ct);
        var assets = await LoadAssetsAsync(req.AssetIds, ct);
        var effectiveAt = Effective(req.EffectiveAt);
        var assignedStatus = await _temporal.DefaultStatusAsync(AssetStateKind.Assigned, ct);
        var empSnapshot = await _snapshots.EmployeeAsync(employee.Id, ct);
        var responsible = await _snapshots.EmployeeAsync(req.ResponsibleEmployeeId, ct);
        var location = req.LocationId ?? employee.LocationId;
        var locationName = await _snapshots.LocationNameAsync(location, ct);
        var returnedAt = req.ReturnedAt?.ToUniversalTime();
        if (returnedAt is not null)
        {
            if (returnedAt <= effectiveAt) throw new ValidationFailedException("Дата возврата должна быть позже даты выдачи");
            if (returnedAt > _clock.UtcNow.AddMinutes(5)) throw new BusinessException(ErrorCodes.FutureDate, "Дата возврата не может быть в будущем");
            if (!_user.Has(Permissions.AssetsBackdate)) throw new ForbiddenException("Историческая выдача требует права assets.backdate");
        }
        var inStock = returnedAt is null ? Guid.Empty : await _temporal.DefaultStatusAsync(AssetStateKind.InStock, ct);

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        OperationBatch? returnBatch = null;
        if (returnedAt is not null)
        {
            returnBatch = new OperationBatch
            {
                Number = await _numbering.NextAsync(c => c.ReturnFormat, "return", ct: ct),
                Type = OperationType.Return,
                EffectiveAt = returnedAt.Value,
                RecordedAt = _clock.UtcNow,
                EmployeeId = employee.Id,
                ResponsibleEmployeeId = req.ResponsibleEmployeeId,
                RegionId = employee.RegionId,
                Comment = "Историческая запись: возврат по выдаче",
                EmployeeSnapshot = Json.Serialize(empSnapshot),
                IsBackdated = true,
            };
            _db.OperationBatches.Add(returnBatch);
        }
        var batch = new OperationBatch
        {
            Number = await _numbering.NextAsync(c => c.IssueFormat, "issue", ct: ct),
            Type = OperationType.Issue,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = employee.Id,
            ResponsibleEmployeeId = req.ResponsibleEmployeeId,
            RegionId = employee.RegionId,
            Comment = req.Comment,
            EmployeeSnapshot = Json.Serialize(empSnapshot),
            ResponsibleSnapshot = Json.SerializeOrNull(responsible),
        };
        _db.OperationBatches.Add(batch);

        using (_auditCtx.Suppress())
        {
            foreach (var asset in assets)
            {
                batch.IsBackdated |= await _temporal.CheckEffectiveDateAsync(asset.Id, effectiveAt, ct);
                var before = await _temporal.StateAtAsync(asset.Id, effectiveAt, ct);
                var assignment = new Assignment
                {
                    BatchId = batch.Id,
                    AssetId = asset.Id,
                    EmployeeId = employee.Id,
                    EffectiveFrom = effectiveAt,
                    RecordedAt = _clock.UtcNow,
                    RecordedById = _user.UserId,
                    LocationId = location,
                    ResponsibleEmployeeId = req.ResponsibleEmployeeId,
                    Condition = req.Condition,
                    Accessories = req.Accessories,
                    Comment = req.Comment,
                    ExpectedReturnDate = req.ExpectedReturnDate,
                    EmployeeSnapshot = batch.EmployeeSnapshot,
                    AssetSnapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
                };
                _db.Assignments.Add(assignment);
                var evt = _temporal.NewEvent(asset, AssetEventType.Assigned, effectiveAt, new AssetStateDelta
                {
                    StatusId = assignedStatus,
                    SetEmployee = true, EmployeeId = employee.Id,
                    SetDepartment = true, DepartmentId = employee.DepartmentId,
                    SetRegion = true, RegionId = employee.RegionId,
                    SetLocation = location is not null, LocationId = location,
                }, OperationType.Issue, assignment.Id, batch.Id, $"Выдан: {employee.FullName} ({batch.Number})", new
                {
                    batch = batch.Number, employee = empSnapshot, location = locationName, condition = req.Condition.ToString(),
                    accessories = req.Accessories, comment = req.Comment, responsible = responsible?.FullName, expectedReturn = req.ExpectedReturnDate
                });
                if (returnBatch is not null)
                {
                    var ret = new AssetReturn
                    {
                        BatchId = returnBatch.Id, AssetId = asset.Id, EmployeeId = employee.Id, AssignmentId = assignment.Id, EffectiveAt = returnedAt!.Value,
                        RecordedAt = _clock.UtcNow, RecordedById = _user.UserId, Condition = req.Condition, ResultStatusId = inStock, LocationId = req.ReturnLocationId,
                        Comment = returnBatch.Comment, EmployeeSnapshot = batch.EmployeeSnapshot, AssetSnapshot = assignment.AssetSnapshot,
                    };
                    _db.AssetReturns.Add(ret);
                    assignment.EffectiveTo = returnedAt;
                    assignment.ReturnId = ret.Id;
                    var retEvt = _temporal.NewEvent(asset, AssetEventType.Returned, returnedAt.Value, new AssetStateDelta
                    {
                        StatusId = inStock, SetEmployee = true, EmployeeId = null, ExpectedEmployeeId = employee.Id,
                        SetLocation = req.ReturnLocationId is not null, LocationId = req.ReturnLocationId,
                    }, OperationType.Return, ret.Id, returnBatch.Id, $"Возвращён от {employee.FullName} ({returnBatch.Number})",
                        new { batch = returnBatch.Number, employee = empSnapshot, historical = true });
                    await _temporal.ApplyAsync(asset, new[] { evt, retEvt }, null, ct);
                }
                else await _temporal.ApplyAsync(asset, evt, null, ct);
                asset.Condition = req.Condition;
                _audit.Log("asset.assign", nameof(Asset), asset.Id, asset.InventoryNumber,
                    new { holder = before.EmployeeId is null ? await _snapshots.LocationNameAsync(before.LocationId, ct) ?? "Склад" : null, status = await _snapshots.StatusNameAsync(before.StatusId, ct) },
                    new { holder = employee.FullName, status = "Выдан", effectiveAt, batch = batch.Number, backdated = batch.IsBackdated });
            }
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        var docId = await TryGenerateAsync(req.GenerateDocument, batch.Id, req.TemplateId, ct);
        return new OperationResult(batch.Id, batch.Number, batch.Type, assets.Count, batch.IsBackdated, docId);
    }

    // ===================================================================== RETURN

    public async Task<OperationResult> ReturnAsync(ReturnRequest req, CancellationToken ct)
    {
        var employee = await LoadEmployeeAsync(req.EmployeeId, false, ct);
        var assets = (await LoadAssetsAsync(req.Items.Select(i => i.AssetId), ct)).ToDictionary(a => a.Id);
        var effectiveAt = Effective(req.EffectiveAt);
        var kinds = await _temporal.KindsAsync(ct);
        var inStock = await _temporal.DefaultStatusAsync(AssetStateKind.InStock, ct);
        var inRepair = await _temporal.DefaultStatusAsync(AssetStateKind.InRepair, ct);
        var empSnapshot = await _snapshots.EmployeeAsync(employee.Id, ct);
        var responsible = await _snapshots.EmployeeAsync(req.ResponsibleEmployeeId, ct);
        var locationName = await _snapshots.LocationNameAsync(req.LocationId, ct);
        if (req.LocationId is not null)
        {
            var locRegion = await _db.Locations.Where(l => l.Id == req.LocationId).Select(l => (Guid?)l.RegionId).FirstOrDefaultAsync(ct)
                            ?? throw new NotFoundException("Локация", req.LocationId);
            _scope.EnsureAccess(locRegion);
        }
        var repairIds = new List<Guid>();

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var batch = new OperationBatch
        {
            Number = await _numbering.NextAsync(c => c.ReturnFormat, "return", ct: ct),
            Type = OperationType.Return,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = employee.Id,
            ResponsibleEmployeeId = req.ResponsibleEmployeeId,
            RegionId = employee.RegionId,
            Comment = req.Comment,
            EmployeeSnapshot = Json.Serialize(empSnapshot),
            ResponsibleSnapshot = Json.SerializeOrNull(responsible),
        };
        _db.OperationBatches.Add(batch);

        using (_auditCtx.Suppress())
        {
            foreach (var item in req.Items)
            {
                var asset = assets[item.AssetId];
                batch.IsBackdated |= await _temporal.CheckEffectiveDateAsync(asset.Id, effectiveAt, ct);
                var assignment = await _db.Assignments
                    .Where(a => a.AssetId == asset.Id && a.EmployeeId == employee.Id && !a.IsCancelled && a.EffectiveTo == null && a.EffectiveFrom <= effectiveAt)
                    .OrderByDescending(a => a.EffectiveFrom).FirstOrDefaultAsync(ct)
                    ?? throw new ConflictException(ErrorCodes.AssetNotAssigned,
                        $"Актив {asset.InventoryNumber} не числится за сотрудником {employee.FullName} на {effectiveAt:dd.MM.yyyy HH:mm}");

                Guid resultStatus;
                if (item.SendToRepair) resultStatus = inRepair;
                else if (item.ResultStatusId is not null)
                {
                    if (kinds(item.ResultStatusId.Value) is not (AssetStateKind.InStock or AssetStateKind.Reserved))
                        throw new ValidationFailedException("Статус после возврата должен быть «на складе / доступен» или «резерв»");
                    resultStatus = item.ResultStatusId.Value;
                }
                else resultStatus = item.Condition == AssetCondition.Broken ? inRepair : inStock;
                var toRepair = resultStatus == inRepair;
                var before = await _temporal.StateAtAsync(asset.Id, effectiveAt, ct);

                var ret = new AssetReturn
                {
                    BatchId = batch.Id,
                    AssetId = asset.Id,
                    EmployeeId = employee.Id,
                    AssignmentId = assignment.Id,
                    EffectiveAt = effectiveAt,
                    RecordedAt = _clock.UtcNow,
                    RecordedById = _user.UserId,
                    Condition = item.Condition,
                    Accessories = item.Accessories,
                    Damage = item.Damage,
                    MissingItems = item.MissingItems,
                    Comment = req.Comment,
                    ResponsibleEmployeeId = req.ResponsibleEmployeeId,
                    ResultStatusId = resultStatus,
                    LocationId = req.LocationId,
                    EmployeeSnapshot = batch.EmployeeSnapshot,
                    AssetSnapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
                };
                _db.AssetReturns.Add(ret);
                var evt = _temporal.NewEvent(asset, AssetEventType.Returned, effectiveAt, new AssetStateDelta
                {
                    StatusId = resultStatus,
                    SetEmployee = true, EmployeeId = null,
                    SetLocation = req.LocationId is not null, LocationId = req.LocationId,
                    ExpectedEmployeeId = employee.Id,
                }, OperationType.Return, ret.Id, batch.Id,
                    toRepair ? $"Возвращён от {employee.FullName} в ремонт ({batch.Number})" : $"Возвращён от {employee.FullName} ({batch.Number})", new
                    {
                        batch = batch.Number, employee = empSnapshot, location = locationName, condition = item.Condition.ToString(),
                        damage = item.Damage, missing = item.MissingItems, accessories = item.Accessories, comment = req.Comment
                    });
                await _temporal.ApplyAsync(asset, evt, null, ct);
                assignment.EffectiveTo = effectiveAt;
                assignment.ReturnId = ret.Id;
                asset.Condition = item.Condition;
                if (toRepair)
                {
                    var repair = await _repairs.CreateFromReturnAsync(asset, employee.Id, before.StatusId,
                        item.RepairProblem ?? item.Damage, effectiveAt, evt.Id, ct);
                    ret.RepairId = repair.Id;
                    repairIds.Add(repair.Id);
                }
                _audit.Log("asset.return", nameof(Asset), asset.Id, asset.InventoryNumber,
                    new { holder = employee.FullName, status = "Выдан" },
                    new { holder = locationName ?? "Склад", status = await _snapshots.StatusNameAsync(resultStatus, ct), effectiveAt, batch = batch.Number, backdated = batch.IsBackdated },
                    item.Damage);
            }
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        var docId = await TryGenerateAsync(req.GenerateDocument, batch.Id, req.TemplateId, ct);
        return new OperationResult(batch.Id, batch.Number, batch.Type, req.Items.Count, batch.IsBackdated, docId, repairIds);
    }

    // ===================================================================== TRANSFER

    public async Task<OperationResult> TransferAsync(TransferRequest req, CancellationToken ct)
    {
        if (req.ToEmployeeId is null && req.ToDepartmentId is null && req.ToRegionId is null && req.ToLocationId is null && !req.ClearDepartment)
            throw new ValidationFailedException("Укажите, куда перемещается актив (сотрудник, подразделение, регион или локация)");
        var assets = await LoadAssetsAsync(req.AssetIds, ct);
        var effectiveAt = Effective(req.EffectiveAt);
        var toEmployee = req.ToEmployeeId is null ? null : await LoadEmployeeAsync(req.ToEmployeeId.Value, true, ct);
        Guid? toRegion = req.ToRegionId;
        if (req.ToLocationId is not null)
        {
            var locRegion = await _db.Locations.Where(l => l.Id == req.ToLocationId).Select(l => (Guid?)l.RegionId).FirstOrDefaultAsync(ct)
                            ?? throw new NotFoundException("Локация", req.ToLocationId);
            if (toRegion is not null && toRegion != locRegion) throw new ValidationFailedException("Локация не относится к выбранному региону");
            toRegion = locRegion;
        }
        if (toRegion is null && toEmployee is not null) toRegion = toEmployee.RegionId;
        if (toRegion is not null)
        {
            _scope.EnsureAccess(toRegion);
            if (!await _db.Regions.AnyAsync(r => r.Id == toRegion, ct)) throw new NotFoundException("Регион", toRegion);
        }
        if (req.ToDepartmentId is not null && !await _db.Departments.AnyAsync(d => d.Id == req.ToDepartmentId, ct))
            throw new NotFoundException("Подразделение", req.ToDepartmentId);

        var toEmpSnapshot = await _snapshots.EmployeeAsync(toEmployee?.Id, ct);
        var responsible = await _snapshots.EmployeeAsync(req.ResponsibleEmployeeId, ct);

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var batch = new OperationBatch
        {
            Number = await _numbering.NextAsync(c => c.TransferFormat, "transfer", ct: ct),
            Type = OperationType.Transfer,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = toEmployee?.Id,
            ResponsibleEmployeeId = req.ResponsibleEmployeeId,
            RegionId = toRegion,
            Comment = req.Comment ?? req.Reason,
            EmployeeSnapshot = Json.SerializeOrNull(toEmpSnapshot),
            ResponsibleSnapshot = Json.SerializeOrNull(responsible),
        };
        _db.OperationBatches.Add(batch);

        using (_auditCtx.Suppress())
        {
            foreach (var asset in assets)
            {
                batch.IsBackdated |= await _temporal.CheckEffectiveDateAsync(asset.Id, effectiveAt, ct);
                var before = await _temporal.StateAtAsync(asset.Id, effectiveAt, ct);
                var fromSnapshot = new
                {
                    employee = (await _snapshots.EmployeeAsync(before.EmployeeId, ct))?.FullName,
                    department = await _snapshots.DepartmentNameAsync(before.DepartmentId, ct),
                    region = await _snapshots.RegionNameAsync(before.RegionId, ct),
                    location = await _snapshots.LocationNameAsync(before.LocationId, ct),
                };
                var delta = new AssetStateDelta();
                var transfer = new AssetTransfer
                {
                    BatchId = batch.Id,
                    AssetId = asset.Id,
                    EffectiveAt = effectiveAt,
                    RecordedAt = _clock.UtcNow,
                    RecordedById = _user.UserId,
                    FromEmployeeId = before.EmployeeId,
                    FromDepartmentId = before.DepartmentId,
                    FromRegionId = before.RegionId,
                    FromLocationId = before.LocationId,
                    ResponsibleEmployeeId = req.ResponsibleEmployeeId,
                    Reason = req.Reason,
                    Comment = req.Comment,
                };
                if (toEmployee is not null)
                {
                    if (before.EmployeeId is null)
                        throw new ConflictException(ErrorCodes.AssetNotAssigned, $"Актив {asset.InventoryNumber} не выдан сотруднику — используйте операцию «Выдать»");
                    if (before.EmployeeId == toEmployee.Id)
                        throw new ValidationFailedException($"Актив {asset.InventoryNumber} уже числится за {toEmployee.FullName}");
                    delta.SetEmployee = true;
                    delta.EmployeeId = toEmployee.Id;
                    delta.ExpectedEmployeeId = before.EmployeeId;
                    delta.SetDepartment = true;
                    delta.DepartmentId = req.ToDepartmentId ?? toEmployee.DepartmentId;
                    delta.SetLocation = true;
                    delta.LocationId = req.ToLocationId ?? toEmployee.LocationId;

                    var old = await _db.Assignments.Where(a => a.AssetId == asset.Id && a.EmployeeId == before.EmployeeId && !a.IsCancelled && a.EffectiveTo == null)
                        .FirstOrDefaultAsync(ct) ?? throw new ConflictException(ErrorCodes.AssetNotAssigned, $"Не найдена активная выдача актива {asset.InventoryNumber}");
                    old.EffectiveTo = effectiveAt;
                    old.CloseReason = $"Передан сотруднику {toEmployee.FullName} ({batch.Number})";
                    var assignment = new Assignment
                    {
                        BatchId = batch.Id,
                        AssetId = asset.Id,
                        EmployeeId = toEmployee.Id,
                        EffectiveFrom = effectiveAt,
                        RecordedAt = _clock.UtcNow,
                        RecordedById = _user.UserId,
                        LocationId = delta.LocationId,
                        ResponsibleEmployeeId = req.ResponsibleEmployeeId,
                        Condition = asset.Condition,
                        Comment = req.Comment,
                        EmployeeSnapshot = batch.EmployeeSnapshot,
                        AssetSnapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
                    };
                    _db.Assignments.Add(assignment);
                    transfer.ClosedAssignmentId = old.Id;
                    transfer.NewAssignmentId = assignment.Id;
                }
                else
                {
                    if (req.ToDepartmentId is not null || req.ClearDepartment) { delta.SetDepartment = true; delta.DepartmentId = req.ToDepartmentId; }
                    if (req.ToLocationId is not null) { delta.SetLocation = true; delta.LocationId = req.ToLocationId; }
                }
                if (toRegion is not null) { delta.SetRegion = true; delta.RegionId = toRegion; }

                transfer.ToEmployeeId = delta.SetEmployee ? delta.EmployeeId : before.EmployeeId;
                transfer.ToDepartmentId = delta.SetDepartment ? delta.DepartmentId : before.DepartmentId;
                transfer.ToRegionId = delta.SetRegion ? delta.RegionId : before.RegionId;
                transfer.ToLocationId = delta.SetLocation ? delta.LocationId : before.LocationId;
                var toSnapshot = new
                {
                    employee = (await _snapshots.EmployeeAsync(transfer.ToEmployeeId, ct))?.FullName,
                    department = await _snapshots.DepartmentNameAsync(transfer.ToDepartmentId, ct),
                    region = await _snapshots.RegionNameAsync(transfer.ToRegionId, ct),
                    location = await _snapshots.LocationNameAsync(transfer.ToLocationId, ct),
                };
                transfer.Snapshot = Json.Serialize(new { from = fromSnapshot, to = toSnapshot });
                _db.AssetTransfers.Add(transfer);

                var description = toEmployee is not null
                    ? $"Передан: {fromSnapshot.employee} → {toEmployee.FullName} ({batch.Number})"
                    : $"Перемещён: {fromSnapshot.location ?? fromSnapshot.region} → {toSnapshot.location ?? toSnapshot.department ?? toSnapshot.region} ({batch.Number})";
                var evt = _temporal.NewEvent(asset, AssetEventType.Transferred, effectiveAt, delta, OperationType.Transfer, transfer.Id, batch.Id,
                    description, new { batch = batch.Number, from = fromSnapshot, to = toSnapshot, reason = req.Reason, comment = req.Comment });
                await _temporal.ApplyAsync(asset, evt, null, ct);
                _audit.Log("asset.transfer", nameof(Asset), asset.Id, asset.InventoryNumber, fromSnapshot, toSnapshot, req.Reason);
            }
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        var docId = await TryGenerateAsync(req.GenerateDocument, batch.Id, req.TemplateId, ct);
        return new OperationResult(batch.Id, batch.Number, batch.Type, assets.Count, batch.IsBackdated, docId);
    }

    // ===================================================================== STATUS CHANGE

    public async Task<OperationResult> ChangeStatusAsync(StatusChangeRequest req, CancellationToken ct)
    {
        var assets = await LoadAssetsAsync(req.AssetIds, ct);
        var effectiveAt = Effective(req.EffectiveAt);
        var target = await _db.AssetStatuses.AsNoTracking().FirstOrDefaultAsync(s => s.Id == req.ToStatusId && !s.IsArchived, ct)
                     ?? throw new NotFoundException("Статус", req.ToStatusId);
        if (target.Kind is AssetStateKind.Reserved && req.ReservedForEmployeeId is not null)
            await LoadEmployeeAsync(req.ReservedForEmployeeId.Value, true, ct);
        var privileged = _user.Has(Permissions.AssetsReactivate);

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var batch = new OperationBatch
        {
            Number = await _numbering.NextAsync(c => c.StatusChangeFormat, "status", ct: ct),
            Type = OperationType.StatusChange,
            EffectiveAt = effectiveAt,
            RecordedAt = _clock.UtcNow,
            EmployeeId = req.ReservedForEmployeeId,
            Comment = req.Comment ?? req.Reason,
            EmployeeSignatureStatus = SignatureStatus.NotRequired,
        };
        _db.OperationBatches.Add(batch);

        using (_auditCtx.Suppress())
        {
            foreach (var asset in assets)
            {
                batch.IsBackdated |= await _temporal.CheckEffectiveDateAsync(asset.Id, effectiveAt, ct);
                var before = await _temporal.StateAtAsync(asset.Id, effectiveAt, ct);
                batch.RegionId ??= asset.RegionId;
                var change = new AssetStatusChange
                {
                    BatchId = batch.Id,
                    AssetId = asset.Id,
                    Number = batch.Number,
                    EffectiveAt = effectiveAt,
                    RecordedAt = _clock.UtcNow,
                    RecordedById = _user.UserId,
                    FromStatusId = before.StatusId ?? asset.StatusId,
                    ToStatusId = target.Id,
                    ReservedForEmployeeId = req.ReservedForEmployeeId,
                    ReservedUntil = req.ReservedUntil,
                    Reason = req.Reason,
                    Comment = req.Comment,
                    DisposalMethod = req.DisposalMethod,
                    Snapshot = Json.Serialize(await _snapshots.AssetAsync(asset.Id, ct)),
                };
                var delta = new AssetStateDelta { StatusId = target.Id, Privileged = privileged };
                if (before.EmployeeId is not null && target.Kind is AssetStateKind.Lost or AssetStateKind.Stolen)
                {
                    delta.SetEmployee = true;
                    delta.EmployeeId = null;
                    delta.ExpectedEmployeeId = before.EmployeeId;
                    var open = await _db.Assignments.FirstOrDefaultAsync(a => a.AssetId == asset.Id && a.EmployeeId == before.EmployeeId && !a.IsCancelled && a.EffectiveTo == null, ct);
                    if (open is not null)
                    {
                        open.EffectiveTo = effectiveAt;
                        open.CloseReason = $"{target.Name} ({batch.Number})";
                        change.ClosedAssignmentId = open.Id;
                    }
                }
                _db.AssetStatusChanges.Add(change);
                var evt = _temporal.NewEvent(asset, AssetEventType.StatusChanged, effectiveAt, delta, OperationType.StatusChange, change.Id, batch.Id,
                    $"Статус: {await _snapshots.StatusNameAsync(before.StatusId, ct)} → {target.Name} ({batch.Number})",
                    new { batch = batch.Number, reason = req.Reason, comment = req.Comment, reservedFor = req.ReservedForEmployeeId, reservedUntil = req.ReservedUntil, disposal = req.DisposalMethod });
                await _temporal.ApplyAsync(asset, evt, null, ct);
                _audit.Log("asset.status", nameof(Asset), asset.Id, asset.InventoryNumber,
                    new { status = await _snapshots.StatusNameAsync(before.StatusId, ct) }, new { status = target.Name, effectiveAt, batch = batch.Number }, req.Reason);
            }
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        var docId = await TryGenerateAsync(req.GenerateDocument, batch.Id, req.TemplateId, ct);
        return new OperationResult(batch.Id, batch.Number, batch.Type, assets.Count, batch.IsBackdated, docId);
    }

    // ===================================================================== CANCEL (correction)

    public async Task<BatchDto> CancelAsync(Guid batchId, CancelOperationRequest req, CancellationToken ct)
    {
        var batch = await _db.OperationBatches.Include(b => b.Assignments).Include(b => b.Returns).Include(b => b.Transfers).Include(b => b.StatusChanges)
                        .FirstOrDefaultAsync(b => b.Id == batchId, ct) ?? throw new NotFoundException("Операция", batchId);
        if (batch.IsCancelled) throw new BusinessException("ALREADY_CANCELLED", "Операция уже отменена");
        var events = await _db.AssetEvents.Where(e => e.BatchId == batchId && !e.IsCancelled).ToListAsync(ct);
        var assetIds = events.Select(e => e.AssetId).Distinct().ToList();
        var assets = await LoadAssetsAsync(assetIds, ct);

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        using (_auditCtx.Suppress())
        {
            foreach (var asset in assets)
            {
                var ids = events.Where(e => e.AssetId == asset.Id).Select(e => e.Id).ToList();
                await _temporal.ApplyAsync(asset, Array.Empty<AssetEvent>(), ids, ct);
            }
            var now = _clock.UtcNow;
            foreach (var e in events)
            {
                e.IsCancelled = true;
                e.CancelledAt = now;
                e.CancelledById = _user.UserId;
                e.CancelReason = req.Reason;
            }
            foreach (var a in batch.Assignments) a.IsCancelled = true;
            foreach (var r in batch.Returns)
            {
                r.IsCancelled = true;
                if (r.AssignmentId is not null)
                {
                    var a = await _db.Assignments.FirstAsync(x => x.Id == r.AssignmentId, ct);
                    a.EffectiveTo = null;
                    a.ReturnId = null;
                }
                if (r.RepairId is not null)
                {
                    var repair = await _db.Repairs.Include(x => x.Status).FirstAsync(x => x.Id == r.RepairId, ct);
                    if (repair.Status!.Stage != RepairStage.Created)
                        throw new ConflictException(ErrorCodes.TemporalConflict, $"По возврату уже ведётся ремонт {repair.Number} — сначала отмените ремонт");
                    var cancelled = await _db.RepairStatuses.Where(s => s.Stage == RepairStage.Cancelled).OrderByDescending(s => s.IsSystem).FirstAsync(ct);
                    repair.StatusId = cancelled.Id;
                    _db.RepairStatusHistory.Add(new RepairStatusHistory { RepairId = repair.Id, StatusId = cancelled.Id, StatusName = cancelled.Name, ChangedAt = now, RecordedAt = now, RecordedById = _user.UserId, RecordedByName = _user.UserName, Comment = "Возврат отменён: " + req.Reason });
                }
            }
            foreach (var t in batch.Transfers)
            {
                t.IsCancelled = true;
                if (t.NewAssignmentId is not null) (await _db.Assignments.FirstAsync(x => x.Id == t.NewAssignmentId, ct)).IsCancelled = true;
                if (t.ClosedAssignmentId is not null)
                {
                    var a = await _db.Assignments.FirstAsync(x => x.Id == t.ClosedAssignmentId, ct);
                    a.EffectiveTo = null;
                    a.CloseReason = null;
                }
            }
            foreach (var s in batch.StatusChanges)
            {
                s.IsCancelled = true;
                if (s.ClosedAssignmentId is not null)
                {
                    var a = await _db.Assignments.FirstAsync(x => x.Id == s.ClosedAssignmentId, ct);
                    a.EffectiveTo = null;
                    a.CloseReason = null;
                }
            }
            batch.IsCancelled = true;
            batch.CancelledAt = now;
            batch.CancelledById = _user.UserId;
            batch.CancelReason = req.Reason;
            foreach (var asset in assets)
            {
                _temporal.AddInfoEvent(asset.Id, AssetEventType.OperationCancelled, now, $"Отменена операция {batch.Number}", new { reason = req.Reason }, batch.Id);
                _audit.Log("operation.cancel", nameof(Asset), asset.Id, asset.InventoryNumber, new { batch = batch.Number, type = batch.Type.ToString() }, new { cancelled = true }, req.Reason);
            }
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        return await GetBatchAsync(batchId, ct);
    }

    // ===================================================================== QUERIES

    public IQueryable<OperationBatch> VisibleBatches() => _scope.Apply(_db.OperationBatches.AsQueryable(), b => b.RegionId);

    public async Task<PagedResult<BatchListItem>> ListBatchesAsync(BatchQuery q, CancellationToken ct)
    {
        var query = VisibleBatches().AsNoTracking();
        if (q.Type is not null) query = query.Where(b => b.Type == q.Type);
        if (q.EmployeeId is not null) query = query.Where(b => b.EmployeeId == q.EmployeeId);
        if (q.AssetId is not null) query = query.Where(b => _db.AssetEvents.Any(e => e.BatchId == b.Id && e.AssetId == q.AssetId));
        if (q.From is not null) query = query.Where(b => b.EffectiveAt >= q.From);
        if (q.To is not null) query = query.Where(b => b.EffectiveAt <= q.To);
        if (q.Backdated is not null) query = query.Where(b => b.IsBackdated == q.Backdated);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(b => EF.Functions.ILike(b.Number, like) || (b.Employee != null && EF.Functions.ILike(b.Employee.FullName, like))
                                     || _db.AssetEvents.Any(e => e.BatchId == b.Id && EF.Functions.ILike(e.Asset!.InventoryNumber, like)));
        }
        var sorts = new Dictionary<string, System.Linq.Expressions.Expression<Func<OperationBatch, object?>>>
        {
            ["effectiveAt"] = b => b.EffectiveAt, ["recordedAt"] = b => b.RecordedAt, ["number"] = b => b.Number
        };
        if (q.Sort is null) { q.Sort = "effectiveAt"; q.Order = "desc"; }
        return await query.SortBy(q, sorts, "effectiveAt").ToPagedAsync(q, b => new BatchListItem(b.Id, b.Number, b.Type, b.EffectiveAt, b.RecordedAt,
            _db.Users.Where(u => u.Id == b.CreatedById).Select(u => u.DisplayName).FirstOrDefault(),
            b.EmployeeId, b.Employee != null ? b.Employee.FullName : null,
            _db.AssetEvents.Count(e => e.BatchId == b.Id && e.AffectsState),
            string.Join(", ", _db.AssetEvents.Where(e => e.BatchId == b.Id && e.AffectsState).Select(e => e.Asset!.InventoryNumber).Take(5)),
            b.IsBackdated, b.IsCancelled, b.EmployeeSignatureStatus, b.Comment,
            _db.GeneratedDocuments.Count(d => d.SourceType == DocumentSources.OperationBatch && d.SourceId == b.Id && !d.IsVoided)), ct);
    }

    public async Task<BatchDto> GetBatchAsync(Guid id, CancellationToken ct)
    {
        var b = await VisibleBatches().AsNoTracking().Include(x => x.Employee).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Операция", id);
        var lines = new List<BatchLineDto>();
        switch (b.Type)
        {
            case OperationType.Issue:
                lines.AddRange(await _db.Assignments.AsNoTracking().Where(a => a.BatchId == id).Select(a => new BatchLineDto(a.Id, a.AssetId, a.Asset!.InventoryNumber,
                    a.Asset.Name, a.Asset.SerialNumber, a.Condition, a.Accessories, null, null, null, null, a.Comment, a.EffectiveTo, a.IsCancelled)).ToListAsync(ct));
                break;
            case OperationType.Return:
                lines.AddRange(await _db.AssetReturns.AsNoTracking().Where(a => a.BatchId == id).Select(a => new BatchLineDto(a.Id, a.AssetId, a.Asset!.InventoryNumber,
                    a.Asset.Name, a.Asset.SerialNumber, a.Condition, a.Accessories, a.Damage, a.MissingItems, null, null, a.Comment, null, a.IsCancelled)).ToListAsync(ct));
                break;
            case OperationType.Transfer:
                var transfers = await _db.AssetTransfers.AsNoTracking().Where(a => a.BatchId == id)
                    .Select(a => new { a.Id, a.AssetId, a.Asset!.InventoryNumber, a.Asset.Name, a.Asset.SerialNumber, a.Snapshot, a.Comment, a.IsCancelled }).ToListAsync(ct);
                foreach (var t in transfers)
                {
                    var snap = Json.ToElement(t.Snapshot);
                    string? Describe(string side)
                    {
                        if (snap is null || !snap.Value.TryGetProperty(side, out var s)) return null;
                        return string.Join(" / ", new[] { "employee", "location", "department", "region" }
                            .Select(k => s.TryGetProperty(k, out var v) && v.ValueKind == System.Text.Json.JsonValueKind.String ? v.GetString() : null)
                            .Where(v => !string.IsNullOrEmpty(v)));
                    }
                    lines.Add(new BatchLineDto(t.Id, t.AssetId, t.InventoryNumber, t.Name, t.SerialNumber, null, null, null, null, Describe("from"), Describe("to"), t.Comment, null, t.IsCancelled));
                }
                break;
            case OperationType.StatusChange:
                lines.AddRange(await _db.AssetStatusChanges.AsNoTracking().Where(a => a.BatchId == id).Select(a => new BatchLineDto(a.Id, a.AssetId, a.Asset!.InventoryNumber,
                    a.Asset.Name, a.Asset.SerialNumber, null, null, null, null,
                    _db.AssetStatuses.Where(s => s.Id == a.FromStatusId).Select(s => s.Name).FirstOrDefault(),
                    _db.AssetStatuses.Where(s => s.Id == a.ToStatusId).Select(s => s.Name).FirstOrDefault(), a.Reason, null, a.IsCancelled)).ToListAsync(ct));
                break;
        }
        var docs = await _db.GeneratedDocuments.AsNoTracking().Where(d => d.SourceType == DocumentSources.OperationBatch && d.SourceId == id && !d.IsVoided)
            .OrderByDescending(d => d.CreatedAt)
            .Select(d => new BatchDocumentDto(d.Id, d.Number, d.Title, d.CreatedAt, d.DocxFileId, d.PdfFileId, d.TemplateVersionNumber)).ToListAsync(ct);
        var createdBy = await _db.Users.Where(u => u.Id == b.CreatedById).Select(u => u.DisplayName).FirstOrDefaultAsync(ct);
        return new BatchDto(b.Id, b.Number, b.Type, b.EffectiveAt, b.RecordedAt, createdBy, b.EmployeeId, b.Employee?.FullName,
            Json.ToElement(b.EmployeeSnapshot), b.ResponsibleEmployeeId, Json.ToElement(b.ResponsibleSnapshot), b.Comment, b.IsBackdated,
            b.IsCancelled, b.CancelReason, b.CancelledAt, b.EmployeeSignatureStatus, b.ResponsibleSignatureStatus, b.SignedAt, b.SignatureMethod, lines, docs);
    }

    public async Task<BatchDto> UpdateSignatureAsync(Guid id, SignatureUpdate req, CancellationToken ct)
    {
        var b = await VisibleBatches().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Операция", id);
        b.EmployeeSignatureStatus = req.EmployeeSignatureStatus;
        b.ResponsibleSignatureStatus = req.ResponsibleSignatureStatus;
        b.SignatureMethod = req.SignatureMethod;
        b.SignedAt = req.SignedAt?.ToUniversalTime() ?? (req.EmployeeSignatureStatus == SignatureStatus.Signed ? _clock.UtcNow : null);
        await _db.SaveChangesAsync(ct);
        return await GetBatchAsync(id, ct);
    }
}
