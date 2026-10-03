using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>Append-only audit trail. A database trigger forbids UPDATE and DELETE.</summary>
public class AuditLog : ITenantEntity
{
    public long Id { get; set; }
    public Guid OrganizationId { get; set; }
    public DateTime Timestamp { get; set; }
    public Guid? UserId { get; set; }
    public string? UserName { get; set; }
    public string? IpAddress { get; set; }
    public string? UserAgent { get; set; }
    public string Action { get; set; } = string.Empty;
    public string? EntityType { get; set; }
    public Guid? EntityId { get; set; }
    public string? EntityName { get; set; }
    public string? OldValues { get; set; }
    public string? NewValues { get; set; }
    public string? Comment { get; set; }
    public string? CorrelationId { get; set; }
    public bool Success { get; set; } = true;
}

public class Notification : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public string Type { get; set; } = string.Empty;
    public NotificationSeverity Severity { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public string? EntityType { get; set; }
    public Guid? EntityId { get; set; }
    public string? Link { get; set; }
    public Guid? RegionId { get; set; }
    /// <summary>Permission required to see the notification.</summary>
    public string? RequiredPermission { get; set; }
    /// <summary>Null = broadcast to everyone with permission; otherwise a single recipient.</summary>
    public Guid? UserId { get; set; }
    /// <summary>Unique key preventing duplicates (e.g. license-expiry:{id}:{date}).</summary>
    public string DedupKey { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public bool IsResolved { get; set; }
    public DateTime? ResolvedAt { get; set; }
}

public class NotificationRead
{
    public Guid NotificationId { get; set; }
    public Guid UserId { get; set; }
    public DateTime ReadAt { get; set; }
}

public class NotificationDelivery : Entity
{
    public Guid NotificationId { get; set; }
    public string Channel { get; set; } = string.Empty;
    public string Recipient { get; set; } = string.Empty;
    public bool Success { get; set; }
    public string? Error { get; set; }
    public DateTime CreatedAt { get; set; }
}

public class Setting : ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public string Key { get; set; } = string.Empty;
    /// <summary>jsonb value.</summary>
    public string Value { get; set; } = "null";
    public DateTime UpdatedAt { get; set; }
    public Guid? UpdatedById { get; set; }
}

public class Backup : Entity
{
    public string FileName { get; set; } = string.Empty;
    public string FilePath { get; set; } = string.Empty;
    public long Size { get; set; }
    public string? Sha256 { get; set; }
    public BackupKind Kind { get; set; }
    public BackupStatus Status { get; set; }
    public DateTime StartedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public Guid? CreatedById { get; set; }
    public string? CreatedByName { get; set; }
    public string? Error { get; set; }
    public bool IncludesFiles { get; set; }
    public string? AppVersion { get; set; }
}

public class ImportJob : AuditableEntity
{
    public string EntityType { get; set; } = string.Empty;
    public Guid FileId { get; set; }
    public string FileName { get; set; } = string.Empty;
    public ImportStatus Status { get; set; }
    /// <summary>jsonb { targetField: sourceColumn }.</summary>
    public string? Mapping { get; set; }
    public int TotalRows { get; set; }
    public int ValidRows { get; set; }
    public int ErrorRows { get; set; }
    public int ImportedRows { get; set; }
    /// <summary>jsonb [{row, column, value, error}].</summary>
    public string? Errors { get; set; }
    public string? Options { get; set; }
    public DateTime? CompletedAt { get; set; }
}
