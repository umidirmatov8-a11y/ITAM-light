using System.ComponentModel.DataAnnotations;
using System.Linq.Expressions;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Licenses;

public sealed class LicenseQuery : PagedRequest
{
    public Guid? SoftwareId { get; set; }
    public Guid? VendorId { get; set; }
    public LicenseModel? Model { get; set; }
    public Guid? RegionId { get; set; }
    public bool? Expired { get; set; }
    public int? ExpiringInDays { get; set; }
    public bool? OverAllocated { get; set; }
}

public sealed class LicenseInput
{
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    public Guid? SoftwareId { get; set; }
    public Guid? VendorId { get; set; }
    public Guid? SupplierId { get; set; }
    public Guid? LicenseTypeId { get; set; }
    public LicenseModel Model { get; set; }
    /// <summary>Null = keep the existing key; empty string = remove.</summary>
    [MaxLength(4000)] public string? LicenseKey { get; set; }
    [Range(1, 1000000)] public int Seats { get; set; } = 1;
    public DateOnly? PurchaseDate { get; set; }
    public DateOnly? ExpirationDate { get; set; }
    public DateOnly? RenewalDate { get; set; }
    [Range(0, 999999999999)] public decimal? Cost { get; set; }
    [MaxLength(8)] public string? Currency { get; set; }
    public Guid? ContractId { get; set; }
    [MaxLength(128)] public string? ContractNumber { get; set; }
    [MaxLength(4000)] public string? Notes { get; set; }
    public Guid? RegionId { get; set; }
    public Dictionary<string, JsonElement>? CustomFields { get; set; }
    public uint? Version { get; set; }
}

public sealed class LicenseAssignRequest
{
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public DateTime? AssignedAt { get; set; }
    [Range(1, 10000)] public int SeatCount { get; set; } = 1;
    [MaxLength(2000)] public string? Comment { get; set; }
    /// <summary>Explicit confirmation required to assign an expired license.</summary>
    public bool ConfirmExpired { get; set; }
}

public sealed class LicenseRevokeRequest
{
    public DateTime? RevokedAt { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
}

public sealed record LicenseListItem(Guid Id, string Name, Guid? SoftwareId, string? SoftwareName, string? VendorName, string? LicenseTypeName,
    LicenseModel Model, int Seats, int UsedSeats, int AvailableSeats, int ExpiredSeats, DateOnly? PurchaseDate, DateOnly? ExpirationDate,
    DateOnly? RenewalDate, decimal? Cost, string? Currency, string? RegionName, bool IsExpired, int? DaysToExpiry, bool IsArchived, bool HasKey);

public sealed record LicenseDto(Guid Id, string Name, Guid? SoftwareId, string? SoftwareName, Guid? VendorId, string? VendorName,
    Guid? SupplierId, string? SupplierName, Guid? LicenseTypeId, string? LicenseTypeName, LicenseModel Model, string? LicenseKeyMasked,
    int Seats, int UsedSeats, int AvailableSeats, int ExpiredSeats, DateOnly? PurchaseDate, DateOnly? ExpirationDate, DateOnly? RenewalDate,
    decimal? Cost, string? Currency, Guid? ContractId, string? ContractNumber, string? Notes, Guid? RegionId, string? RegionName,
    bool IsExpired, int? DaysToExpiry, bool IsArchived, JsonElement? CustomFields, uint Version, DateTime CreatedAt);

public sealed record LicenseAssignmentDto(Guid Id, Guid LicenseId, string LicenseName, string? SoftwareName, Guid? EmployeeId, string? EmployeeName,
    Guid? AssetId, string? AssetInventoryNumber, DateTime AssignedAt, DateTime? RevokedAt, DateTime RecordedAt, int SeatCount, string? Comment, string? RevokeReason);

public sealed record LicenseSummary(int Licenses, int TotalSeats, int UsedSeats, int AvailableSeats, int ExpiredSeats, int ExpiringSoon, int OverAllocated);

public sealed class LicenseService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly ISecretProtector _protector;
    private readonly IAuditService _audit;
    private readonly AuditContext _auditCtx;
    private readonly ICustomFieldValidator _customFields;
    private readonly AssetTemporalStore _temporal;

