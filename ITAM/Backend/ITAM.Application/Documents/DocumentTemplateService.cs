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
    DateTime CreatedAt, string? CreatedByName, IReadOnlyList<string> Placeholders, int DocumentsGenerated, bool IsArchived);

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
    private readonly IPdfConverter _pdf;

    public DocumentTemplateService(IAppDbContext db, IFileService files, IDocumentRenderer renderer, ICurrentUser user, IClock clock, IAuditService audit,
        IPdfConverter pdf)
    {
        _db = db; _files = files; _renderer = renderer; _user = user; _clock = clock; _audit = audit; _pdf = pdf;
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
                x.v.CreatedAt, x.v.CreatedByName, Json.Deserialize<List<string>>(x.v.Placeholders) ?? new List<string>(), x.Count, x.v.IsArchived)).ToList(),
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
    public async Task<DocumentTemplateVersion> AddVersionCoreAsync(DocumentTemplate t, Stream file, string fileName, string? changeNote, bool activate, CancellationToken ct,
        TemplateModel? editorModel = null)
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
            EditorModel = editorModel is null ? null : Json.Serialize(editorModel),
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
        if (target.IsArchived)
            throw new BusinessException("VERSION_ARCHIVED", $"Версия {target.VersionNumber} в архиве — сначала верните её из архива");
        var old = versions.FirstOrDefault(v => v.IsActive)?.VersionNumber;
        foreach (var v in versions) v.IsActive = v.Id == versionId;
        t.ActiveVersionId = versionId;
        _audit.Log("template.version.activate", nameof(DocumentTemplate), id, t.Name, new { version = old }, new { version = target.VersionNumber });
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    // ------------------------------------------------------------------ web editor

    /// <summary>Editor content of a version (default: the active one). Uploaded DOCX versions are converted on the fly.</summary>
    public async Task<TemplateEditorDto> GetEditorAsync(Guid id, Guid? versionId, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var q = _db.DocumentTemplateVersions.AsNoTracking().Where(v => v.TemplateId == id);
        var version = versionId is not null
            ? await q.FirstOrDefaultAsync(v => v.Id == versionId, ct) ?? throw new NotFoundException("Версия шаблона", versionId)
            : await q.OrderByDescending(v => v.IsActive).ThenByDescending(v => v.VersionNumber).FirstOrDefaultAsync(ct);
        TemplateModel model;
        var fromDocx = false;
        if (version?.EditorModel is not null && Json.Deserialize<TemplateModel>(version.EditorModel) is { } stored) model = stored;
        else if (version is not null)
        {
            try { model = _renderer.ImportTemplate(await _files.ReadAllBytesAsync(version.FileId, ct)); }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                throw new BusinessException("TEMPLATE_INVALID", "Не удалось открыть версию шаблона в редакторе: файл DOCX повреждён");
            }
            fromDocx = true;
        }
        else model = new TemplateModel { Blocks = { new TemplateBlock { Type = "heading", Text = t.Name } } };
        return new TemplateEditorDto(t.Id, t.Name, t.DocumentType, version?.Id, version?.VersionNumber, model, fromDocx, Placeholders.For(t.DocumentType));
    }

    /// <summary>Saves the editor content as a new version of the template.</summary>
    public async Task<TemplateDto> SaveFromEditorAsync(Guid id, TemplateEditorSaveRequest req, CancellationToken ct)
    {
        req.Model.Validate();
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var bytes = _renderer.BuildTemplate(req.Model);
        await AddVersionCoreAsync(t, new MemoryStream(bytes), FileNameFor(t.Name), string.IsNullOrWhiteSpace(req.ChangeNote) ? "Изменено в редакторе" : req.ChangeNote,
            req.Activate, ct, req.Model);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(id, ct);
    }

    /// <summary>Creates a template from the editor content.</summary>
    public async Task<TemplateDto> CreateFromEditorAsync(TemplateEditorCreateRequest req, CancellationToken ct)
    {
        req.Model.Validate();
        var t = new DocumentTemplate { Name = req.Name.Trim(), Code = req.Code, Description = req.Description, DocumentType = req.DocumentType, IsDefault = req.IsDefault };
        _db.DocumentTemplates.Add(t);
        var bytes = _renderer.BuildTemplate(req.Model);
        await AddVersionCoreAsync(t, new MemoryStream(bytes), FileNameFor(t.Name), "Создан в редакторе", true, ct, req.Model);
        if (t.IsDefault) await ResetDefaultsAsync(t, ct);
        await _db.SaveChangesAsync(ct);
        return await GetAsync(t.Id, ct);
    }

    /// <summary>The editor content as a document with placeholders: PDF when PDF generation is available, otherwise DOCX.</summary>
    public async Task<(byte[] Content, string ContentType, string FileName)> PreviewAsync(TemplateModel model, CancellationToken ct)
    {
        model.Validate();
        var docx = _renderer.BuildTemplate(model);
        var pdf = await _pdf.ConvertDocxAsync(docx, ct);
        return pdf is not null
            ? (pdf, "application/pdf", "preview.pdf")
            : (docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "preview.docx");
    }

    private static string FileNameFor(string name)
    {
        var safe = new string(name.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c).ToArray()).Trim();
        return (safe.Length == 0 ? "template" : safe.Length > 100 ? safe[..100] : safe) + ".docx";
    }

    /// <summary>
    /// Deletes a template with all its versions. Allowed only while no document has been generated from it: generated
    /// documents reference the exact template version they were produced from — such templates can be archived instead.
    /// </summary>
    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var versions = await _db.DocumentTemplateVersions.Where(v => v.TemplateId == id).ToListAsync(ct);
        var versionIds = versions.Select(v => v.Id).ToList();
        var used = await _db.GeneratedDocuments.CountAsync(d => d.TemplateId == id || (d.TemplateVersionId != null && versionIds.Contains(d.TemplateVersionId.Value)), ct);
        if (used > 0)
            throw new ConflictException(ErrorCodes.HasDependencies,
                $"По шаблону «{t.Name}» уже сформировано документов: {used}. Удалить его нельзя — документы ссылаются на версию шаблона. " +
                "Отправьте шаблон в архив: он перестанет предлагаться при формировании документов.");
        var fileIds = versions.Select(v => v.FileId).ToList();
        await DetachDeletedDocumentsAsync(versionIds, ct);
        foreach (var d in await _db.GeneratedDocuments.IgnoreQueryFilters().Where(d => d.IsDeleted && d.TemplateId == id).ToListAsync(ct)) d.TemplateId = null;
        _db.DocumentTemplateVersions.RemoveRange(versions);
        _db.DocumentTemplates.Remove(t);
        _audit.Log("template.delete", nameof(DocumentTemplate), t.Id, t.Name, new { type = t.DocumentType.ToString(), versions = versions.Count }, null);
        await _db.SaveChangesAsync(ct);
        foreach (var fileId in fileIds) await _files.DeleteAsync(fileId, ct);
    }

    /// <summary>
    /// Deletes a template version. Not allowed for the active version (activate another one first) or for a version
    /// documents were generated from (archive it instead).
    /// </summary>
    public async Task<TemplateDto> DeleteVersionAsync(Guid id, Guid versionId, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var v = await _db.DocumentTemplateVersions.FirstOrDefaultAsync(x => x.Id == versionId && x.TemplateId == id, ct)
                ?? throw new NotFoundException("Версия шаблона", versionId);
        if (v.IsActive || t.ActiveVersionId == v.Id)
            throw new ConflictException(ErrorCodes.HasDependencies, $"Версия {v.VersionNumber} активна. Сначала сделайте активной другую версию.");
        var used = await _db.GeneratedDocuments.CountAsync(d => d.TemplateVersionId == v.Id, ct);
        if (used > 0)
            throw new ConflictException(ErrorCodes.HasDependencies,
                $"По версии {v.VersionNumber} сформировано документов: {used}. Удалить её нельзя — отправьте версию в архив.");
        await DetachDeletedDocumentsAsync(new[] { v.Id }, ct);
        _db.DocumentTemplateVersions.Remove(v);
        _audit.Log("template.version.delete", nameof(DocumentTemplate), t.Id, t.Name, new { version = v.VersionNumber, hash = v.FileHash }, null);
        await _db.SaveChangesAsync(ct);
        await _files.DeleteAsync(v.FileId, ct);
        return await GetAsync(id, ct);
    }

    /// <summary>Archives (or restores) a version. The active version cannot be archived.</summary>
    public async Task<TemplateDto> ArchiveVersionAsync(Guid id, Guid versionId, bool archived, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        var v = await _db.DocumentTemplateVersions.FirstOrDefaultAsync(x => x.Id == versionId && x.TemplateId == id, ct)
                ?? throw new NotFoundException("Версия шаблона", versionId);
        if (archived && (v.IsActive || t.ActiveVersionId == v.Id))
            throw new ConflictException(ErrorCodes.HasDependencies, $"Версия {v.VersionNumber} активна. Сначала сделайте активной другую версию.");
        if (v.IsArchived != archived)
        {
            v.IsArchived = archived;
            _audit.Log(archived ? "template.version.archive" : "template.version.unarchive", nameof(DocumentTemplate), t.Id, t.Name, null, new { version = v.VersionNumber });
            await _db.SaveChangesAsync(ct);
        }
        return await GetAsync(id, ct);
    }

    /// <summary>Deleted (soft) documents keep the version number but stop referencing a version that is being removed.</summary>
    private async Task DetachDeletedDocumentsAsync(IReadOnlyCollection<Guid> versionIds, CancellationToken ct)
    {
        var docs = await _db.GeneratedDocuments.IgnoreQueryFilters()
            .Where(d => d.IsDeleted && d.TemplateVersionId != null && versionIds.Contains(d.TemplateVersionId.Value)).ToListAsync(ct);
        foreach (var d in docs) d.TemplateVersionId = null;
    }

    public async Task ArchiveAsync(Guid id, bool archived, CancellationToken ct)
    {
        var t = await _db.DocumentTemplates.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Шаблон", id);
        t.IsArchived = archived;
        if (archived) t.IsDefault = false;
        await _db.SaveChangesAsync(ct);
    }
}
