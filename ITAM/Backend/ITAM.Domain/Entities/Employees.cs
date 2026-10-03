using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

public class EmployeeStatus : LookupEntity
{
    public EmployeeStatusKind Kind { get; set; }
    public string? Color { get; set; }
    public bool IsSystem { get; set; }
}

public class Employee : SoftDeletableEntity, IRegionBound, IHasCustomFields
{
    public string EmployeeNumber { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;
    public string FirstName { get; set; } = string.Empty;
    public string? MiddleName { get; set; }
    /// <summary>Denormalized "Last First Middle" for search and sorting.</summary>
    public string FullName { get; set; } = string.Empty;
    public string? Login { get; set; }
    public string? Email { get; set; }
    public string? Phone { get; set; }

    public Guid? PositionId { get; set; }
    public Position? Position { get; set; }
    public Guid? DepartmentId { get; set; }
    public Department? Department { get; set; }
    public Guid RegionId { get; set; }
    public Region? Region { get; set; }
    /// <summary>Office (location of type Office/Branch/Building).</summary>
    public Guid? LocationId { get; set; }
    public Location? Location { get; set; }
    /// <summary>Room (location of type Room).</summary>
    public Guid? RoomId { get; set; }
    public Location? Room { get; set; }
    public Guid? ManagerId { get; set; }
    public Employee? Manager { get; set; }

    public DateOnly? HireDate { get; set; }
    public DateOnly? TerminationDate { get; set; }
    public Guid StatusId { get; set; }
    public EmployeeStatus? Status { get; set; }
    public string? Comment { get; set; }
    public Guid? PhotoFileId { get; set; }
    public string? CustomFields { get; set; }

    /// <summary>External directory identity (AD objectGUID / LDAP DN) for future synchronization.</summary>
    public string? ExternalId { get; set; }
    public string? ExternalSource { get; set; }

    public uint Version { get; set; }

    Guid? IRegionBound.RegionId => RegionId;

    public static string ComposeFullName(string last, string first, string? middle)
        => string.Join(' ', new[] { last, first, middle }.Where(s => !string.IsNullOrWhiteSpace(s)).Select(s => s!.Trim()));
}

/// <summary>Effective-dated organizational placement of an employee (where the employee was at a given date).</summary>
public class EmployeeOrgHistory : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public DateTime EffectiveFrom { get; set; }
    public DateTime? EffectiveTo { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public Guid? DepartmentId { get; set; }
    public Guid? PositionId { get; set; }
    public Guid RegionId { get; set; }
    public Guid? LocationId { get; set; }
    public Guid? ManagerId { get; set; }
    public Guid? StatusId { get; set; }
    /// <summary>Names at the time of change (jsonb) — survives later renames.</summary>
    public string? Snapshot { get; set; }
    public string? Reason { get; set; }
}
