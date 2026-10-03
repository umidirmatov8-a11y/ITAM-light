using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>Information system an employee can have access to (AD, VPN, ERP, CRM, ...).</summary>
public class AccessSystem : LookupEntity
{
    public string? Owner { get; set; }
    public string? Criticality { get; set; }
    /// <summary>Months between access recertifications; null = no periodic review.</summary>
    public int? ReviewIntervalMonths { get; set; }
}

public class AccessLevel : LookupEntity
{
    /// <summary>Null = level applicable to every system.</summary>
    public Guid? AccessSystemId { get; set; }
    public AccessSystem? AccessSystem { get; set; }
}

public class EmployeeAccess : SoftDeletableEntity, IHasCustomFields
{
    public Guid EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid AccessSystemId { get; set; }
    public AccessSystem? AccessSystem { get; set; }
    public Guid? AccessLevelId { get; set; }
    public AccessLevel? AccessLevel { get; set; }
    public string? Username { get; set; }
    public string? Role { get; set; }
    public DateTime GrantedAt { get; set; }
    public DateTime? RevokedAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public AccessStatus Status { get; set; } = AccessStatus.Active;
    public Guid? ResponsibleEmployeeId { get; set; }
    public string? RequestReference { get; set; }
    public DateOnly? ReviewDueDate { get; set; }
    public DateTime? LastReviewedAt { get; set; }
    public string? Comment { get; set; }
    public string? RevokeReason { get; set; }
    public string? CustomFields { get; set; }
}
