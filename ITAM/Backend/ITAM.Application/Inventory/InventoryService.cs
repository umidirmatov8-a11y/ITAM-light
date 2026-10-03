using System.ComponentModel.DataAnnotations;
using System.Text.RegularExpressions;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Inventory;

public sealed class InventoryCreateRequest
{
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    public Guid? RegionId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? DepartmentId { get; set; }
    [MaxLength(2000)] public string? Comment { get; set; }
}

public sealed class InventoryScanRequest
{
    /// <summary>Inventory number, serial number, asset id or the QR URL (…/assets/{id}).</summary>
    [Required, MaxLength(512)] public string Code { get; set; } = string.Empty;
    public Guid? FoundLocationId { get; set; }
    public AssetCondition? Condition { get; set; }
    [MaxLength(1000)] public string? Comment { get; set; }
}

public sealed class InventoryItemUpdate
{
    public InventoryItemResult Result { get; set; }
    public Guid? FoundLocationId { get; set; }
    public AssetCondition? Condition { get; set; }
    [MaxLength(1000)] public string? Comment { get; set; }
}

public sealed record InventoryListItem(Guid Id, string Number, string Name, string? RegionName, string? LocationName, InventoryCampaignStatus Status,
    DateTime? StartedAt, DateTime? CompletedAt, int Total, int Checked, int Found, int Missing, int Misplaced, int Unexpected);

public sealed record InventoryItemDto(Guid Id, Guid AssetId, string InventoryNumber, string AssetName, string? SerialNumber, string? ExpectedLocation,
    string? ExpectedEmployee, string? FoundLocation, InventoryItemResult Result, DateTime? CheckedAt, string? CheckedByName, AssetCondition? Condition, string? Comment);

public sealed partial class InventoryService
{
    private readonly IAppDbContext _db;
    private readonly IRegionScope _scope;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly INumberingService _numbering;
    private readonly AssetTemporalStore _temporal;
    private readonly IAuditService _audit;

    public InventoryService(IAppDbContext db, IRegionScope scope, ICurrentUser user, IClock clock, INumberingService numbering, AssetTemporalStore temporal, IAuditService audit)
    {
        _db = db; _scope = scope; _user = user; _clock = clock; _numbering = numbering; _temporal = temporal; _audit = audit;
    }

    private IQueryable<InventoryCampaign> Visible() => _scope.Apply(_db.InventoryCampaigns.AsQueryable(), c => c.RegionId, includeNull: _scope.IsUnrestricted);

    private System.Linq.Expressions.Expression<Func<InventoryCampaign, InventoryListItem>> Projection() => c => new InventoryListItem(c.Id, c.Number, c.Name,
        _db.Regions.Where(r => r.Id == c.RegionId).Select(r => r.Name).FirstOrDefault(),
        _db.Locations.Where(r => r.Id == c.LocationId).Select(r => r.FullPath ?? r.Name).FirstOrDefault(),
        c.Status, c.StartedAt, c.CompletedAt, c.Items.Count, c.Items.Count(i => i.Result != InventoryItemResult.Pending),
        c.Items.Count(i => i.Result == InventoryItemResult.Found), c.Items.Count(i => i.Result == InventoryItemResult.Missing),
        c.Items.Count(i => i.Result == InventoryItemResult.Misplaced), c.Items.Count(i => i.Result == InventoryItemResult.Unexpected));

