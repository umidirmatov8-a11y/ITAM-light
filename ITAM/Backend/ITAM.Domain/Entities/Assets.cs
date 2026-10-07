using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

public class AssetCategory : LookupEntity
{
    public Guid? ParentId { get; set; }
    public AssetCategory? Parent { get; set; }
    public int? DefaultUsefulLifeMonths { get; set; }
}

public class AssetType : LookupEntity
{
    public Guid? CategoryId { get; set; }
    public AssetCategory? Category { get; set; }
    /// <summary>Inventory number prefix, e.g. LPT, MON.</summary>
    public string Prefix { get; set; } = string.Empty;
    /// <summary>Optional override of the global inventory number format.</summary>
    public string? InventoryNumberFormat { get; set; }
    public string? Icon { get; set; }
    public bool RequireSerialNumber { get; set; }
    public int? UsefulLifeMonths { get; set; }
}

public class AssetStatus : LookupEntity
{
    public AssetStateKind Kind { get; set; }
    public string? Color { get; set; }
    public bool IsSystem { get; set; }
    /// <summary>The status used when the system moves an asset into this kind automatically.</summary>
    public bool IsDefaultForKind { get; set; }
}

public class Manufacturer : LookupEntity
{
    public string? Website { get; set; }
    public string? SupportPhone { get; set; }
}

/// <summary>Suppliers, service centers and software vendors.</summary>
public class Supplier : LookupEntity
{
    public string? ContactPerson { get; set; }
    public string? Phone { get; set; }
    public string? Email { get; set; }
    public string? Address { get; set; }
    public string? TaxId { get; set; }
    public string? Website { get; set; }
    public bool IsSupplier { get; set; } = true;
    public bool IsServiceCenter { get; set; }
    public bool IsVendor { get; set; }
}

public class Contract : SoftDeletableEntity
{
    public string Number { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public ContractType Type { get; set; }
    public Guid? SupplierId { get; set; }
    public Supplier? Supplier { get; set; }
    public DateOnly? StartDate { get; set; }
    public DateOnly? EndDate { get; set; }
    public decimal? Amount { get; set; }
    public string? Currency { get; set; }
    public string? Notes { get; set; }
    public Guid? RegionId { get; set; }
}

public class Asset : SoftDeletableEntity, IRegionBound, IHasCustomFields
{
    public string InventoryNumber { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public Guid AssetTypeId { get; set; }
    public AssetType? AssetType { get; set; }
    public Guid? CategoryId { get; set; }
    public AssetCategory? Category { get; set; }
    public Guid? ManufacturerId { get; set; }
    public Manufacturer? Manufacturer { get; set; }
    public string? Model { get; set; }
    public string? SerialNumber { get; set; }

    // ---- Current state projection (derived from AssetEvents; never edited directly) ----
    public Guid StatusId { get; set; }
    public AssetStatus? Status { get; set; }
    public Guid? EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid? DepartmentId { get; set; }
    public Department? Department { get; set; }
    public Guid RegionId { get; set; }
    public Region? Region { get; set; }
    public Guid? LocationId { get; set; }
    public Location? Location { get; set; }

    /// <summary>Материально ответственное лицо.</summary>
    public Guid? ResponsibleEmployeeId { get; set; }
    public Employee? ResponsibleEmployee { get; set; }
    /// <summary>Kit / component relation (e.g. docking station belongs to a laptop).</summary>
    public Guid? ParentAssetId { get; set; }
    public Asset? ParentAsset { get; set; }

    public string? Hostname { get; set; }
    public string? IpAddress { get; set; }
    public string? MacAddress { get; set; }

    // ---- Financial ----
    public DateOnly? PurchaseDate { get; set; }
    public decimal? PurchasePrice { get; set; }
    public string? Currency { get; set; }
    public Guid? SupplierId { get; set; }
    public Supplier? Supplier { get; set; }
    public Guid? ContractId { get; set; }
    public Contract? Contract { get; set; }
    public string? InvoiceNumber { get; set; }
    public DateOnly? WarrantyExpiration { get; set; }
    public DepreciationMethod DepreciationMethod { get; set; } = DepreciationMethod.StraightLine;
    public int? UsefulLifeMonths { get; set; }
    public decimal? SalvageValue { get; set; }

    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    public string? Notes { get; set; }
    public string? CustomFields { get; set; }
    public DateTime? LastInventoryAt { get; set; }

    /// <summary>Optimistic concurrency token (PostgreSQL xmin).</summary>
    public uint Version { get; set; }

    Guid? IRegionBound.RegionId => RegionId;
}

/// <summary>
/// Append-only temporal history of an asset. State columns hold the asset state AFTER this event;
/// <see cref="Delta"/> holds the change itself so the stream can be replayed after a backdated insertion.
/// </summary>
public class AssetEvent : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public long Sequence { get; set; }
    public AssetEventType EventType { get; set; }
    public bool AffectsState { get; set; }
    public DateTime EffectiveAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public string? RecordedByName { get; set; }
    public OperationType? OperationType { get; set; }
    public Guid? OperationId { get; set; }
    public Guid? BatchId { get; set; }

    // State after the event
    public Guid? StatusId { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? RegionId { get; set; }
    public Guid? LocationId { get; set; }

    /// <summary>jsonb <c>AssetStateDelta</c>.</summary>
    public string? Delta { get; set; }
    /// <summary>jsonb human readable data (names at that time, from/to, comments).</summary>
    public string? Data { get; set; }
    public string? Description { get; set; }

    public bool IsCancelled { get; set; }
    public DateTime? CancelledAt { get; set; }
    public Guid? CancelledById { get; set; }
    public string? CancelReason { get; set; }
}

public class CustomFieldDefinition : AuditableEntity, IArchivable
{
    public CustomFieldEntity EntityType { get; set; }
    /// <summary>Optional binding to an asset type: the field is shown only for assets of this type.</summary>
    public Guid? AssetTypeId { get; set; }
    public AssetType? AssetType { get; set; }
    /// <summary>Stable key used in jsonb and in document placeholders (Asset.Custom.&lt;Key&gt;).</summary>
    public string Key { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public CustomFieldType DataType { get; set; }
    /// <summary>jsonb array of options for Dropdown / MultiSelect.</summary>
    public string? Options { get; set; }
    public bool IsRequired { get; set; }
    public bool IsSearchable { get; set; }
    public bool ShowInList { get; set; }
    public string? DefaultValue { get; set; }
    public string? HelpText { get; set; }
    public string? Group { get; set; }
    public int SortOrder { get; set; }
    public bool IsArchived { get; set; }
}

/// <summary>Atomic counters for inventory/operation/document numbers.</summary>
public class NumberSequence : ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public string Key { get; set; } = string.Empty;
    public long NextValue { get; set; } = 1;
}
