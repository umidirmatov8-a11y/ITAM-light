using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

public class Software : LookupEntity, IHasCustomFields
{
    public string? Publisher { get; set; }
    public string? Version { get; set; }
    public string? Category { get; set; }
    public bool RequiresLicense { get; set; } = true;
    public string? Website { get; set; }
    public string? CustomFields { get; set; }
}

public class LicenseType : LookupEntity
{
    public LicenseModel Model { get; set; }
}

public class License : SoftDeletableEntity, IRegionBound, IHasCustomFields
{
    public string Name { get; set; } = string.Empty;
    public Guid? SoftwareId { get; set; }
    public Software? Software { get; set; }
    public Guid? VendorId { get; set; }
    public Supplier? Vendor { get; set; }
    public Guid? SupplierId { get; set; }
    public Supplier? Supplier { get; set; }
    public Guid? LicenseTypeId { get; set; }
    public LicenseType? LicenseType { get; set; }
    public LicenseModel Model { get; set; }
    /// <summary>Encrypted with ASP.NET Data Protection; never logged or audited in clear text.</summary>
    [Sensitive]
    public string? LicenseKeyEncrypted { get; set; }
    public int Seats { get; set; } = 1;
    public DateOnly? PurchaseDate { get; set; }
    public DateOnly? ExpirationDate { get; set; }
    public DateOnly? RenewalDate { get; set; }
    public decimal? Cost { get; set; }
    public string? Currency { get; set; }
    public Guid? ContractId { get; set; }
    public string? ContractNumber { get; set; }
    public string? Notes { get; set; }
    public Guid? RegionId { get; set; }
    public bool IsArchived { get; set; }
    public string? CustomFields { get; set; }
    public uint Version { get; set; }
    public List<LicenseAssignment> Assignments { get; set; } = new();
}

public class LicenseAssignment : AuditableEntity
{
    public Guid LicenseId { get; set; }
    public License? License { get; set; }
    public Guid? EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public Guid? AssetId { get; set; }
    public Asset? Asset { get; set; }
    public DateTime AssignedAt { get; set; }
    public DateTime? RevokedAt { get; set; }
    public DateTime RecordedAt { get; set; }
    public Guid? RecordedById { get; set; }
    public int SeatCount { get; set; } = 1;
    public string? Comment { get; set; }
    public string? RevokeReason { get; set; }
    public string? Snapshot { get; set; }
}
