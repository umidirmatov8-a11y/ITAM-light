using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using ITAM.Domain.Enums;

namespace ITAM.Application.Operations;

public sealed class IssueRequest
{
    [Required] public Guid EmployeeId { get; set; }
    [Required, MinLength(1)] public List<Guid> AssetIds { get; set; } = new();
    /// <summary>Business date/time of the hand-over (may be in the past with assets.backdate).</summary>
    public DateTime? EffectiveAt { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    [MaxLength(2000)] public string? Accessories { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    /// <summary>Temporary issue (loan): expected return date.</summary>
    public DateOnly? ExpectedReturnDate { get; set; }
    /// <summary>
    /// Historical record: the asset was issued at <see cref="EffectiveAt"/> and already returned at this date.
    /// Issue and return are inserted into the history together (requires assets.backdate).
    /// </summary>
    public DateTime? ReturnedAt { get; set; }
    public Guid? ReturnLocationId { get; set; }
    public bool GenerateDocument { get; set; }
    public Guid? TemplateId { get; set; }
}

public sealed class ReturnItem
{
    [Required] public Guid AssetId { get; set; }
    public AssetCondition Condition { get; set; } = AssetCondition.Good;
    [MaxLength(2000)] public string? Accessories { get; set; }
    [MaxLength(2000)] public string? Damage { get; set; }
    [MaxLength(2000)] public string? MissingItems { get; set; }
    /// <summary>Send the returned asset to repair (status In Repair + repair record).</summary>
    public bool SendToRepair { get; set; }
    [MaxLength(4000)] public string? RepairProblem { get; set; }
    /// <summary>Explicit resulting status (must be of kind InStock); default: available.</summary>
    public Guid? ResultStatusId { get; set; }
}

public sealed class ReturnRequest
{
    [Required] public Guid EmployeeId { get; set; }
    [Required, MinLength(1)] public List<ReturnItem> Items { get; set; } = new();
    public DateTime? EffectiveAt { get; set; }
    /// <summary>Warehouse / office where the asset is returned to.</summary>
    public Guid? LocationId { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public bool GenerateDocument { get; set; }
    public Guid? TemplateId { get; set; }
}

public sealed class TransferRequest
{
    [Required, MinLength(1)] public List<Guid> AssetIds { get; set; } = new();
    public DateTime? EffectiveAt { get; set; }
    /// <summary>Employee-to-employee transfer (asset must be assigned).</summary>
    public Guid? ToEmployeeId { get; set; }
    public Guid? ToDepartmentId { get; set; }
    public Guid? ToRegionId { get; set; }
    public Guid? ToLocationId { get; set; }
    public bool ClearDepartment { get; set; }
    public Guid? ResponsibleEmployeeId { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public bool GenerateDocument { get; set; }
    public Guid? TemplateId { get; set; }
}

public sealed class StatusChangeRequest
{
    [Required, MinLength(1)] public List<Guid> AssetIds { get; set; } = new();
    [Required] public Guid ToStatusId { get; set; }
    public DateTime? EffectiveAt { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public Guid? ReservedForEmployeeId { get; set; }
    public DateOnly? ReservedUntil { get; set; }
    [MaxLength(256)] public string? DisposalMethod { get; set; }
    public bool GenerateDocument { get; set; }
    public Guid? TemplateId { get; set; }
}

public sealed class CancelOperationRequest
{
    [Required, MinLength(3), MaxLength(1000)] public string Reason { get; set; } = string.Empty;
}

public sealed record OperationResult(Guid BatchId, string Number, OperationType Type, int AssetCount, bool IsBackdated, Guid? DocumentId, IReadOnlyList<Guid>? RepairIds = null);

public sealed record BatchListItem(Guid Id, string Number, OperationType Type, DateTime EffectiveAt, DateTime RecordedAt, string? CreatedBy,
    Guid? EmployeeId, string? EmployeeName, int AssetCount, string? AssetNumbers, bool IsBackdated, bool IsCancelled,
    SignatureStatus EmployeeSignatureStatus, string? Comment, int DocumentCount);

public sealed record BatchDto(Guid Id, string Number, OperationType Type, DateTime EffectiveAt, DateTime RecordedAt, string? CreatedBy,
    Guid? EmployeeId, string? EmployeeName, JsonElement? EmployeeSnapshot, Guid? ResponsibleEmployeeId, JsonElement? ResponsibleSnapshot,
    string? Comment, bool IsBackdated, bool IsCancelled, string? CancelReason, DateTime? CancelledAt,
    SignatureStatus EmployeeSignatureStatus, SignatureStatus ResponsibleSignatureStatus, DateTime? SignedAt, SignatureMethod SignatureMethod,
    IReadOnlyList<BatchLineDto> Lines, IReadOnlyList<BatchDocumentDto> Documents);

public sealed record BatchLineDto(Guid Id, Guid AssetId, string InventoryNumber, string AssetName, string? SerialNumber, AssetCondition? Condition,
    string? Accessories, string? Damage, string? MissingItems, string? From, string? To, string? Comment, DateTime? EffectiveTo, bool IsCancelled);

public sealed record BatchDocumentDto(Guid Id, string Number, string Title, DateTime CreatedAt, Guid? DocxFileId, Guid? PdfFileId, int TemplateVersion);

public sealed class BatchQuery : ITAM.Application.Common.PagedRequest
{
    public OperationType? Type { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public DateTime? From { get; set; }
    public DateTime? To { get; set; }
    public bool? Backdated { get; set; }
}

public sealed class SignatureUpdate
{
    public SignatureStatus EmployeeSignatureStatus { get; set; }
    public SignatureStatus ResponsibleSignatureStatus { get; set; }
    public SignatureMethod SignatureMethod { get; set; }
    public DateTime? SignedAt { get; set; }
}
