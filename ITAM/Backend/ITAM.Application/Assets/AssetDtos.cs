using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Finance;

namespace ITAM.Application.Assets;

public sealed class AssetQuery : PagedRequest
{
    public Guid? AssetTypeId { get; set; }
    public Guid? CategoryId { get; set; }
    public Guid? StatusId { get; set; }
    public AssetStateKind? StatusKind { get; set; }
    public Guid? RegionId { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? ManufacturerId { get; set; }
    public Guid? SupplierId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public Guid? ParentAssetId { get; set; }
    public DateOnly? PurchaseFrom { get; set; }
    public DateOnly? PurchaseTo { get; set; }
    public DateOnly? WarrantyFrom { get; set; }
    public DateOnly? WarrantyTo { get; set; }
    public bool? WarrantyExpired { get; set; }
    public bool? NoResponsible { get; set; }
    public bool? Assigned { get; set; }
    /// <summary>Custom field filter: key=value (exact match on jsonb).</summary>
    public string? CustomFieldKey { get; set; }
    public string? CustomFieldValue { get; set; }
}

public sealed record AssetListItem(
    Guid Id, string InventoryNumber, string Name, Guid AssetTypeId, string? TypeName, string? CategoryName,
    string? ManufacturerName, string? Model, string? SerialNumber,
    Guid StatusId, string? StatusName, string? StatusColor, AssetStateKind StatusKind,
    Guid? EmployeeId, string? EmployeeName, Guid? DepartmentId, string? DepartmentName, Guid RegionId, string? RegionName,
    Guid? LocationId, string? LocationName, Guid? ResponsibleEmployeeId, string? ResponsibleName,
    DateOnly? PurchaseDate, decimal? PurchasePrice, string? Currency, DateOnly? WarrantyExpiration,
    string? Hostname, string? IpAddress, AssetCondition Condition, JsonElement? CustomFields, DateTime CreatedAt);

public sealed record AssetDto(
    Guid Id, string InventoryNumber, string Name, Guid AssetTypeId, string? TypeName, string? TypePrefix, Guid? CategoryId, string? CategoryName,
    Guid? ManufacturerId, string? ManufacturerName, string? Model, string? SerialNumber,
    Guid StatusId, string? StatusName, string? StatusColor, AssetStateKind StatusKind,
    Guid? EmployeeId, string? EmployeeName, string? EmployeeNumber, Guid? DepartmentId, string? DepartmentName,
    Guid RegionId, string? RegionName, Guid? LocationId, string? LocationName,
    Guid? ResponsibleEmployeeId, string? ResponsibleName, Guid? ParentAssetId, string? ParentAssetNumber,
    string? Hostname, string? IpAddress, string? MacAddress,
    DateOnly? PurchaseDate, decimal? PurchasePrice, string? Currency, Guid? SupplierId, string? SupplierName,
    Guid? ContractId, string? ContractNumber, string? InvoiceNumber, DateOnly? WarrantyExpiration,
    DepreciationMethod DepreciationMethod, int? UsefulLifeMonths, decimal? SalvageValue, DepreciationInfo? Depreciation,
    AssetCondition Condition, string? Notes, JsonElement? CustomFields, DateTime? LastInventoryAt,
    DateTime CreatedAt, DateTime? UpdatedAt, uint Version,
    CurrentAssignmentDto? CurrentAssignment, IReadOnlyList<ChildAssetDto> Components, OpenRepairDto? OpenRepair);

public sealed record CurrentAssignmentDto(Guid AssignmentId, Guid BatchId, string BatchNumber, DateTime EffectiveFrom, DateTime RecordedAt, DateOnly? ExpectedReturnDate, string? Accessories);
public sealed record ChildAssetDto(Guid Id, string InventoryNumber, string Name, string? StatusName);
public sealed record OpenRepairDto(Guid Id, string Number, string Status, DateTime OpenedAt);

public sealed class AssetInput
{
    [MaxLength(64)] public string? InventoryNumber { get; set; }
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    [Required] public Guid AssetTypeId { get; set; }
    public Guid? ManufacturerId { get; set; }
    [MaxLength(256)] public string? Model { get; set; }
    [MaxLength(128)] public string? SerialNumber { get; set; }
    /// <summary>Create only. Later changes go through operations.</summary>
    public Guid? StatusId { get; set; }
    /// <summary>Create only.</summary>
    public Guid? RegionId { get; set; }
    /// <summary>Create only.</summary>
    public Guid? LocationId { get; set; }
    /// <summary>Create only.</summary>
    public Guid? DepartmentId { get; set; }
    /// <summary>Create only: business date of registration (default: purchase date or now).</summary>
    public DateTime? RegisteredAt { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public Guid? ParentAssetId { get; set; }
    [MaxLength(128)] public string? Hostname { get; set; }
    [MaxLength(64)] public string? IpAddress { get; set; }
    [MaxLength(64)] public string? MacAddress { get; set; }
    public DateOnly? PurchaseDate { get; set; }
    [Range(0, 999999999999)] public decimal? PurchasePrice { get; set; }
    [MaxLength(8)] public string? Currency { get; set; }
    public Guid? SupplierId { get; set; }
    public Guid? ContractId { get; set; }
    [MaxLength(128)] public string? InvoiceNumber { get; set; }
    public DateOnly? WarrantyExpiration { get; set; }
    public DepreciationMethod DepreciationMethod { get; set; } = DepreciationMethod.StraightLine;
    [Range(1, 600)] public int? UsefulLifeMonths { get; set; }
    [Range(0, 999999999999)] public decimal? SalvageValue { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    [MaxLength(4000)] public string? Notes { get; set; }
    public Dictionary<string, JsonElement>? CustomFields { get; set; }
    public uint? Version { get; set; }
}

public sealed record AssetEventDto(
    Guid Id, long Sequence, AssetEventType EventType, bool AffectsState, DateTime EffectiveAt, DateTime RecordedAt, string? RecordedByName,
    OperationType? OperationType, Guid? OperationId, Guid? BatchId, string? Description, JsonElement? Data,
    string? StatusName, string? EmployeeName, string? DepartmentName, string? RegionName, string? LocationName,
    bool IsCancelled, string? CancelReason, bool IsBackdated);

public sealed record AssetStateAtDto(DateTime At, Guid? StatusId, string? StatusName, AssetStateKind? Kind, Guid? EmployeeId, string? EmployeeName,
    string? DepartmentName, string? RegionName, string? LocationName);

public sealed class AssetBulkStatusRequest
{
    [Required] public List<Guid> AssetIds { get; set; } = new();
    [Required] public Guid ToStatusId { get; set; }
    public DateTime? EffectiveAt { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
}

public sealed class AssetBulkEditRequest
{
    [Required] public List<Guid> AssetIds { get; set; } = new();
    public Guid? ResponsibleEmployeeId { get; set; }
    public bool SetResponsible { get; set; }
    public DateOnly? WarrantyExpiration { get; set; }
    public bool SetWarranty { get; set; }
    public Guid? SupplierId { get; set; }
    public bool SetSupplier { get; set; }
}
