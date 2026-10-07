using System.ComponentModel.DataAnnotations;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Stock;

public sealed class StockMovementRequest
{
    [Required] public Guid StockItemId { get; set; }
    public StockMovementType Type { get; set; }
    [Range(0.001, 1000000)] public decimal Quantity { get; set; }
    public Guid? FromLocationId { get; set; }
    public Guid? ToLocationId { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public Guid? RepairId { get; set; }
    public DateTime? EffectiveAt { get; set; }
    [MaxLength(128)] public string? DocumentNumber { get; set; }
    [MaxLength(2000)] public string? Comment { get; set; }
}

public sealed record StockBalanceDto(Guid StockItemId, string ItemName, string? Sku, string? Category, string Unit, Guid LocationId, string LocationName,
    decimal Quantity, decimal MinQuantity, bool IsLow);

public sealed record StockItemSummary(Guid Id, string Name, string? Sku, string? Category, string Unit, decimal Total, decimal MinQuantity, bool IsLow, decimal? UnitPrice);

public sealed record StockMovementDto(Guid Id, string ItemName, StockMovementType Type, decimal Quantity, string? FromLocation, string? ToLocation,
    string? EmployeeName, string? AssetNumber, DateTime EffectiveAt, string? DocumentNumber, string? Comment, DateTime CreatedAt);

/// <summary>Warehouse of consumables and spare parts (balances per location, movement journal).</summary>
public sealed class StockService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly IClock _clock;
    private readonly IAuditService _audit;

    public StockService(IAppDbContext db, IRegionScope scope, IClock clock, IAuditService audit) { _db = db; _scope = scope; _clock = clock; _audit = audit; }

