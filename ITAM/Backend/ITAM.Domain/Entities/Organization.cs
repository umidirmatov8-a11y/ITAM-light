using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>Tenant. The first version runs with a single organization; every aggregate carries OrganizationId.</summary>
public class Organization : Entity
{
    public string Name { get; set; } = string.Empty;
    public string? Code { get; set; }
    public bool IsActive { get; set; } = true;
    public DateTime CreatedAt { get; set; }
}

public class Region : LookupEntity, IRegionBound
{
    Guid? IRegionBound.RegionId => Id;
}

/// <summary>Hierarchical location tree: city → branch → office → floor → room, warehouses, data centers.</summary>
public class Location : LookupEntity, IRegionBound, IHasCustomFields
{
    public LocationType Type { get; set; }
    public Guid RegionId { get; set; }
    public Region? Region { get; set; }
    public Guid? ParentId { get; set; }
    public Location? Parent { get; set; }
    public List<Location> Children { get; set; } = new();
    public string? Address { get; set; }
    /// <summary>Materialized display path, e.g. "Ташкент / Головной офис / каб. 301". Recomputed on rename.</summary>
    public string? FullPath { get; set; }
    public string? CustomFields { get; set; }
    Guid? IRegionBound.RegionId => RegionId;
}

/// <summary>Hierarchical organizational structure: division → department → unit → group.</summary>
public class Department : LookupEntity, IRegionBound, IHasCustomFields
{
    public DepartmentType Type { get; set; } = DepartmentType.Department;
    public Guid? ParentId { get; set; }
    public Department? Parent { get; set; }
    public List<Department> Children { get; set; } = new();
    /// <summary>Null = organization-wide department visible to all regions.</summary>
    public Guid? RegionId { get; set; }
    public Region? Region { get; set; }
    public Guid? HeadEmployeeId { get; set; }
    public string? CostCenter { get; set; }
    public string? FullPath { get; set; }
    public string? CustomFields { get; set; }
}

public class Position : LookupEntity
{
}
