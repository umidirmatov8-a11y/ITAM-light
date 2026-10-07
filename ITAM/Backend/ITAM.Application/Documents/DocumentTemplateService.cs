using System.ComponentModel.DataAnnotations;
using System.Security.Cryptography;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Documents;

public sealed record TemplateListItem(Guid Id, string Name, string? Code, string? Description, DocumentType DocumentType, bool IsDefault, bool IsArchived,
    int? ActiveVersion, int VersionCount, DateTime? UpdatedAt);

public sealed record TemplateDto(Guid Id, string Name, string? Code, string? Description, DocumentType DocumentType, bool IsDefault, bool IsArchived,
    Guid? ActiveVersionId, IReadOnlyList<TemplateVersionDto> Versions, IReadOnlyList<PlaceholderInfo> AvailablePlaceholders);

public sealed record TemplateVersionDto(Guid Id, int VersionNumber, Guid FileId, string FileName, string FileHash, string? ChangeNote, bool IsActive,
    DateTime CreatedAt, string? CreatedByName, IReadOnlyList<string> Placeholders, int DocumentsGenerated);

public sealed class TemplateMetaInput
{
    [Required, MaxLength(256)] public string Name { get; set; } = string.Empty;
    [MaxLength(64)] public string? Code { get; set; }
    [MaxLength(2000)] public string? Description { get; set; }
    public DocumentType DocumentType { get; set; }
    public bool IsDefault { get; set; }
}

/// <summary>DOCX templates with immutable versions. Generated documents keep the exact version used.</summary>
public sealed class DocumentTemplateService
{
    private readonly IAppDbContext _db;
    private readonly IFileService _files;
    private readonly IDocumentRenderer _renderer;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IAuditService _audit;

    public DocumentTemplateService(IAppDbContext db, IFileService files, IDocumentRenderer renderer, ICurrentUser user, IClock clock, IAuditService audit)
    {
        _db = db; _files = files; _renderer = renderer; _user = user; _clock = clock; _audit = audit;
    }

    public async Task<IReadOnlyList<TemplateListItem>> ListAsync(DocumentType? type, bool includeArchived, CancellationToken ct)
    {
        var q = _db.DocumentTemplates.AsNoTracking().AsQueryable();
        if (type is not null) q = q.Where(t => t.DocumentType == type);
        if (!includeArchived) q = q.Where(t => !t.IsArchived);
        return await q.OrderBy(t => t.DocumentType).ThenBy(t => t.Name).Select(t => new TemplateListItem(t.Id, t.Name, t.Code, t.Description, t.DocumentType,
            t.IsDefault, t.IsArchived, t.Versions.Where(v => v.IsActive).Select(v => (int?)v.VersionNumber).FirstOrDefault(), t.Versions.Count,
            t.UpdatedAt ?? t.CreatedAt)).ToListAsync(ct);
    }

    public async Task<TemplateDto> GetAsync(Guid id, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var versions = await _db.DocumentTemplateVersions.AsNoTracking().Where(v => v.TemplateId == id).OrderByDescending(v => v.VersionNumber)
            .Select(v => new { v, v.File!.FileName, Count = _db.GeneratedDocuments.Count(d => d.TemplateVersionId == v.Id) }).ToListAsync(ct);
        return new TemplateDto(t.Id, t.Name, t.Code, t.Description, t.DocumentType, t.IsDefault, t.IsArchived, t.ActiveVersionId,
            versions.Select(x => new TemplateVersionDto(x.v.Id, x.v.VersionNumber, x.v.FileId, x.FileName, x.v.FileHash, x.v.ChangeNote, x.v.IsActive,
                x.v.CreatedAt, x.v.CreatedByName, Json.Deserialize<List<string>>(x.v.Placeholders) ?? new List<string>(), x.Count)).ToList(),
            Placeholders.For(t.DocumentType));
    }

