namespace ITAM.Domain.Common;

/// <summary>Base entity with a time-ordered UUID v7 identifier.</summary>
public abstract class Entity
{
    public Guid Id { get; set; } = Guid.CreateVersion7();
}

/// <summary>Entity that belongs to an organization (tenant). Populated automatically on save.</summary>
public interface ITenantEntity
{
    Guid OrganizationId { get; set; }
}

public interface IAuditableEntity
{
    DateTime CreatedAt { get; set; }
    Guid? CreatedById { get; set; }
    DateTime? UpdatedAt { get; set; }
    Guid? UpdatedById { get; set; }
}

/// <summary>Soft delete: rows are never removed physically, a global query filter hides them.</summary>
public interface ISoftDelete
{
    bool IsDeleted { get; set; }
    DateTime? DeletedAt { get; set; }
    Guid? DeletedById { get; set; }
}

public interface IArchivable
{
    bool IsArchived { get; set; }
}

/// <summary>Entity whose changes are recorded automatically in the audit log.</summary>
public interface IAuditable
{
}

/// <summary>Entity bound to a region; used by regional access scoping.</summary>
public interface IRegionBound
{
    Guid? RegionId { get; }
}

/// <summary>Entity carrying admin-defined custom field values (jsonb).</summary>
public interface IHasCustomFields
{
    string? CustomFields { get; set; }
}

public abstract class AuditableEntity : Entity, IAuditableEntity, ITenantEntity, IAuditable
{
    public Guid OrganizationId { get; set; }
    public DateTime CreatedAt { get; set; }
    public Guid? CreatedById { get; set; }
    public DateTime? UpdatedAt { get; set; }
    public Guid? UpdatedById { get; set; }
}

public abstract class SoftDeletableEntity : AuditableEntity, ISoftDelete
{
    public bool IsDeleted { get; set; }
    public DateTime? DeletedAt { get; set; }
    public Guid? DeletedById { get; set; }
}

/// <summary>Base class for admin-managed reference data (справочники).</summary>
public abstract class LookupEntity : AuditableEntity, IArchivable
{
    public string Name { get; set; } = string.Empty;
    public string? Code { get; set; }
    public string? Description { get; set; }
    public int SortOrder { get; set; }
    public bool IsArchived { get; set; }
}

/// <summary>Marks a property whose value must never appear in audit logs or application logs.</summary>
[AttributeUsage(AttributeTargets.Property)]
public sealed class SensitiveAttribute : Attribute
{
}
