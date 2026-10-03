using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Enums;

namespace ITAM.Application.Employees;

public sealed class EmployeeQuery : PagedRequest
{
    public Guid? RegionId { get; set; }
    public Guid? DepartmentId { get; set; }
    public bool IncludeSubDepartments { get; set; } = true;
    public Guid? PositionId { get; set; }
    public Guid? StatusId { get; set; }
    public EmployeeStatusKind? StatusKind { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? ManagerId { get; set; }
    public bool? HasAssets { get; set; }
    public DateOnly? HiredFrom { get; set; }
    public DateOnly? HiredTo { get; set; }
    /// <summary>Hide terminated/archived employees unless requested.</summary>
    public bool ActiveOnly { get; set; }
}

public sealed record EmployeeListItem(
    Guid Id, string EmployeeNumber, string FullName, string? Login, string? Email, string? Phone,
    Guid? PositionId, string? PositionName, Guid? DepartmentId, string? DepartmentName, Guid RegionId, string? RegionName,
    Guid? LocationId, string? LocationName, Guid StatusId, string? StatusName, string? StatusColor, EmployeeStatusKind StatusKind,
    DateOnly? HireDate, DateOnly? TerminationDate, int AssetCount, Guid? PhotoFileId);

public sealed record EmployeeDto(
    Guid Id, string EmployeeNumber, string LastName, string FirstName, string? MiddleName, string FullName,
    string? Login, string? Email, string? Phone,
    Guid? PositionId, string? PositionName, Guid? DepartmentId, string? DepartmentName, string? DepartmentPath,
    Guid RegionId, string? RegionName, Guid? LocationId, string? LocationName, Guid? RoomId, string? RoomName,
    Guid? ManagerId, string? ManagerName, DateOnly? HireDate, DateOnly? TerminationDate,
    Guid StatusId, string? StatusName, string? StatusColor, EmployeeStatusKind StatusKind,
    string? Comment, Guid? PhotoFileId, JsonElement? CustomFields, string? ExternalId,
    DateTime CreatedAt, DateTime? UpdatedAt, uint Version, int AssetCount, int LicenseCount, int AccessCount);

public sealed class EmployeeInput
{
    [MaxLength(64)] public string? EmployeeNumber { get; set; }
    [Required, MaxLength(128)] public string LastName { get; set; } = string.Empty;
    [Required, MaxLength(128)] public string FirstName { get; set; } = string.Empty;
    [MaxLength(128)] public string? MiddleName { get; set; }
    [MaxLength(128)] public string? Login { get; set; }
    [EmailAddress, MaxLength(256)] public string? Email { get; set; }
    [MaxLength(64)] public string? Phone { get; set; }
    public Guid? PositionId { get; set; }
    public Guid? DepartmentId { get; set; }
    [Required] public Guid RegionId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? RoomId { get; set; }
    public Guid? ManagerId { get; set; }
    public DateOnly? HireDate { get; set; }
    public Guid? StatusId { get; set; }
    [MaxLength(4000)] public string? Comment { get; set; }
    public Dictionary<string, JsonElement>? CustomFields { get; set; }
    /// <summary>Effective date of an organizational change (department/position/region/office). Default: now.</summary>
    public DateTime? OrgChangeEffectiveAt { get; set; }
    [MaxLength(1000)] public string? OrgChangeReason { get; set; }
    public bool StartOnboarding { get; set; }
    public Guid? OnboardingTemplateId { get; set; }
    public uint? Version { get; set; }
}

public sealed class TerminateRequest
{
    [Required] public DateOnly TerminationDate { get; set; }
    [MaxLength(1000)] public string? Reason { get; set; }
    /// <summary>Terminate even though open items remain (requires employees.terminate and is audited).</summary>
    public bool Force { get; set; }
    public bool StartOffboarding { get; set; } = true;
    public Guid? OffboardingTemplateId { get; set; }
}

public sealed class EmployeeBulkRequest
{
    [Required] public List<Guid> Ids { get; set; } = new();
    /// <summary>changeRegion | changeDepartment | changePosition | changeStatus | archive</summary>
    [Required] public string Action { get; set; } = string.Empty;
    public Guid? Value { get; set; }
}

public sealed record BulkResult(int Succeeded, IReadOnlyList<BulkError> Errors);
public sealed record BulkError(Guid Id, string? Name, string Code, string Message);

public sealed record OpenItemsDto(
    IReadOnlyList<OpenAssetItem> Assets,
    IReadOnlyList<OpenLicenseItem> Licenses,
    IReadOnlyList<OpenAccessItem> Accesses,
    IReadOnlyList<OpenRepairItem> Repairs,
    IReadOnlyList<OpenDocumentItem> UnsignedDocuments,
    IReadOnlyList<OpenChecklistItem> Checklists)
{
    public int Total => Assets.Count + Licenses.Count + Accesses.Count + Repairs.Count;
}

public sealed record OpenAssetItem(Guid AssetId, string InventoryNumber, string Name, string? Type, DateTime? AssignedAt, Guid? AssignmentId);
public sealed record OpenLicenseItem(Guid AssignmentId, Guid LicenseId, string LicenseName, string? Software, DateTime AssignedAt);
public sealed record OpenAccessItem(Guid Id, string System, string? Username, string? Level, AccessStatus Status, DateTime GrantedAt);
public sealed record OpenRepairItem(Guid Id, string Number, string AssetInventoryNumber, string Status, DateTime OpenedAt);
public sealed record OpenDocumentItem(Guid Id, string Number, string Title, DateTime CreatedAt);
public sealed record OpenChecklistItem(Guid Id, string Title, ChecklistKind Kind, int Done, int Total);

public sealed record EmployeeOrgHistoryDto(Guid Id, DateTime EffectiveFrom, DateTime? EffectiveTo, DateTime RecordedAt,
    string? Department, string? Position, string? Region, string? Location, string? Manager, string? Status, string? Reason);
