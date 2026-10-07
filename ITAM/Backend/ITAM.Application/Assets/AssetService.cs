using System.Linq.Expressions;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Finance;
using ITAM.Domain.Numbering;
using ITAM.Domain.Security;
using ITAM.Domain.Temporal;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Assets;

public sealed class AssetService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly IDepartmentScope _deptScope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly ICustomFieldValidator _customFields;
    private readonly INumberGenerator _numbers;
    private readonly ISettingsService _settings;
    private readonly AssetTemporalStore _temporal;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly ISnapshotService _snapshots;

    public AssetService(IAppDbContext db, IRegionScope scope, IDepartmentScope deptScope, ICurrentUser user, IClock clock,
        ICustomFieldValidator customFields, INumberGenerator numbers, ISettingsService settings, AssetTemporalStore temporal,
        IAuditService audit, AuditContext auditCtx, ISnapshotService snapshots)
    {
        _db = db; _scope = scope; _deptScope = deptScope; _user = user; _clock = clock; _customFields = customFields;
        _numbers = numbers; _settings = settings; _temporal = temporal; _audit = audit; _auditCtx = auditCtx; _snapshots = snapshots;
    }

    public async Task<IQueryable<Asset>> VisibleAsync(CancellationToken ct)
    {
        var q = _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId);
        var depts = await _deptScope.AllowedDepartmentsAsync(ct);
        if (depts is not null)
            q = q.Where(a => (a.DepartmentId != null && depts.Contains(a.DepartmentId.Value))
                             || (a.Employee != null && a.Employee.DepartmentId != null && depts.Contains(a.Employee.DepartmentId.Value)));
        return q;
    }

    private static readonly Dictionary<string, Expression<Func<Asset, object?>>> Sorts = new()
    {
        ["inventoryNumber"] = a => a.InventoryNumber,
        ["name"] = a => a.Name,
        ["typeName"] = a => a.AssetType!.Name,
        ["statusName"] = a => a.Status!.Name,
        ["employeeName"] = a => a.Employee!.FullName,
        ["regionName"] = a => a.Region!.Name,
        ["departmentName"] = a => a.Department!.Name,
        ["locationName"] = a => a.Location!.Name,
        ["serialNumber"] = a => a.SerialNumber,
        ["manufacturerName"] = a => a.Manufacturer!.Name,
        ["model"] = a => a.Model,
        ["purchaseDate"] = a => a.PurchaseDate,
        ["purchasePrice"] = a => a.PurchasePrice,
        ["warrantyExpiration"] = a => a.WarrantyExpiration,
        ["createdAt"] = a => a.CreatedAt,
    };

    public async Task<IQueryable<Asset>> FilteredAsync(AssetQuery q, CancellationToken ct)
    {
        var query = (await VisibleAsync(ct)).AsNoTracking();
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(a => EF.Functions.ILike(a.InventoryNumber, like) || EF.Functions.ILike(a.Name, like)
                                     || (a.SerialNumber != null && EF.Functions.ILike(a.SerialNumber, like))
                                     || (a.Model != null && EF.Functions.ILike(a.Model, like))
                                     || (a.Hostname != null && EF.Functions.ILike(a.Hostname, like))
                                     || (a.IpAddress != null && EF.Functions.ILike(a.IpAddress, like))
                                     || (a.MacAddress != null && EF.Functions.ILike(a.MacAddress, like))
                                     || (a.Employee != null && EF.Functions.ILike(a.Employee.FullName, like)));
        }
        if (q.AssetTypeId is not null) query = query.Where(a => a.AssetTypeId == q.AssetTypeId);
        if (q.CategoryId is not null) query = query.Where(a => a.CategoryId == q.CategoryId);
        if (q.StatusId is not null) query = query.Where(a => a.StatusId == q.StatusId);
        if (q.StatusKind is not null) query = query.Where(a => a.Status!.Kind == q.StatusKind);
        if (q.RegionId is not null) query = query.Where(a => a.RegionId == q.RegionId);
        if (q.DepartmentId is not null) query = query.Where(a => a.DepartmentId == q.DepartmentId);
        if (q.LocationId is not null)
        {
            var locIds = await LocationSubtreeAsync(q.LocationId.Value, ct);
            query = query.Where(a => a.LocationId != null && locIds.Contains(a.LocationId.Value));
        }
        if (q.EmployeeId is not null) query = query.Where(a => a.EmployeeId == q.EmployeeId);
        if (q.ManufacturerId is not null) query = query.Where(a => a.ManufacturerId == q.ManufacturerId);
        if (q.SupplierId is not null) query = query.Where(a => a.SupplierId == q.SupplierId);
        if (q.ResponsibleEmployeeId is not null) query = query.Where(a => a.ResponsibleEmployeeId == q.ResponsibleEmployeeId);
        if (q.ParentAssetId is not null) query = query.Where(a => a.ParentAssetId == q.ParentAssetId);
        if (q.PurchaseFrom is not null) query = query.Where(a => a.PurchaseDate >= q.PurchaseFrom);
        if (q.PurchaseTo is not null) query = query.Where(a => a.PurchaseDate <= q.PurchaseTo);
        if (q.WarrantyFrom is not null) query = query.Where(a => a.WarrantyExpiration >= q.WarrantyFrom);
        if (q.WarrantyTo is not null) query = query.Where(a => a.WarrantyExpiration <= q.WarrantyTo);
        if (q.WarrantyExpired is not null)
        {
            var today = DateOnly.FromDateTime(_clock.UtcNow);
            query = q.WarrantyExpired.Value ? query.Where(a => a.WarrantyExpiration < today) : query.Where(a => a.WarrantyExpiration == null || a.WarrantyExpiration >= today);
        }
        if (q.NoResponsible == true) query = query.Where(a => a.ResponsibleEmployeeId == null);
        if (q.Assigned is not null) query = q.Assigned.Value ? query.Where(a => a.EmployeeId != null) : query.Where(a => a.EmployeeId == null);
        if (!string.IsNullOrWhiteSpace(q.CustomFieldKey) && q.CustomFieldValue is not null)
        {
            var json = Json.Serialize(new Dictionary<string, string> { [q.CustomFieldKey] = q.CustomFieldValue });
            query = query.Where(a => a.CustomFields != null && EF.Functions.JsonContains(a.CustomFields, json));
        }
        if (!q.IncludeArchived) query = query.Where(a => a.Status!.Kind != AssetStateKind.Archived);
        return query;
    }

    private async Task<List<Guid>> LocationSubtreeAsync(Guid root, CancellationToken ct)
    {
        var all = await _db.Locations.AsNoTracking().Select(d => new { d.Id, d.ParentId }).ToListAsync(ct);
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

    public Expression<Func<Asset, AssetListItem>> ListProjection()
    {
        var finance = _user.Has(Permissions.AssetsFinanceView);
        return a => new AssetListItem(a.Id, a.InventoryNumber, a.Name, a.AssetTypeId, a.AssetType!.Name, a.Category != null ? a.Category.Name : null,
            a.Manufacturer != null ? a.Manufacturer.Name : null, a.Model, a.SerialNumber,
            a.StatusId, a.Status!.Name, a.Status.Color, a.Status.Kind,
            a.EmployeeId, a.Employee != null ? a.Employee.FullName : null, a.DepartmentId, a.Department != null ? a.Department.Name : null,
            a.RegionId, a.Region!.Name, a.LocationId, a.Location != null ? (a.Location.FullPath ?? a.Location.Name) : null,
            a.ResponsibleEmployeeId, a.ResponsibleEmployee != null ? a.ResponsibleEmployee.FullName : null,
            a.PurchaseDate, finance ? a.PurchasePrice : null, a.Currency, a.WarrantyExpiration,
            a.Hostname, a.IpAddress, a.Condition, null, a.CreatedAt);
    }

    public async Task<PagedResult<AssetListItem>> ListAsync(AssetQuery q, CancellationToken ct)
    {
        var query = (await FilteredAsync(q, ct)).SortBy(q, Sorts, "inventoryNumber");
        var page = await query.ToPagedAsync(q, ListProjection(), ct);
        // Custom fields for column selection (loaded separately: jsonb strings are parsed in memory).
        var ids = page.Items.Select(i => i.Id).ToList();
        var cfs = await _db.Assets.AsNoTracking().Where(a => ids.Contains(a.Id) && a.CustomFields != null)
            .Select(a => new { a.Id, a.CustomFields }).ToDictionaryAsync(a => a.Id, a => a.CustomFields, ct);
        var items = page.Items.Select(i => cfs.TryGetValue(i.Id, out var cf) ? i with { CustomFields = Json.ToElement(cf) } : i).ToList();
        return page with { Items = items };
    }

    public async Task<Asset> LoadVisibleAsync(Guid id, CancellationToken ct, bool tracking = true)
    {
        var q = await VisibleAsync(ct);
        if (!tracking) q = q.AsNoTracking();
        return await q.FirstOrDefaultAsync(a => a.Id == id, ct) ?? throw new NotFoundException("Актив", id);
    }

    public async Task<AssetDto> GetAsync(Guid id, CancellationToken ct)
    {
        var a = await (await VisibleAsync(ct)).AsNoTracking()
            .Include(x => x.AssetType).Include(x => x.Category).Include(x => x.Manufacturer).Include(x => x.Status)
            .Include(x => x.Employee).Include(x => x.Department).Include(x => x.Region).Include(x => x.Location)
            .Include(x => x.ResponsibleEmployee).Include(x => x.ParentAsset).Include(x => x.Supplier).Include(x => x.Contract)
            .FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Актив", id);
        var finance = _user.Has(Permissions.AssetsFinanceView);
        var life = a.UsefulLifeMonths ?? a.AssetType?.UsefulLifeMonths ?? a.Category?.DefaultUsefulLifeMonths;
        var depreciation = finance ? DepreciationCalculator.Calculate(a.DepreciationMethod, a.PurchasePrice, a.SalvageValue, a.PurchaseDate, life, DateOnly.FromDateTime(_clock.UtcNow)) : null;

        var current = await _db.Assignments.AsNoTracking().Where(x => x.AssetId == id && x.EffectiveTo == null && !x.IsCancelled)
            .Select(x => new CurrentAssignmentDto(x.Id, x.BatchId, x.Batch!.Number, x.EffectiveFrom, x.RecordedAt, x.ExpectedReturnDate, x.Accessories))
            .FirstOrDefaultAsync(ct);
        var children = await _db.Assets.AsNoTracking().Where(x => x.ParentAssetId == id)
            .Select(x => new ChildAssetDto(x.Id, x.InventoryNumber, x.Name, x.Status!.Name)).ToListAsync(ct);
        var repair = await _db.Repairs.AsNoTracking()
            .Where(r => r.AssetId == id && r.Status!.Stage != RepairStage.Returned && r.Status.Stage != RepairStage.Cancelled)
            .Select(r => new OpenRepairDto(r.Id, r.Number, r.Status!.Name, r.OpenedAt)).FirstOrDefaultAsync(ct);

        return new AssetDto(a.Id, a.InventoryNumber, a.Name, a.AssetTypeId, a.AssetType?.Name, a.AssetType?.Prefix, a.CategoryId, a.Category?.Name,
            a.ManufacturerId, a.Manufacturer?.Name, a.Model, a.SerialNumber,
            a.StatusId, a.Status?.Name, a.Status?.Color, a.Status?.Kind ?? AssetStateKind.InStock,
            a.EmployeeId, a.Employee?.FullName, a.Employee?.EmployeeNumber, a.DepartmentId, a.Department?.Name,
            a.RegionId, a.Region?.Name, a.LocationId, a.Location?.FullPath ?? a.Location?.Name,
            a.ResponsibleEmployeeId, a.ResponsibleEmployee?.FullName, a.ParentAssetId, a.ParentAsset?.InventoryNumber,
            a.Hostname, a.IpAddress, a.MacAddress,
            a.PurchaseDate, finance ? a.PurchasePrice : null, a.Currency, a.SupplierId, a.Supplier?.Name,
            a.ContractId, a.Contract?.Number, a.InvoiceNumber, a.WarrantyExpiration,
            a.DepreciationMethod, life, finance ? a.SalvageValue : null, depreciation,
            a.Condition, a.Notes, Json.ToElement(a.CustomFields), a.LastInventoryAt,
            a.CreatedAt, a.UpdatedAt, a.Version, current, children, repair);
    }

    public async Task<AssetDto> CreateAsync(AssetInput input, CancellationToken ct)
    {
        var type = await _db.AssetTypes.AsNoTracking().FirstOrDefaultAsync(t => t.Id == input.AssetTypeId && !t.IsArchived, ct)
                   ?? throw new ValidationFailedException("Тип актива не найден", new Dictionary<string, string[]> { ["assetTypeId"] = new[] { "Тип не найден" } });
        if (input.RegionId is null) throw new ValidationFailedException("Укажите регион", new Dictionary<string, string[]> { ["regionId"] = new[] { "Обязательное поле" } });
        _scope.EnsureAccess(input.RegionId);
        if (type.RequireSerialNumber && string.IsNullOrWhiteSpace(input.SerialNumber))
            throw new ValidationFailedException("Для этого типа обязателен серийный номер", new Dictionary<string, string[]> { ["serialNumber"] = new[] { "Обязательное поле" } });
        await ValidateReferencesAsync(input, null, ct);

        var asset = new Asset { AssetTypeId = type.Id, CategoryId = type.CategoryId, RegionId = input.RegionId.Value };
        Apply(asset, input);
        asset.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Asset, type.Id, input.CustomFields, ct);
        asset.InventoryNumber = string.IsNullOrWhiteSpace(input.InventoryNumber)
            ? await NextInventoryNumberAsync(type, input.RegionId.Value, ct)
            : input.InventoryNumber.Trim().ToUpperInvariant();
        if (await _db.Assets.IgnoreQueryFilters().AnyAsync(a => a.InventoryNumber == asset.InventoryNumber, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Инвентарный номер {asset.InventoryNumber} уже используется");
        if (!string.IsNullOrWhiteSpace(asset.SerialNumber) && await _db.Assets.AnyAsync(a => a.SerialNumber == asset.SerialNumber && a.ManufacturerId == asset.ManufacturerId, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Актив с серийным номером {asset.SerialNumber} уже существует");

        var statusId = input.StatusId ?? await _temporal.DefaultStatusAsync(AssetStateKind.InStock, ct);
        var kinds = await _temporal.KindsAsync(ct);
        if (kinds(statusId) is AssetStateKind.Assigned or AssetStateKind.InRepair)
            throw new ValidationFailedException("Начальный статус не может быть «Выдан» или «В ремонте» — используйте операции");
        asset.StatusId = statusId;
        _db.Assets.Add(asset);

        var registeredAt = input.RegisteredAt?.ToUniversalTime()
                           ?? (input.PurchaseDate is { } pd && pd.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc) <= _clock.UtcNow
                               ? pd.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc) : _clock.UtcNow);
        if (registeredAt > _clock.UtcNow.AddMinutes(5)) throw new BusinessException(ErrorCodes.FutureDate, "Дата регистрации не может быть в будущем");
        var created = _temporal.NewEvent(asset, AssetEventType.Created, registeredAt, new AssetStateDelta
        {
            StatusId = statusId,
            SetEmployee = true, EmployeeId = null,
            SetDepartment = true, DepartmentId = input.DepartmentId,
            SetRegion = true, RegionId = input.RegionId,
            SetLocation = true, LocationId = input.LocationId,
        }, description: "Актив зарегистрирован", data: new
        {
            status = await _snapshots.StatusNameAsync(statusId, ct),
            location = await _snapshots.LocationNameAsync(input.LocationId, ct),
            region = await _snapshots.RegionNameAsync(input.RegionId, ct),
        });
        await _temporal.ApplyAsync(asset, created, null, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(asset.Id, ct);
    }

    public async Task<string> NextInventoryNumberAsync(AssetType type, Guid regionId, CancellationToken ct)
    {
        var cfg = await _settings.GetAsync<NumberingSettings>(ct);
        var pattern = string.IsNullOrWhiteSpace(type.InventoryNumberFormat) ? cfg.AssetFormat : type.InventoryNumberFormat;
        var regionCode = pattern.Contains("{REGION}") ? await _db.Regions.Where(r => r.Id == regionId).Select(r => r.Code).FirstOrDefaultAsync(ct) : null;
        for (var attempt = 0; attempt < 20; attempt++)
        {
            var now = _clock.UtcNow;
            var key = NumberFormatter.SequenceKey("asset", pattern, type.Prefix, now, regionCode);
            var seq = await _numbers.NextAsync(key, ct);
            var number = NumberFormatter.Format(pattern, seq, type.Prefix, now, regionCode);
            // Skip numbers taken manually / by import.
            if (!await _db.Assets.IgnoreQueryFilters().AnyAsync(a => a.InventoryNumber == number, ct)) return number;
        }
        throw new BusinessException("NUMBERING_EXHAUSTED", "Не удалось сгенерировать свободный инвентарный номер");
    }

    public async Task<AssetDto> UpdateAsync(Guid id, AssetInput input, CancellationToken ct)
    {
        var asset = await LoadVisibleAsync(id, ct);
        if (input.Version is not null && input.Version != asset.Version)
            throw new ConflictException(ErrorCodes.AssetConcurrentModification, "Актив был изменён другим пользователем. Обновите страницу.");
        await ValidateReferencesAsync(input, id, ct);
        if (input.AssetTypeId != asset.AssetTypeId)
        {
            var type = await _db.AssetTypes.AsNoTracking().FirstOrDefaultAsync(t => t.Id == input.AssetTypeId, ct) ?? throw new ValidationFailedException("Тип актива не найден");
            asset.AssetTypeId = type.Id;
            asset.CategoryId = type.CategoryId;
        }
        if (!_user.Has(Permissions.AssetsFinanceView))
        {
            // Users without finance access cannot see the values, so they must not overwrite them either.
            input.PurchasePrice = asset.PurchasePrice;
            input.SalvageValue = asset.SalvageValue;
        }
        Apply(asset, input);
        if (!string.IsNullOrWhiteSpace(input.InventoryNumber) && !string.Equals(input.InventoryNumber.Trim(), asset.InventoryNumber, StringComparison.OrdinalIgnoreCase))
        {
            var number = input.InventoryNumber.Trim().ToUpperInvariant();
            if (await _db.Assets.IgnoreQueryFilters().AnyAsync(a => a.InventoryNumber == number && a.Id != id, ct))
                throw new ConflictException(ErrorCodes.Duplicate, $"Инвентарный номер {number} уже используется");
            asset.InventoryNumber = number;
        }
        asset.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.Asset, asset.AssetTypeId, input.CustomFields, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    private static void Apply(Asset a, AssetInput i)
    {
        a.Name = i.Name.Trim();
        a.ManufacturerId = i.ManufacturerId;
        a.Model = i.Model?.Trim();
        a.SerialNumber = string.IsNullOrWhiteSpace(i.SerialNumber) ? null : i.SerialNumber.Trim();
        a.ResponsibleEmployeeId = i.ResponsibleEmployeeId;
        a.ParentAssetId = i.ParentAssetId;
        a.Hostname = i.Hostname?.Trim();
        a.IpAddress = i.IpAddress?.Trim();
        a.MacAddress = i.MacAddress?.Trim().ToUpperInvariant();
        a.PurchaseDate = i.PurchaseDate;
        a.PurchasePrice = i.PurchasePrice;
        a.Currency = i.Currency;
        a.SupplierId = i.SupplierId;
        a.ContractId = i.ContractId;
        a.InvoiceNumber = i.InvoiceNumber;
        a.WarrantyExpiration = i.WarrantyExpiration;
        a.DepreciationMethod = i.DepreciationMethod;
        a.UsefulLifeMonths = i.UsefulLifeMonths;
        a.SalvageValue = i.SalvageValue;
        a.Condition = i.Condition;
        a.Notes = i.Notes;
    }

    private async Task ValidateReferencesAsync(AssetInput i, Guid? selfId, CancellationToken ct)
    {
        var errors = new Dictionary<string, string[]>();
        if (i.ManufacturerId is not null && !await _db.Manufacturers.AnyAsync(x => x.Id == i.ManufacturerId, ct)) errors["manufacturerId"] = new[] { "Не найден" };
        if (i.SupplierId is not null && !await _db.Suppliers.AnyAsync(x => x.Id == i.SupplierId, ct)) errors["supplierId"] = new[] { "Не найден" };
        if (i.ContractId is not null && !await _db.Contracts.AnyAsync(x => x.Id == i.ContractId, ct)) errors["contractId"] = new[] { "Не найден" };
        if (i.ResponsibleEmployeeId is not null && !await _db.Employees.AnyAsync(x => x.Id == i.ResponsibleEmployeeId, ct)) errors["responsibleEmployeeId"] = new[] { "Не найден" };
        if (i.LocationId is not null && !await _db.Locations.AnyAsync(x => x.Id == i.LocationId, ct)) errors["locationId"] = new[] { "Не найдена" };
        if (i.DepartmentId is not null && !await _db.Departments.AnyAsync(x => x.Id == i.DepartmentId, ct)) errors["departmentId"] = new[] { "Не найдено" };
        if (i.ParentAssetId is not null)
        {
            if (i.ParentAssetId == selfId) errors["parentAssetId"] = new[] { "Актив не может входить в состав самого себя" };
            else if (!await _db.Assets.AnyAsync(x => x.Id == i.ParentAssetId, ct)) errors["parentAssetId"] = new[] { "Не найден" };
            else if (selfId is not null && await _db.Assets.AnyAsync(x => x.Id == i.ParentAssetId && x.ParentAssetId == selfId, ct))
                errors["parentAssetId"] = new[] { "Циклическая связь" };
        }
        if (errors.Count > 0) throw new ValidationFailedException("Проверьте заполнение полей", errors);
    }

    /// <summary>Soft delete is allowed only for assets without operational history; otherwise use archive status.</summary>
    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var asset = await LoadVisibleAsync(id, ct);
        var hasHistory = await _db.AssetEvents.AnyAsync(e => e.AssetId == id && e.EventType != AssetEventType.Created && e.EventType != AssetEventType.Updated, ct)
                         || await _db.Assignments.AnyAsync(e => e.AssetId == id, ct)
                         || await _db.Repairs.AnyAsync(e => e.AssetId == id, ct)
                         || await _db.LicenseAssignments.AnyAsync(e => e.AssetId == id, ct);
        if (hasHistory)
            throw new ConflictException(ErrorCodes.HasDependencies, "У актива есть история операций — удаление запрещено. Используйте статус «Архив» или списание.");
        _db.Assets.Remove(asset);
        await _db.SaveChangesAsync(ct);
    }

    public async Task<IReadOnlyList<AssetEventDto>> HistoryAsync(Guid id, CancellationToken ct)
    {
        await LoadVisibleAsync(id, ct, tracking: false);
        var events = await _db.AssetEvents.AsNoTracking().Where(e => e.AssetId == id)
            .OrderByDescending(e => e.EffectiveAt).ThenByDescending(e => e.Sequence).ToListAsync(ct);
        var statusIds = events.Where(e => e.StatusId != null).Select(e => e.StatusId!.Value).Distinct().ToList();
        var empIds = events.Where(e => e.EmployeeId != null).Select(e => e.EmployeeId!.Value).Distinct().ToList();
        var deptIds = events.Where(e => e.DepartmentId != null).Select(e => e.DepartmentId!.Value).Distinct().ToList();
        var regIds = events.Where(e => e.RegionId != null).Select(e => e.RegionId!.Value).Distinct().ToList();
        var locIds = events.Where(e => e.LocationId != null).Select(e => e.LocationId!.Value).Distinct().ToList();
        var statuses = await _db.AssetStatuses.IgnoreQueryFilters().Where(s => statusIds.Contains(s.Id)).ToDictionaryAsync(s => s.Id, s => s.Name, ct);
        var emps = await _db.Employees.IgnoreQueryFilters().Where(s => empIds.Contains(s.Id)).ToDictionaryAsync(s => s.Id, s => s.FullName, ct);
        var depts = await _db.Departments.IgnoreQueryFilters().Where(s => deptIds.Contains(s.Id)).ToDictionaryAsync(s => s.Id, s => s.Name, ct);
        var regs = await _db.Regions.IgnoreQueryFilters().Where(s => regIds.Contains(s.Id)).ToDictionaryAsync(s => s.Id, s => s.Name, ct);
        var locs = await _db.Locations.IgnoreQueryFilters().Where(s => locIds.Contains(s.Id)).ToDictionaryAsync(s => s.Id, s => s.FullPath ?? s.Name, ct);
        var tolerance = (await _settings.GetAsync<SecuritySettings>(ct)).BackdateToleranceHours;
        return events.Select(e => new AssetEventDto(e.Id, e.Sequence, e.EventType, e.AffectsState, e.EffectiveAt, e.RecordedAt, e.RecordedByName,
            e.OperationType, e.OperationId, e.BatchId, e.Description, Json.ToElement(e.Data),
            e.StatusId is { } s ? statuses.GetValueOrDefault(s) : null,
            e.EmployeeId is { } em ? emps.GetValueOrDefault(em) : null,
            e.DepartmentId is { } d ? depts.GetValueOrDefault(d) : null,
            e.RegionId is { } r ? regs.GetValueOrDefault(r) : null,
            e.LocationId is { } l ? locs.GetValueOrDefault(l) : null,
            e.IsCancelled, e.CancelReason, e.EventType != AssetEventType.Created && (e.RecordedAt - e.EffectiveAt).TotalHours > tolerance)).ToList();
    }

    public async Task<IReadOnlyList<TimelineItem>> TimelineAsync(Guid id, CancellationToken ct)
        => (await HistoryAsync(id, ct)).Select(e => new TimelineItem(e.EffectiveAt, e.RecordedAt, e.EventType.ToString(),
            e.Description ?? e.EventType.ToString(),
            e.EventType switch
            {
                AssetEventType.Assigned or AssetEventType.Transferred => e.EmployeeName ?? e.LocationName,
                AssetEventType.Returned => e.LocationName ?? e.StatusName,
                _ when e.AffectsState => e.StatusName,
                _ => null
            },
            null, e.RecordedByName, e.IsBackdated, e.IsCancelled,
            e.EventType switch
            {
                AssetEventType.Created => "green",
                AssetEventType.Assigned => "blue",
                AssetEventType.Returned => "orange",
                AssetEventType.RepairOpened => "red",
                AssetEventType.RepairClosed => "green",
                AssetEventType.Transferred => "purple",
                _ => "gray"
            })).ToList();

    public async Task<AssetStateAtDto> StateAtAsync(Guid id, DateTime at, CancellationToken ct)
    {
        await LoadVisibleAsync(id, ct, tracking: false);
        var s = await _temporal.StateAtAsync(id, at.ToUniversalTime(), ct);
        return new AssetStateAtDto(at, s.StatusId, await _snapshots.StatusNameAsync(s.StatusId, ct), s.Kind, s.EmployeeId,
            s.EmployeeId is null ? null : await _db.Employees.IgnoreQueryFilters().Where(e => e.Id == s.EmployeeId).Select(e => e.FullName).FirstOrDefaultAsync(ct),
            await _snapshots.DepartmentNameAsync(s.DepartmentId, ct), await _snapshots.RegionNameAsync(s.RegionId, ct), await _snapshots.LocationNameAsync(s.LocationId, ct));
    }

    public async Task<BulkResultDto> BulkEditAsync(AssetBulkEditRequest req, CancellationToken ct)
    {
        var assets = await (await VisibleAsync(ct)).Where(a => req.AssetIds.Contains(a.Id)).ToListAsync(ct);
        foreach (var a in assets)
        {
            if (req.SetResponsible) a.ResponsibleEmployeeId = req.ResponsibleEmployeeId;
            if (req.SetWarranty) a.WarrantyExpiration = req.WarrantyExpiration;
            if (req.SetSupplier) a.SupplierId = req.SupplierId;
        }
        await _db.SaveChangesAsync(ct);
        return new BulkResultDto(assets.Count, req.AssetIds.Except(assets.Select(a => a.Id))
            .Select(id => new BulkErrorDto(id, null, "NOT_FOUND", "Не найден или вне области доступа")).ToList());
    }

    public async Task<IReadOnlyList<LabelData>> LabelsAsync(IReadOnlyList<Guid> ids, string baseUrl, CancellationToken ct)
    {
        var assets = await (await VisibleAsync(ct)).AsNoTracking().Where(a => ids.Contains(a.Id)).OrderBy(a => a.InventoryNumber)
            .Select(a => new { a.Id, a.InventoryNumber, a.Name, a.SerialNumber }).ToListAsync(ct);
        return assets.Select(a => new LabelData($"{baseUrl.TrimEnd('/')}/assets/{a.Id}", a.InventoryNumber, a.Name, a.SerialNumber)).ToList();
    }
}

public sealed record BulkResultDto(int Succeeded, IReadOnlyList<BulkErrorDto> Errors);
public sealed record BulkErrorDto(Guid Id, string? Name, string Code, string Message);
