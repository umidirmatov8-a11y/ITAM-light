using ITAM.Domain.Common;

namespace ITAM.Domain.Entities;

public class User : SoftDeletableEntity
{
    public string UserName { get; set; } = string.Empty;
    public string NormalizedUserName { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public string? Email { get; set; }
    [Sensitive]
    public string? PasswordHash { get; set; }
    public bool IsActive { get; set; } = true;
    public int FailedLoginCount { get; set; }
    public DateTime? LockoutEnd { get; set; }
    public DateTime? LastLoginAt { get; set; }
    public string? LastLoginIp { get; set; }
    public DateTime? PasswordChangedAt { get; set; }
    public bool MustChangePassword { get; set; }
    public Guid? EmployeeId { get; set; }
    /// <summary>Local, LDAP, OIDC (future providers).</summary>
    public string AuthProvider { get; set; } = "Local";
    public string? ExternalId { get; set; }
    /// <summary>When true the user is not limited by regional scope.</summary>
    public bool AllRegions { get; set; }
    public string? Language { get; set; }
    public string? TimeZone { get; set; }
    /// <summary>jsonb UI preferences (theme, table columns, saved filters).</summary>
    public string? Preferences { get; set; }
    public List<UserRole> Roles { get; set; } = new();
    public List<UserRegion> Regions { get; set; } = new();
}

public class Role : AuditableEntity
{
    public string Name { get; set; } = string.Empty;
    public string Code { get; set; } = string.Empty;
    public string? Description { get; set; }
    public bool IsSystem { get; set; }
    public List<RolePermission> Permissions { get; set; } = new();
}

public class Permission
{
    public string Code { get; set; } = string.Empty;
    public string Group { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
}

public class RolePermission
{
    public Guid RoleId { get; set; }
    public Role? Role { get; set; }
    public string PermissionCode { get; set; } = string.Empty;
}

public class UserRole
{
    public Guid UserId { get; set; }
    public User? User { get; set; }
    public Guid RoleId { get; set; }
    public Role? Role { get; set; }
}

public class UserRegion
{
    public Guid UserId { get; set; }
    public User? User { get; set; }
    public Guid RegionId { get; set; }
    public Region? Region { get; set; }
}

/// <summary>Server-side session: enables revocation, idle timeout and an "active sessions" view.</summary>
public class UserSession : Entity
{
    public Guid UserId { get; set; }
    public User? User { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime LastSeenAt { get; set; }
    public DateTime ExpiresAt { get; set; }
    public string? IpAddress { get; set; }
    public string? UserAgent { get; set; }
    public DateTime? RevokedAt { get; set; }
    public string? RevokeReason { get; set; }
}

/// <summary>Personal API token for integrations (SIEM, Power BI, scripts). Only the hash is stored.</summary>
public class ApiToken : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid UserId { get; set; }
    public User? User { get; set; }
    public string Name { get; set; } = string.Empty;
    [Sensitive]
    public string TokenHash { get; set; } = string.Empty;
    public string Prefix { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public DateTime? ExpiresAt { get; set; }
    public DateTime? LastUsedAt { get; set; }
    public DateTime? RevokedAt { get; set; }
}
