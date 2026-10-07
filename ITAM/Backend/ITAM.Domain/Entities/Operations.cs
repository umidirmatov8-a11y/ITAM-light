using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>Act-level operation: one issue/return/transfer act covering one or more assets.</summary>
public class OperationBatch : AuditableEntity, IRegionBound
{
    public string Number { get; set; } = string.Empty;
    public OperationType Type { get; set; }
    public DateTime EffectiveAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public Guid? RegionId { get; set; }
    public string? Comment { get; set; }
    /// <summary>jsonb snapshot of the employee (name, number, department, position, region, location) at operation time.</summary>
    public string? EmployeeSnapshot { get; set; }
    public string? ResponsibleSnapshot { get; set; }
    public bool IsBackdated { get; set; }
    public bool IsCancelled { get; set; }
    public DateTime? CancelledAt { get; set; }
    public Guid? CancelledById { get; set; }
    public string? CancelReason { get; set; }
    public SignatureStatus EmployeeSignatureStatus { get; set; } = SignatureStatus.Pending;
    public SignatureStatus ResponsibleSignatureStatus { get; set; } = SignatureStatus.Pending;
    public DateTime? SignedAt { get; set; }
    public SignatureMethod SignatureMethod { get; set; } = SignatureMethod.None;
    public List<Assignment> Assignments { get; set; } = new();
    public List<AssetReturn> Returns { get; set; } = new();
    public List<AssetTransfer> Transfers { get; set; } = new();
    public List<AssetStatusChange> StatusChanges { get; set; } = new();
}

public class Assignment : AuditableEntity
{
    public Guid BatchId { get; set; }
    public OperationBatch? Batch { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public Guid EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    /// <summary>Business date the asset was handed over.</summary>
    public DateTime EffectiveFrom { get; set; }
    /// <summary>Business date the asset was returned (null = still assigned).</summary>
    public DateTime? EffectiveTo { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    public string? Accessories { get; set; }
    public string? Comment { get; set; }
    public DateOnly? ExpectedReturnDate { get; set; }
    public Guid? ReturnId { get; set; }
    public string? CloseReason { get; set; }
    public string? AssetSnapshot { get; set; }
    public string? EmployeeSnapshot { get; set; }
    public bool IsCancelled { get; set; }
}

public class AssetReturn : AuditableEntity
{
    public Guid BatchId { get; set; }
    public OperationBatch? Batch { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public Guid EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid? AssignmentId { get; set; }
    public DateTime EffectiveAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    public string? Accessories { get; set; }
    public string? Damage { get; set; }
    public string? MissingItems { get; set; }
    public string? Comment { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public Guid? ResultStatusId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? RepairId { get; set; }
    public string? AssetSnapshot { get; set; }
    public string? EmployeeSnapshot { get; set; }
    public bool IsCancelled { get; set; }
}

public class AssetTransfer : AuditableEntity
{
    public Guid BatchId { get; set; }
    public OperationBatch? Batch { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public DateTime EffectiveAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public Guid? FromEmployeeId { get; set; }
    public Guid? FromDepartmentId { get; set; }
    public Guid? FromRegionId { get; set; }
    public Guid? FromLocationId { get; set; }
    public Guid? ToEmployeeId { get; set; }
    public Guid? ToDepartmentId { get; set; }
    public Guid? ToRegionId { get; set; }
    public Guid? ToLocationId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public string? Reason { get; set; }
    public string? Comment { get; set; }
    /// <summary>jsonb { from: {...names}, to: {...names} }.</summary>
    public string? Snapshot { get; set; }
    /// <summary>Employee-to-employee transfer: the assignment that was closed and the one that was opened.</summary>
    public Guid? ClosedAssignmentId { get; set; }
    public Guid? NewAssignmentId { get; set; }
    public bool IsCancelled { get; set; }
}

/// <summary>Generic status operation (reserve, lost, stolen, dispose, write-off, archive, restore).</summary>
public class AssetStatusChange : AuditableEntity
{
    public Guid? BatchId { get; set; }
    public OperationBatch? Batch { get; set; }
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public string Number { get; set; } = string.Empty;
    public DateTime EffectiveAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public Guid FromStatusId { get; set; }
    public Guid ToStatusId { get; set; }
    public Guid? ReservedForEmployeeId { get; set; }
    public DateOnly? ReservedUntil { get; set; }
    public string? Reason { get; set; }
    public string? Comment { get; set; }
    public string? DisposalMethod { get; set; }
    public Guid? ClosedAssignmentId { get; set; }
    public string? Snapshot { get; set; }
    public bool IsCancelled { get; set; }
}

public class RepairStatus : LookupEntity
{
    public RepairStage Stage { get; set; }
    public string? Color { get; set; }
    public bool IsSystem { get; set; }
    public bool IsClosed => Stage is RepairStage.Returned or RepairStage.Cancelled;
}

public class Repair : SoftDeletableEntity, IRegionBound, IHasCustomFields
{
    public string Number { get; set; } = string.Empty;
    public Guid AssetId { get; set; }
    public Asset? Asset { get; set; }
    public Guid StatusId { get; set; }
    public RepairStatus? Status { get; set; }
    public DateTime OpenedAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public DateTime? SentAt { get; set; }
    public Guid? ServiceCenterId { get; set; }
    public Supplier? ServiceCenter { get; set; }
    public string Problem { get; set; } = string.Empty;
    public string? Diagnosis { get; set; }
    public string? RepairDescription { get; set; }
    public string? Parts { get; set; }
    public decimal? Cost { get; set; }
    public string? Currency { get; set; }
    public bool IsWarranty { get; set; }
    public DateOnly? ExpectedReturnDate { get; set; }
    public DateTime? ActualReturnAt { get; set; }
    public string? Technician { get; set; }
    public string? Comment { get; set; }
    /// <summary>Employee who reported/held the asset when the repair was opened.</summary>
    public Guid? EmployeeId { get; set; }
    public Guid? PreviousStatusId { get; set; }
    /// <summary>Asset status set when the repair is closed (null = previous status / available).</summary>
    public Guid? ReturnStatusId { get; set; }
    /// <summary>AssetEvent that moved the asset into repair (null when the asset was not moved by this repair).</summary>
    public Guid? OpenEventId { get; set; }
    public Guid? CloseEventId { get; set; }
    public Guid? RegionId { get; set; }
    public string? AssetSnapshot { get; set; }
    public string? CustomFields { get; set; }
    public uint Version { get; set; }
    public List<RepairStatusHistory> History { get; set; } = new();
}

public class RepairStatusHistory : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid RepairId { get; set; }
    public Guid StatusId { get; set; }
    public string StatusName { get; set; } = string.Empty;
    public DateTime ChangedAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public string? RecordedByName { get; set; }
    public string? Comment { get; set; }
}
