using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

public class DocumentTemplate : LookupEntity
{
    public DocumentType DocumentType { get; set; }
    public bool IsDefault { get; set; }
    public Guid? ActiveVersionId { get; set; }
    public List<DocumentTemplateVersion> Versions { get; set; } = new();
}

/// <summary>Immutable template version. A generated document references the exact version it was produced from.</summary>
public class DocumentTemplateVersion : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    public Guid TemplateId { get; set; }
    public DocumentTemplate? Template { get; set; }
    public int VersionNumber { get; set; }
    public Guid FileId { get; set; }
    public StoredFile? File { get; set; }
    public string FileHash { get; set; } = string.Empty;
    public string? ChangeNote { get; set; }
    /// <summary>jsonb array of placeholders detected in the DOCX.</summary>
    public string? Placeholders { get; set; }
    public bool IsActive { get; set; }
    public DateTime CreatedAt { get; set; }
    public Guid? CreatedById { get; set; }
    public string? CreatedByName { get; set; }
}

public class GeneratedDocument : SoftDeletableEntity, IRegionBound
{
    public string Number { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public DocumentType DocumentType { get; set; }
    public Guid? TemplateId { get; set; }
    public Guid? TemplateVersionId { get; set; }
    public DocumentTemplateVersion? TemplateVersion { get; set; }
    public int TemplateVersionNumber { get; set; }
    /// <summary>OperationBatch, Repair, Checklist, InventoryCampaign, StatusChange, Employee ...</summary>
    public string SourceType { get; set; } = string.Empty;
    public Guid? SourceId { get; set; }
    public Guid? EmployeeId { get; set; }
    public Guid? AssetId { get; set; }
    public Guid? RegionId { get; set; }
    public Guid? DocxFileId { get; set; }
    public StoredFile? DocxFile { get; set; }
    public Guid? PdfFileId { get; set; }
    public StoredFile? PdfFile { get; set; }
    /// <summary>jsonb: all placeholder values used for generation (frozen).</summary>
    public string? DataSnapshot { get; set; }
    public SignatureStatus EmployeeSignatureStatus { get; set; } = SignatureStatus.Pending;
    public SignatureStatus ResponsibleSignatureStatus { get; set; } = SignatureStatus.Pending;
    public DateTime? EmployeeSignedAt { get; set; }
    public DateTime? ResponsibleSignedAt { get; set; }
    public SignatureMethod SignatureMethod { get; set; } = SignatureMethod.None;
    public Guid? SignedScanFileId { get; set; }
    public bool IsVoided { get; set; }
    public string? VoidReason { get; set; }
}

/// <summary>Metadata of a file kept in the file storage (local disk today, S3-compatible tomorrow).</summary>
public class StoredFile : Entity, ITenantEntity, ISoftDelete
{
    public Guid OrganizationId { get; set; }
    public string FileName { get; set; } = string.Empty;
    public string ContentType { get; set; } = "application/octet-stream";
    /// <summary>Storage key relative to the storage root, e.g. documents/2026/10/{id}.docx.</summary>
    public string StoragePath { get; set; } = string.Empty;
    public long Size { get; set; }
    public string Sha256 { get; set; } = string.Empty;
    public FileCategory Category { get; set; }
    public string? EntityType { get; set; }
    public Guid? EntityId { get; set; }
    public string? Description { get; set; }
    public DateTime CreatedAt { get; set; }
    public Guid? CreatedById { get; set; }
    public string? CreatedByName { get; set; }
    public bool IsDeleted { get; set; }
    public DateTime? DeletedAt { get; set; }
    public Guid? DeletedById { get; set; }
}
