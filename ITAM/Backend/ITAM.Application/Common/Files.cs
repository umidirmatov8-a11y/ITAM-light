using System.Security.Cryptography;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Common;

public sealed record StoredFileDto(Guid Id, string FileName, string ContentType, long Size, string Sha256, FileCategory Category,
    string? EntityType, Guid? EntityId, string? Description, DateTime CreatedAt, string? CreatedByName);

public interface IFileService
{
    Task<StoredFile> SaveAsync(Stream content, string fileName, string? contentType, FileCategory category, string? entityType = null, Guid? entityId = null, string? description = null, CancellationToken ct = default);
    Task<StoredFile> SaveBytesAsync(byte[] content, string fileName, string contentType, FileCategory category, string? entityType = null, Guid? entityId = null, CancellationToken ct = default);
    Task<(StoredFile file, Stream stream)> OpenAsync(Guid id, CancellationToken ct = default);
    Task<byte[]> ReadAllBytesAsync(Guid id, CancellationToken ct = default);
    Task<IReadOnlyList<StoredFileDto>> ListAsync(string entityType, Guid entityId, CancellationToken ct = default);
    Task DeleteAsync(Guid id, CancellationToken ct = default);
}

public sealed class FileService : IFileService
{
    public const long MaxUploadBytes = 50L * 1024 * 1024;

    private static readonly HashSet<string> AllowedExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".tif", ".tiff", ".zip", ".7z", ".rar", ".odt", ".ods", ".rtf", ".msg", ".eml", ".xml", ".json"
    };

    /// <summary>Entities that accept attachments, with the permission required to attach.</summary>
    public static readonly IReadOnlyDictionary<string, string> AttachableEntities = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["Employee"] = Permissions.EmployeesView,
        ["Asset"] = Permissions.AssetsView,
        ["Repair"] = Permissions.AssetsView,
        ["OperationBatch"] = Permissions.AssetsView,
        ["License"] = Permissions.LicensesView,
        ["Contract"] = Permissions.ContractsView,
        ["GeneratedDocument"] = Permissions.DocumentsView,
        ["InventoryCampaign"] = Permissions.InventoryView,
    };

    private readonly IAppDbContext _db;
    private readonly IFileStorage _storage;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly IAuditService _audit;

    public FileService(IAppDbContext db, IFileStorage storage, ICurrentUser user, IClock clock, IAuditService audit)
    {
        _db = db; _storage = storage; _user = user; _clock = clock; _audit = audit;
    }

    public async Task<StoredFile> SaveAsync(Stream content, string fileName, string? contentType, FileCategory category, string? entityType = null, Guid? entityId = null, string? description = null, CancellationToken ct = default)
    {
        fileName = Path.GetFileName(fileName ?? "file");
        var ext = Path.GetExtension(fileName);
        if (category != FileCategory.Backup && !AllowedExtensions.Contains(ext))
            throw new BusinessException("FILE_TYPE_NOT_ALLOWED", $"Тип файла {ext} не разрешён");

        using var buffer = new MemoryStream();
        await content.CopyToAsync(buffer, ct);
        if (buffer.Length > MaxUploadBytes) throw new BusinessException("FILE_TOO_LARGE", "Файл превышает 50 МБ");
        buffer.Position = 0;
        var hash = Convert.ToHexString(SHA256.HashData(buffer.ToArray())).ToLowerInvariant();
        buffer.Position = 0;

        var now = _clock.UtcNow;
        var file = new StoredFile
        {
            FileName = fileName.Length > 500 ? fileName[^500..] : fileName,
            ContentType = string.IsNullOrWhiteSpace(contentType) ? GuessContentType(ext) : contentType,
            Size = buffer.Length,
            Sha256 = hash,
            Category = category,
            EntityType = entityType,
            EntityId = entityId,
            Description = description,
            CreatedAt = now,
            CreatedById = _user.UserId,
            CreatedByName = _user.DisplayName ?? _user.UserName,
        };
        var folder = category switch
        {
            FileCategory.Document => "documents",
            FileCategory.Template => "templates",
            FileCategory.Photo => "photos",
            FileCategory.Logo => "logos",
            FileCategory.Import => "imports",
            FileCategory.Export => "exports",
            _ => "attachments"
        };
        file.StoragePath = $"{folder}/{now:yyyy}/{now:MM}/{file.Id:N}{ext.ToLowerInvariant()}";
        await _storage.SaveAsync(file.StoragePath, buffer, ct);
        _db.StoredFiles.Add(file);
        if (category is FileCategory.Attachment or FileCategory.Photo)
            _audit.Log("file.upload", entityType ?? "File", entityId ?? file.Id, fileName, null, new { file.FileName, file.Size, file.Sha256 });
        return file;
    }

    public Task<StoredFile> SaveBytesAsync(byte[] content, string fileName, string contentType, FileCategory category, string? entityType = null, Guid? entityId = null, CancellationToken ct = default)
        => SaveAsync(new MemoryStream(content), fileName, contentType, category, entityType, entityId, null, ct);

    public async Task<(StoredFile file, Stream stream)> OpenAsync(Guid id, CancellationToken ct = default)
    {
        var file = await _db.StoredFiles.AsNoTracking().FirstOrDefaultAsync(f => f.Id == id, ct) ?? throw new NotFoundException("Файл", id);
        return (file, await _storage.OpenReadAsync(file.StoragePath, ct));
    }

    public async Task<byte[]> ReadAllBytesAsync(Guid id, CancellationToken ct = default)
    {
        var (_, stream) = await OpenAsync(id, ct);
        await using (stream)
        {
            using var ms = new MemoryStream();
            await stream.CopyToAsync(ms, ct);
            return ms.ToArray();
        }
    }

    public async Task<IReadOnlyList<StoredFileDto>> ListAsync(string entityType, Guid entityId, CancellationToken ct = default)
        => await _db.StoredFiles.AsNoTracking()
            .Where(f => f.EntityType == entityType && f.EntityId == entityId && (f.Category == FileCategory.Attachment || f.Category == FileCategory.Photo))
            .OrderByDescending(f => f.CreatedAt)
            .Select(f => new StoredFileDto(f.Id, f.FileName, f.ContentType, f.Size, f.Sha256, f.Category, f.EntityType, f.EntityId, f.Description, f.CreatedAt, f.CreatedByName))
            .ToListAsync(ct);

    public async Task DeleteAsync(Guid id, CancellationToken ct = default)
    {
        var file = await _db.StoredFiles.FirstOrDefaultAsync(f => f.Id == id, ct) ?? throw new NotFoundException("Файл", id);
        file.IsDeleted = true;
        file.DeletedAt = _clock.UtcNow;
        file.DeletedById = _user.UserId;
        _audit.Log("file.delete", file.EntityType ?? "File", file.EntityId ?? file.Id, file.FileName);
        await _db.SaveChangesAsync(ct);
    }

    public static string GuessContentType(string ext) => ext.ToLowerInvariant() switch
    {
        ".pdf" => "application/pdf",
        ".docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv" => "text/csv",
        ".txt" => "text/plain",
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".gif" => "image/gif",
        ".webp" => "image/webp",
        ".zip" => "application/zip",
        ".json" => "application/json",
        ".xml" => "application/xml",
        _ => "application/octet-stream"
    };
}