    public LicenseService(IAppDbContext db, IRegionScope scope, ICurrentUser user, IClock clock, ISecretProtector protector,
        IAuditService audit, AuditContext auditCtx, ICustomFieldValidator customFields, AssetTemporalStore temporal)
    {
        _db = db; _scope = scope; _user = user; _clock = clock; _protector = protector; _audit = audit; _auditCtx = auditCtx;
        _customFields = customFields; _temporal = temporal;
    }

    private DateOnly Today => DateOnly.FromDateTime(_clock.UtcNow);

    public IQueryable<License> Visible() => _scope.Apply(_db.Licenses.AsQueryable(), l => l.RegionId);

    private static readonly Dictionary<string, Expression<Func<License, object?>>> Sorts = new()
    {
        ["name"] = l => l.Name,
        ["softwareName"] = l => l.Software!.Name,
        ["expirationDate"] = l => l.ExpirationDate,
        ["seats"] = l => l.Seats,
        ["cost"] = l => l.Cost,
        ["purchaseDate"] = l => l.PurchaseDate,
    };

    public IQueryable<License> Filtered(LicenseQuery q)
    {
        var query = Visible().AsNoTracking();
        if (!q.IncludeArchived) query = query.Where(l => !l.IsArchived);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(l => EF.Functions.ILike(l.Name, like) || (l.Software != null && EF.Functions.ILike(l.Software.Name, like))
                                     || (l.ContractNumber != null && EF.Functions.ILike(l.ContractNumber, like)));
        }
        if (q.SoftwareId is not null) query = query.Where(l => l.SoftwareId == q.SoftwareId);
        if (q.VendorId is not null) query = query.Where(l => l.VendorId == q.VendorId);
        if (q.Model is not null) query = query.Where(l => l.Model == q.Model);
        if (q.RegionId is not null) query = query.Where(l => l.RegionId == q.RegionId);
        var today = Today;
        if (q.Expired is not null) query = q.Expired.Value ? query.Where(l => l.ExpirationDate < today) : query.Where(l => l.ExpirationDate == null || l.ExpirationDate >= today);
        if (q.ExpiringInDays is not null)
        {
            var until = today.AddDays(q.ExpiringInDays.Value);
            query = query.Where(l => l.ExpirationDate >= today && l.ExpirationDate <= until);
        }
        if (q.OverAllocated == true) query = query.Where(l => l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount) > l.Seats);
        return query;
    }

    public async Task<PagedResult<LicenseListItem>> ListAsync(LicenseQuery q, CancellationToken ct)
    {
        var today = Today;
        return await Filtered(q).SortBy(q, Sorts, "name").ToPagedAsync(q, l => new LicenseListItem(l.Id, l.Name, l.SoftwareId,
            l.Software != null ? l.Software.Name : null, l.Vendor != null ? l.Vendor.Name : null, l.LicenseType != null ? l.LicenseType.Name : null,
            l.Model, l.Seats,
            l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount),
            l.Seats - l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount),
            l.ExpirationDate < today ? l.Seats : 0,
            l.PurchaseDate, l.ExpirationDate, l.RenewalDate, l.Cost, l.Currency,
            _db.Regions.Where(r => r.Id == l.RegionId).Select(r => r.Name).FirstOrDefault(),
            l.ExpirationDate < today, l.ExpirationDate == null ? null : l.ExpirationDate.Value.DayNumber - today.DayNumber,
            l.IsArchived, l.LicenseKeyEncrypted != null), ct);
    }

    public async Task<LicenseDto> GetAsync(Guid id, CancellationToken ct)
    {
        var l = await Visible().AsNoTracking().Include(x => x.Software).Include(x => x.Vendor).Include(x => x.Supplier).Include(x => x.LicenseType)
                    .FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Лицензия", id);
        var used = await _db.LicenseAssignments.Where(a => a.LicenseId == id && a.RevokedAt == null).SumAsync(a => a.SeatCount, ct);
        var today = Today;
        var expired = l.ExpirationDate < today;
        var key = _protector.Unprotect(l.LicenseKeyEncrypted);
        return new LicenseDto(l.Id, l.Name, l.SoftwareId, l.Software?.Name, l.VendorId, l.Vendor?.Name, l.SupplierId, l.Supplier?.Name,
            l.LicenseTypeId, l.LicenseType?.Name, l.Model, Mask(key), l.Seats, used, l.Seats - used, expired ? l.Seats : 0,
            l.PurchaseDate, l.ExpirationDate, l.RenewalDate, _user.Has(Permissions.AssetsFinanceView) || _user.Has(Permissions.LicensesManage) ? l.Cost : null,
            l.Currency, l.ContractId, l.ContractNumber, l.Notes, l.RegionId,
            l.RegionId is null ? null : await _db.Regions.Where(r => r.Id == l.RegionId).Select(r => r.Name).FirstOrDefaultAsync(ct),
            expired, l.ExpirationDate is null ? null : l.ExpirationDate.Value.DayNumber - today.DayNumber, l.IsArchived,
            Json.ToElement(l.CustomFields), l.Version, l.CreatedAt);
    }

    private static string? Mask(string? key)
        => string.IsNullOrEmpty(key) ? null : key.Length <= 5 ? "*****" : new string('*', Math.Min(20, key.Length - 5)) + key[^5..];

    /// <summary>Reveals the license key (licenses.keys.view). Every access is audited.</summary>
    public async Task<string?> RevealKeyAsync(Guid id, CancellationToken ct)
    {
        var l = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Лицензия", id);
        _audit.Log("license.key.view", nameof(License), id, l.Name);
        await _db.SaveChangesAsync(ct);
        return _protector.Unprotect(l.LicenseKeyEncrypted);
    }

    public async Task<LicenseDto> SaveAsync(Guid? id, LicenseInput input, CancellationToken ct)
    {
        License l;
        if (id is null)
        {
            l = new License();
            _db.Licenses.Add(l);
        }
        else
        {
            l = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Лицензия", id);
            if (input.Version is not null && input.Version != l.Version)
                throw new ConflictException(ErrorCodes.ConcurrentModification, "Лицензия была изменена другим пользователем");
            var used = await _db.LicenseAssignments.Where(a => a.LicenseId == id && a.RevokedAt == null).SumAsync(a => a.SeatCount, ct);
            if (input.Seats < used) throw new ValidationFailedException($"Количество мест не может быть меньше занятых ({used})");
        }
        if (input.RegionId is not null) _scope.EnsureAccess(input.RegionId);
        else if (!_scope.IsUnrestricted) throw new ValidationFailedException("Укажите регион лицензии");
        if (input.ExpirationDate is not null && input.PurchaseDate is not null && input.ExpirationDate < input.PurchaseDate)
            throw new ValidationFailedException("Дата окончания раньше даты покупки");

        l.Name = input.Name.Trim();
        l.SoftwareId = input.SoftwareId;
        l.VendorId = input.VendorId;
        l.SupplierId = input.SupplierId;
        l.LicenseTypeId = input.LicenseTypeId;
        l.Model = input.Model;
        if (input.LicenseKey is not null)
            l.LicenseKeyEncrypted = input.LicenseKey.Length == 0 ? null : _protector.Protect(input.LicenseKey.Trim());
        l.Seats = input.Seats;
        l.PurchaseDate = input.PurchaseDate;
        l.ExpirationDate = input.ExpirationDate;
        l.RenewalDate = input.RenewalDate;
        l.Cost = input.Cost;
        l.Currency = input.Currency;
        l.ContractId = input.ContractId;
        l.ContractNumber = input.ContractNumber;
        l.Notes = input.Notes;
        l.RegionId = input.RegionId;
        l.CustomFields = await _customFields.NormalizeAsync(CustomFieldEntity.License, null, input.CustomFields, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(l.Id, ct);
    }

    public async Task ArchiveAsync(Guid id, bool archived, CancellationToken ct)
    {
        var l = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Лицензия", id);
        if (archived && await _db.LicenseAssignments.AnyAsync(a => a.LicenseId == id && a.RevokedAt == null, ct))
            throw new ConflictException(ErrorCodes.HasDependencies, "Сначала отзовите все назначения лицензии");
        l.IsArchived = archived;
        await _db.SaveChangesAsync(ct);
    }

    public async Task<LicenseAssignmentDto> AssignAsync(Guid licenseId, LicenseAssignRequest req, CancellationToken ct)
    {
        var l = await Visible().FirstOrDefaultAsync(x => x.Id == licenseId && !x.IsArchived, ct) ?? throw new NotFoundException("Лицензия", licenseId);
        if (req.EmployeeId is null && req.AssetId is null) throw new ValidationFailedException("Укажите сотрудника и/или устройство");
        if (l.Model == LicenseModel.PerDevice && req.AssetId is null) throw new ValidationFailedException("Лицензия «на устройство» требует указать устройство");
        if (l.Model == LicenseModel.PerUser && req.EmployeeId is null) throw new ValidationFailedException("Лицензия «на пользователя» требует указать сотрудника");
        var assignedAt = req.AssignedAt?.ToUniversalTime() ?? _clock.UtcNow;
        if (assignedAt > _clock.UtcNow.AddMinutes(5)) throw new BusinessException(ErrorCodes.FutureDate, "Дата не может быть в будущем");
        var assignDate = DateOnly.FromDateTime(assignedAt);
        if (l.ExpirationDate is not null && l.ExpirationDate < assignDate && !req.ConfirmExpired)
            throw new ConflictException(ErrorCodes.LicenseExpired, $"Лицензия истекла {l.ExpirationDate:dd.MM.yyyy}. Подтвердите назначение просроченной лицензии.");

        Employee? employee = null;
        if (req.EmployeeId is not null)
            employee = await _scope.Apply(_db.Employees.AsQueryable(), e => e.RegionId).FirstOrDefaultAsync(e => e.Id == req.EmployeeId, ct)
                       ?? throw new NotFoundException("Сотрудник", req.EmployeeId);
        Asset? asset = null;
        if (req.AssetId is not null)
            asset = await _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId).FirstOrDefaultAsync(a => a.Id == req.AssetId, ct)
                    ?? throw new NotFoundException("Актив", req.AssetId);
        if (await _db.LicenseAssignments.AnyAsync(a => a.LicenseId == licenseId && a.RevokedAt == null && a.EmployeeId == req.EmployeeId && a.AssetId == req.AssetId, ct))
            throw new ConflictException(ErrorCodes.Duplicate, "Такое назначение уже существует");

        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        var used = await _db.LicenseAssignments.Where(a => a.LicenseId == licenseId && a.RevokedAt == null).SumAsync(a => a.SeatCount, ct);
        if (l.Model is not (LicenseModel.Site or LicenseModel.Volume) || l.Seats > 0)
            if (used + req.SeatCount > l.Seats)
                throw new ConflictException(ErrorCodes.LicenseNoSeats, $"Нет свободных мест: занято {used} из {l.Seats}");

        var a = new LicenseAssignment
        {
            LicenseId = licenseId,
            EmployeeId = req.EmployeeId,
            AssetId = req.AssetId,
            AssignedAt = assignedAt,
            RecordedAt = _clock.UtcNow,
            RecordedById = _user.UserId,
            SeatCount = req.SeatCount,
            Comment = req.Comment,
            Snapshot = Json.Serialize(new { employee = employee?.FullName, asset = asset?.InventoryNumber, license = l.Name }),
        };
        _db.LicenseAssignments.Add(a);
        // Touch the license row: concurrent assignments of the last seat conflict on xmin.
        l.UpdatedAt = _clock.UtcNow;
        if (asset is not null)
            _temporal.AddInfoEvent(asset.Id, AssetEventType.LicenseAssigned, assignedAt, $"Назначена лицензия: {l.Name}", new { employee = employee?.FullName }, a.Id);
        using (_auditCtx.Suppress())
        {
            _audit.Log("license.assign", nameof(License), l.Id, l.Name, null,
                new { employee = employee?.FullName, asset = asset?.InventoryNumber, seats = req.SeatCount, assignedAt, expiredConfirmed = req.ConfirmExpired && l.ExpirationDate < assignDate });
            await _db.SaveChangesAsync(ct);
        }
        await tx.CommitAsync(ct);
        return (await AssignmentsAsync(licenseId, null, null, true, ct)).First(x => x.Id == a.Id);
    }

    public async Task<LicenseAssignmentDto> RevokeAsync(Guid assignmentId, LicenseRevokeRequest req, CancellationToken ct)
    {
        var a = await _db.LicenseAssignments.Include(x => x.License).FirstOrDefaultAsync(x => x.Id == assignmentId, ct) ?? throw new NotFoundException("Назначение лицензии", assignmentId);
        await GetAsync(a.LicenseId, ct); // scope check
        if (a.RevokedAt is not null) throw new BusinessException("ALREADY_REVOKED", "Назначение уже отозвано");
        var revokedAt = req.RevokedAt?.ToUniversalTime() ?? _clock.UtcNow;
        if (revokedAt < a.AssignedAt) throw new BusinessException(ErrorCodes.TemporalConflict, "Дата отзыва раньше даты назначения");
        a.RevokedAt = revokedAt;
        a.RevokeReason = req.Reason;
        if (a.AssetId is not null)
            _temporal.AddInfoEvent(a.AssetId.Value, AssetEventType.LicenseRevoked, revokedAt, $"Отозвана лицензия: {a.License!.Name}", null, a.Id);
        using (_auditCtx.Suppress())
        {
            _audit.Log("license.revoke", nameof(License), a.LicenseId, a.License!.Name, new { assignment = a.Id }, new { revokedAt }, req.Reason);
            await _db.SaveChangesAsync(ct);
        }
        return (await AssignmentsAsync(a.LicenseId, null, null, true, ct)).First(x => x.Id == a.Id);
    }

    public async Task<IReadOnlyList<LicenseAssignmentDto>> AssignmentsAsync(Guid? licenseId, Guid? employeeId, Guid? assetId, bool includeRevoked, CancellationToken ct)
    {
        var q = _db.LicenseAssignments.AsNoTracking().AsQueryable();
        if (licenseId is not null) q = q.Where(a => a.LicenseId == licenseId);
        if (employeeId is not null) q = q.Where(a => a.EmployeeId == employeeId);
        if (assetId is not null) q = q.Where(a => a.AssetId == assetId);
        if (!includeRevoked) q = q.Where(a => a.RevokedAt == null);
        q = _scope.Apply(q, a => a.License!.RegionId);
        return await q.OrderByDescending(a => a.AssignedAt).Take(2000).Select(a => new LicenseAssignmentDto(a.Id, a.LicenseId, a.License!.Name,
            a.License.Software != null ? a.License.Software.Name : null, a.EmployeeId, a.Employee != null ? a.Employee.FullName : null,
            a.AssetId, a.Asset != null ? a.Asset.InventoryNumber : null, a.AssignedAt, a.RevokedAt, a.RecordedAt, a.SeatCount, a.Comment, a.RevokeReason)).ToListAsync(ct);
    }

    public async Task<LicenseSummary> SummaryAsync(CancellationToken ct)
    {
        var today = Today;
        var soon = today.AddDays(30);
        var rows = await Visible().AsNoTracking().Where(l => !l.IsArchived)
            .Select(l => new { l.Seats, l.ExpirationDate, Used = l.Assignments.Where(a => a.RevokedAt == null).Sum(a => a.SeatCount) }).ToListAsync(ct);
        return new LicenseSummary(rows.Count, rows.Sum(r => r.Seats), rows.Sum(r => r.Used), rows.Sum(r => Math.Max(0, r.Seats - r.Used)),
            rows.Where(r => r.ExpirationDate < today).Sum(r => r.Seats), rows.Count(r => r.ExpirationDate >= today && r.ExpirationDate <= soon),
            rows.Count(r => r.Used > r.Seats));
    }
}