    public async Task<PagedResult<InventoryListItem>> ListAsync(PagedRequest q, CancellationToken ct)
    {
        var query = Visible().AsNoTracking();
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(c => EF.Functions.ILike(c.Name, like) || EF.Functions.ILike(c.Number, like));
        }
        return await query.OrderByDescending(c => c.CreatedAt).ToPagedAsync(q, Projection(), ct);
    }

    public async Task<InventoryListItem> GetAsync(Guid id, CancellationToken ct)
        => await Visible().AsNoTracking().Where(c => c.Id == id).Select(Projection()).FirstOrDefaultAsync(ct)
           ?? throw new NotFoundException("Инвентаризация", id);

    public async Task<InventoryListItem> CreateAsync(InventoryCreateRequest req, CancellationToken ct)
    {
        if (req.RegionId is not null) _scope.EnsureAccess(req.RegionId);
        else if (!_scope.IsUnrestricted) throw new ValidationFailedException("Укажите регион");
        var assets = _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId)
            .Where(a => a.Status!.Kind != AssetStateKind.Disposed && a.Status.Kind != AssetStateKind.WrittenOff && a.Status.Kind != AssetStateKind.Archived);
        if (req.RegionId is not null) assets = assets.Where(a => a.RegionId == req.RegionId);
        if (req.DepartmentId is not null) assets = assets.Where(a => a.DepartmentId == req.DepartmentId);
        if (req.LocationId is not null)
        {
            var all = await _db.Locations.AsNoTracking().Select(l => new { l.Id, l.ParentId }).ToListAsync(ct);
            var set = new HashSet<Guid> { req.LocationId.Value };
            bool added;
            do { added = false; foreach (var l in all) if (l.ParentId is not null && set.Contains(l.ParentId.Value) && set.Add(l.Id)) added = true; } while (added);
            var ids = set.ToList();
            assets = assets.Where(a => a.LocationId != null && ids.Contains(a.LocationId.Value));
        }
        var list = await assets.Select(a => new { a.Id, a.LocationId, a.EmployeeId }).ToListAsync(ct);
        var c = new InventoryCampaign
        {
            Number = await _numbering.NextAsync(x => x.InventoryFormat, "inventory", ct: ct),
            Name = req.Name.Trim(),
            RegionId = req.RegionId,
            LocationId = req.LocationId,
            DepartmentId = req.DepartmentId,
            Comment = req.Comment,
            Status = InventoryCampaignStatus.InProgress,
            StartedAt = _clock.UtcNow,
        };
        foreach (var a in list)
            c.Items.Add(new InventoryCampaignItem { AssetId = a.Id, ExpectedLocationId = a.LocationId, ExpectedEmployeeId = a.EmployeeId, Result = InventoryItemResult.Pending });
        _db.InventoryCampaigns.Add(c);
        _audit.Log("inventory.start", nameof(InventoryCampaign), c.Id, c.Number, null, new { c.Name, items = list.Count });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(c.Id, ct);
    }

    public async Task<PagedResult<InventoryItemDto>> ItemsAsync(Guid id, InventoryItemResult? result, PagedRequest q, CancellationToken ct)
    {
        if (!await Visible().AnyAsync(c => c.Id == id, ct)) throw new NotFoundException("Инвентаризация", id);
        var query = _db.InventoryCampaignItems.AsNoTracking().Where(i => i.CampaignId == id);
        if (result is not null) query = query.Where(i => i.Result == result);
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(i => EF.Functions.ILike(i.Asset!.InventoryNumber, like) || EF.Functions.ILike(i.Asset.Name, like)
                                     || (i.Asset.SerialNumber != null && EF.Functions.ILike(i.Asset.SerialNumber, like)));
        }
        return await query.OrderBy(i => i.Result).ThenBy(i => i.Asset!.InventoryNumber).ToPagedAsync(q, i => new InventoryItemDto(i.Id, i.AssetId,
            i.Asset!.InventoryNumber, i.Asset.Name, i.Asset.SerialNumber,
            _db.Locations.Where(l => l.Id == i.ExpectedLocationId).Select(l => l.FullPath ?? l.Name).FirstOrDefault(),
            _db.Employees.Where(e => e.Id == i.ExpectedEmployeeId).Select(e => e.FullName).FirstOrDefault(),
            _db.Locations.Where(l => l.Id == i.FoundLocationId).Select(l => l.FullPath ?? l.Name).FirstOrDefault(),
            i.Result, i.CheckedAt, i.CheckedByName, i.Condition, i.Comment), ct);
    }

    [GeneratedRegex(@"/assets/(?<id>[0-9a-fA-F\-]{36})")]
    private static partial Regex AssetUrlRegex();

    public async Task<InventoryItemDto> ScanAsync(Guid id, InventoryScanRequest req, CancellationToken ct)
    {
        var c = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Инвентаризация", id);
        if (c.Status != InventoryCampaignStatus.InProgress) throw new BusinessException("INVENTORY_CLOSED", "Инвентаризация завершена");
        var code = req.Code.Trim();
        Guid? assetId = null;
        var m = AssetUrlRegex().Match(code);
        if (m.Success) assetId = Guid.Parse(m.Groups["id"].Value);
        else if (Guid.TryParse(code, out var g)) assetId = g;
        var assets = _scope.Apply(_db.Assets.AsQueryable(), a => a.RegionId);
        var asset = assetId is not null
            ? await assets.FirstOrDefaultAsync(a => a.Id == assetId, ct)
            : await assets.FirstOrDefaultAsync(a => a.InventoryNumber == code.ToUpper(), ct) ?? await assets.FirstOrDefaultAsync(a => a.SerialNumber == code, ct);
        if (asset is null) throw new NotFoundException("Актив", code);

        var item = await _db.InventoryCampaignItems.FirstOrDefaultAsync(i => i.CampaignId == id && i.AssetId == asset.Id, ct);
        if (item is null)
        {
            item = new InventoryCampaignItem { CampaignId = id, AssetId = asset.Id, ExpectedLocationId = null, Result = InventoryItemResult.Unexpected };
            _db.InventoryCampaignItems.Add(item);
        }
        else
        {
            var foundLoc = req.FoundLocationId ?? c.LocationId;
            item.Result = item.ExpectedLocationId is not null && req.FoundLocationId is not null && req.FoundLocationId != item.ExpectedLocationId
                ? InventoryItemResult.Misplaced : InventoryItemResult.Found;
            if (foundLoc is not null && item.FoundLocationId is null) item.FoundLocationId = foundLoc;
        }
        if (req.FoundLocationId is not null) item.FoundLocationId = req.FoundLocationId;
        item.CheckedAt = _clock.UtcNow;
        item.CheckedById = _user.UserId;
        item.CheckedByName = _user.DisplayName ?? _user.UserName;
        item.Condition = req.Condition ?? item.Condition;
        item.Comment = req.Comment ?? item.Comment;
        await _db.SaveChangesAsync(ct);
        return (await ItemsAsync(id, null, new PagedRequest { Search = asset.InventoryNumber, PageSize = 10 }, ct)).Items.First(i => i.Id == item.Id);
    }

    public async Task<InventoryItemDto> UpdateItemAsync(Guid id, Guid itemId, InventoryItemUpdate req, CancellationToken ct)
    {
        var c = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Инвентаризация", id);
        if (c.Status != InventoryCampaignStatus.InProgress) throw new BusinessException("INVENTORY_CLOSED", "Инвентаризация завершена");
        var item = await _db.InventoryCampaignItems.Include(i => i.Asset).FirstOrDefaultAsync(i => i.Id == itemId && i.CampaignId == id, ct) ?? throw new NotFoundException("Позиция", itemId);
        item.Result = req.Result;
        item.FoundLocationId = req.FoundLocationId ?? item.FoundLocationId;
        item.Condition = req.Condition ?? item.Condition;
        item.Comment = req.Comment;
        item.CheckedAt = req.Result == InventoryItemResult.Pending ? null : _clock.UtcNow;
        item.CheckedById = _user.UserId;
        item.CheckedByName = _user.DisplayName ?? _user.UserName;
        await _db.SaveChangesAsync(ct);
        return (await ItemsAsync(id, null, new PagedRequest { Search = item.Asset!.InventoryNumber, PageSize = 10 }, ct)).Items.First(i => i.Id == item.Id);
    }

    public async Task<InventoryListItem> CompleteAsync(Guid id, CancellationToken ct)
    {
        var c = await Visible().Include(x => x.Items).FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Инвентаризация", id);
        if (c.Status != InventoryCampaignStatus.InProgress) throw new BusinessException("INVENTORY_CLOSED", "Инвентаризация уже завершена");
        var now = _clock.UtcNow;
        foreach (var i in c.Items)
        {
            if (i.Result == InventoryItemResult.Pending) i.Result = InventoryItemResult.Missing;
            var text = i.Result switch
            {
                InventoryItemResult.Found => "найден",
                InventoryItemResult.Misplaced => "найден в другом месте",
                InventoryItemResult.Unexpected => "излишек",
                _ => "не найден"
            };
            _temporal.AddInfoEvent(i.AssetId, AssetEventType.InventoryChecked, i.CheckedAt ?? now, $"Инвентаризация {c.Number}: {text}", new { campaign = c.Number, result = i.Result.ToString(), i.Comment }, c.Id);
        }
        var foundIds = c.Items.Where(i => i.Result is InventoryItemResult.Found or InventoryItemResult.Misplaced or InventoryItemResult.Unexpected).Select(i => i.AssetId).ToList();
        await _db.Assets.Where(a => foundIds.Contains(a.Id)).ExecuteUpdateAsync(s => s.SetProperty(a => a.LastInventoryAt, now), ct);
        c.Status = InventoryCampaignStatus.Completed;
        c.CompletedAt = now;
        _audit.Log("inventory.complete", nameof(InventoryCampaign), c.Id, c.Number, null, new
        {
            total = c.Items.Count, found = c.Items.Count(i => i.Result == InventoryItemResult.Found), missing = c.Items.Count(i => i.Result == InventoryItemResult.Missing)
        });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task CancelAsync(Guid id, CancellationToken ct)
    {
        var c = await Visible().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Инвентаризация", id);
        c.Status = InventoryCampaignStatus.Cancelled;
        await _db.SaveChangesAsync(ct);
    }
}
