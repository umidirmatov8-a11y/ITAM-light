using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>Stocktaking campaign: expected assets of a region/location are checked (QR scanning or manual).</summary>
public class InventoryCampaign : AuditableEntity, IRegionBound
{
    public string Number { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public Guid? RegionId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? DepartmentId { get; set; }
    public InventoryCampaignStatus Status { get; set; }
    public DateTime? StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public string? Comment { get; set; }
    public List<InventoryCampaignItem> Items { get; set; } = new();
}

public class InventoryCampaignItem : Entity
{
    public Guid CampaignId { get; set; }
    public InventoryCampaign? Campaign { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public Guid? ExpectedLocationId { get; set; }
    public Guid? ExpectedEmployeeId { get; set; }
    public Guid? FoundLocationId { get; set; }
    public InventoryItemResult Result { get; set; }
    public DateTime? CheckedAt { get; set; }
    public Guid? CheckedById { get; set; }
    public string? CheckedByName { get; set; }
    public AssetCondition? Condition { get; set; }
    public string? Comment { get; set; }
}

/// <summary>Consumables and spare parts (cartridges, cables, RAM modules, disks ...).</summary>
public class StockItem : LookupEntity
{
    public string? Sku { get; set; }
    public string? Category { get; set; }
    public string Unit { get; set; } = "шт";
    public decimal MinQuantity { get; set; }
    public decimal? UnitPrice { get; set; }
}

public class StockBalance : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid StockItemId { get; set; }
    public StockItem? StockItem { get; set; }
    public Guid LocationId { get; set; }
    public Location? Location { get; set; }
    public decimal Quantity { get; set; }
    public uint Version { get; set; }
}

public class StockMovement : AuditableEntity
{
    public Guid StockItemId { get; set; }
    public StockItem? StockItem { get; set; }
    public StockMovementType Type { get; set; }
    public decimal Quantity { get; set; }
    public Guid? FromLocationId { get; set; }
    public Guid? ToLocationId { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public Guid? RepairId { get; set; }
    public DateTime EffectiveAt { get; set; }
    public string? DocumentNumber { get; set; }
    public string? Comment { get; set; }
}