    public async Task<TemplateDto> CreateAsync(TemplateMetaInput meta, Stream file, string fileName, CancellationToken ct)
    {
        var t = new DocumentTemplate { Name = meta.Name.Trim(), Code = meta.Code, Description = meta.Description, DocumentType = meta.DocumentType, IsDefault = meta.IsDefault };
        _db.DocumentTemplates.Add(t);
        await AddVersionCoreAsync(t, file, fileName, "Первая версия", true, ct);
        if (t.IsDefault) await ResetDefaultsAsync(t, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(t.Id, ct);
    }

    public async Task<TemplateDto> UpdateMetaAsync(Guid id, TemplateMetaInput meta, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        t.Name = meta.Name.Trim();
        t.Code = meta.Code;
        t.Description = meta.Description;
        t.DocumentType = meta.DocumentType;
        t.IsDefault = meta.IsDefault;
        if (t.IsDefault) await ResetDefaultsAsync(t, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    private async Task ResetDefaultsAsync(DocumentTemplate t, CancellationToken ct)
        => await _db.DocumentTemplates.Where(x => x.DocumentType == t.DocumentType && x.Id != t.Id && x.IsDefault)
            .ExecuteUpdateAsync(s => s.SetProperty(x => x.IsDefault, false), ct);

    public async Task<TemplateDto> AddVersionAsync(Guid id, Stream file, string fileName, string? changeNote, bool activate, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        await AddVersionCoreAsync(t, file, fileName, changeNote, activate, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    /// <summary>Stores a new immutable version (also used by the seeder for built-in templates).</summary>
    public async Task<DocumentTemplateVersion> AddVersionCoreAsync(DocumentTemplate t, Stream file, string fileName, string? changeNote, bool activate, CancellationToken ct)
    {
        if (!fileName.EndsWith(".docx", StringComparison.OrdinalIgnoreCase))
            throw new BusinessException("TEMPLATE_FORMAT", "Шаблон должен быть в формате DOCX");
        using var ms = new MemoryStream();
        await file.CopyToAsync(ms, ct);
        var bytes = ms.ToArray();
        IReadOnlyList<string> placeholders;
        try { placeholders = _renderer.ExtractPlaceholders(bytes); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            throw new BusinessException("TEMPLATE_INVALID", "Файл не является корректным документом DOCX");
        }
        var stored = await _files.SaveBytesAsync(bytes, fileName, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            FileCategory.Template, nameof(DocumentTemplate), t.Id, ct);
        var persistedMax = await _db.DocumentTemplateVersions.Where(v => v.TemplateId == t.Id).MaxAsync(v => (int?)v.VersionNumber, ct) ?? 0;
        var localMax = _db.DocumentTemplateVersions.Local.Where(v => v.TemplateId == t.Id).Select(v => v.VersionNumber).DefaultIfEmpty(0).Max();
        var next = Math.Max(persistedMax, localMax) + 1;
        var version = new DocumentTemplateVersion
        {
            TemplateId = t.Id,
            VersionNumber = next,
            FileId = stored.Id,
            FileHash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            ChangeNote = changeNote,
            Placeholders = Json.Serialize(placeholders),
            IsActive = activate,
            CreatedAt = _clock.UtcNow,
            CreatedById = _user.UserId,
            CreatedByName = _user.DisplayName ?? _user.UserName ?? "system",
        };
        _db.DocumentTemplateVersions.Add(version);
        if (activate)
        {
            foreach (var v in await _db.DocumentTemplateVersions.Where(v => v.TemplateId == t.Id && v.IsActive).ToListAsync(ct)) v.IsActive = false;
            t.ActiveVersionId = version.Id;
        }
        _audit.Log("template.version.add", nameof(DocumentTemplate), t.Id, t.Name, null, new { version = next, hash = version.FileHash, activate, changeNote });
        return version;
    }

    public async Task<TemplateDto> ActivateAsync(Guid id, Guid versionId, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var versions = await _db.DocumentTemplateVersions.Where(v => v.TemplateId == id).ToListAsync(ct);
        var target = versions.FirstOrDefault(v => v.Id == versionId) ?? throw new NotFoundException("Версия шаблона", versionId);
        var old = versions.FirstOrDefault(v => v.IsActive)?.VersionNumber;
        foreach (var v in versions) v.IsActive = v.Id == versionId;
        t.ActiveVersionId = versionId;
        _audit.Log("template.version.activate", nameof(DocumentTemplate), id, t.Name, new { version = old }, new { version = target.VersionNumber });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    public async Task ArchiveAsync(Guid id, bool archived, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        t.IsArchived = archived;
        if (archived) t.IsDefault = false;
        await _db.SaveChangesAsync(ct);
    }
}