    public async Task<IReadOnlyList<StockItemSummary>> SummaryAsync(string? search, CancellationToken ct)
    {
        var q = _db.StockItems.AsNoTracking().Where(i => !i.IsArchived);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var like = QueryableExtensions.LikePattern(search);
            q = q.Where(i => EF.Functions.ILike(i.Name, like) || (i.Sku != null && EF.Functions.ILike(i.Sku, like)));
        }
        var balances = _scope.Apply(_db.StockBalances.AsNoTracking(), b => b.Location!.RegionId);
        return await q.OrderBy(i => i.Name).Select(i => new StockItemSummary(i.Id, i.Name, i.Sku, i.Category, i.Unit,
            balances.Where(b => b.StockItemId == i.Id).Sum(b => (decimal?)b.Quantity) ?? 0, i.MinQuantity,
            (balances.Where(b => b.StockItemId == i.Id).Sum(b => (decimal?)b.Quantity) ?? 0) < i.MinQuantity, i.UnitPrice)).ToListAsync(ct);
    }

    public async Task<IReadOnlyList<StockBalanceDto>> BalancesAsync(Guid? itemId, Guid? locationId, CancellationToken ct)
    {
        var q = _scope.Apply(_db.StockBalances.AsNoTracking(), b => b.Location!.RegionId);
        if (itemId is not null) q = q.Where(b => b.StockItemId == itemId);
        if (locationId is not null) q = q.Where(b => b.LocationId == locationId);
        return await q.OrderBy(b => b.StockItem!.Name).ThenBy(b => b.Location!.Name).Select(b => new StockBalanceDto(b.StockItemId, b.StockItem!.Name, b.StockItem.Sku,
            b.StockItem.Category, b.StockItem.Unit, b.LocationId, b.Location!.FullPath ?? b.Location.Name, b.Quantity, b.StockItem.MinQuantity,
            b.Quantity < b.StockItem.MinQuantity)).ToListAsync(ct);
    }

    public async Task<PagedResult<StockMovementDto>> MovementsAsync(Guid? itemId, PagedRequest q, CancellationToken ct)
    {
        var query = _db.StockMovements.AsNoTracking().AsQueryable();
        if (itemId is not null) query = query.Where(m => m.StockItemId == itemId);
        return await query.OrderByDescending(m => m.EffectiveAt).ToPagedAsync(q, m => new StockMovementDto(m.Id, m.StockItem!.Name, m.Type, m.Quantity,
            _db.Locations.Where(l => l.Id == m.FromLocationId).Select(l => l.Name).FirstOrDefault(),
            _db.Locations.Where(l => l.Id == m.ToLocationId).Select(l => l.Name).FirstOrDefault(),
            _db.Employees.Where(e => e.Id == m.EmployeeId).Select(e => e.FullName).FirstOrDefault(),
            _db.Assets.Where(a => a.Id == m.AssetId).Select(a => a.InventoryNumber).FirstOrDefault(),
            m.EffectiveAt, m.DocumentNumber, m.Comment, m.CreatedAt), ct);
    }

    public async Task<StockMovementDto> MoveAsync(StockMovementRequest req, CancellationToken ct)
    {
        var item = await _db.StockItems.FirstOrDefaultAsync(i => i.Id == req.StockItemId, ct) ?? throw new NotFoundException("Номенклатура", req.StockItemId);
        switch (req.Type)
        {
            case StockMovementType.Receipt:
                if (req.ToLocationId is null) throw new ValidationFailedException("Укажите склад поступления");
                break;
            case StockMovementType.Issue:
            case StockMovementType.UsedInRepair:
                if (req.FromLocationId is null) throw new ValidationFailedException("Укажите склад списания");
                break;
            case StockMovementType.Transfer:
                if (req.FromLocationId is null || req.ToLocationId is null || req.FromLocationId == req.ToLocationId) throw new ValidationFailedException("Укажите разные склады");
                break;
            case StockMovementType.Adjustment:
                if (req.ToLocationId is null && req.FromLocationId is null) throw new ValidationFailedException("Укажите склад");
                break;
        }
        await using var tx = await _db.Database.BeginTransactionAsync(ct);
        async Task<StockBalance> Balance(Guid locationId)
        {
            var region = await _db.Locations.Where(l => l.Id == locationId).Select(l => (Guid?)l.RegionId).FirstOrDefaultAsync(ct) ?? throw new NotFoundException("Склад", locationId);
            _scope.EnsureAccess(region);
            var b = await _db.StockBalances.FirstOrDefaultAsync(x => x.StockItemId == item.Id && x.LocationId == locationId, ct);
            if (b is null) { b = new StockBalance { StockItemId = item.Id, LocationId = locationId }; _db.StockBalances.Add(b); }
            return b;
        }
        if (req.FromLocationId is not null && req.Type != StockMovementType.Adjustment)
        {
            var from = await Balance(req.FromLocationId.Value);
            if (from.Quantity < req.Quantity) throw new ConflictException("STOCK_INSUFFICIENT", $"Недостаточно остатка: {from.Quantity:0.###} {item.Unit}");
            from.Quantity -= req.Quantity;
        }
        if (req.ToLocationId is not null && req.Type is StockMovementType.Receipt or StockMovementType.Transfer)
            (await Balance(req.ToLocationId.Value)).Quantity += req.Quantity;
        if (req.Type == StockMovementType.Adjustment)
        {
            // Adjustment sets the counted quantity (stocktaking of consumables).
            var b = await Balance((req.ToLocationId ?? req.FromLocationId)!.Value);
            b.Quantity = req.Quantity;
        }
        var m = new StockMovement
        {
            StockItemId = item.Id, Type = req.Type, Quantity = req.Quantity, FromLocationId = req.FromLocationId, ToLocationId = req.ToLocationId,
            EmployeeId = req.EmployeeId, AssetId = req.AssetId, RepairId = req.RepairId, EffectiveAt = req.EffectiveAt?.ToUniversalTime() ?? _clock.UtcNow,
            DocumentNumber = req.DocumentNumber, Comment = req.Comment,
        };
        _db.StockMovements.Add(m);
        await _db.SaveChangesAsync(ct);
        await tx.CommitAsync(ct);
        return (await MovementsAsync(item.Id, new PagedRequest { PageSize = 50 }, ct)).Items.First(x => x.Id == m.Id);
    }
}
