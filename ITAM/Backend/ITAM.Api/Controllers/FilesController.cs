using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Api.Controllers;

/// <summary>Attachments for employees, assets, repairs, operations, licenses, contracts (invoices, warranty, photos, acts).</summary>
[Authorize]
public sealed class FilesController : ApiControllerBase
{
    private readonly IFileService _files;
    private readonly ICurrentUser _user;
    private readonly AppDbContext _db;

    public FilesController(IFileService files, ICurrentUser user, AppDbContext db) { _files = files; _user = user; _db = db; }

    private void EnsureEntityAccess(string entityType)
    {
        if (!FileService.AttachableEntities.TryGetValue(entityType, out var perm)) throw new ValidationFailedException("Недопустимый тип объекта");
        if (!_user.Has(perm)) throw new ForbiddenException();
    }

    [HttpGet("{entityType}/{entityId:guid}")]
    public Task<IReadOnlyList<StoredFileDto>> List(string entityType, Guid entityId)
    {
        EnsureEntityAccess(entityType);
        return _files.ListAsync(entityType, entityId, Ct);
    }

    [HttpPost("{entityType}/{entityId:guid}")]
    [RequestSizeLimit(60 * 1024 * 1024)]
    public async Task<StoredFileDto> Upload(string entityType, Guid entityId, IFormFile file, [FromForm] string? description, [FromForm] bool photo = false)
    {
        EnsureEntityAccess(entityType);
        if (!_user.Has(Permissions.FilesUpload)) throw new ForbiddenException();
        await using var s = file.OpenReadStream();
        var stored = await _files.SaveAsync(s, file.FileName, file.ContentType, photo ? FileCategory.Photo : FileCategory.Attachment, entityType, entityId, description, Ct);
        if (photo && entityType == "Employee")
        {
            var emp = await _db.Employees.FirstOrDefaultAsync(e => e.Id == entityId, Ct) ?? throw new NotFoundException("Сотрудник", entityId);
            emp.PhotoFileId = stored.Id;
        }
        await _db.SaveChangesAsync(Ct);
        return new StoredFileDto(stored.Id, stored.FileName, stored.ContentType, stored.Size, stored.Sha256, stored.Category, stored.EntityType, stored.EntityId,
            stored.Description, stored.CreatedAt, stored.CreatedByName);
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Download(Guid id, [FromQuery] bool inline = false)
    {
        var meta = await _db.StoredFiles.AsNoTracking().FirstOrDefaultAsync(f => f.Id == id, Ct) ?? throw new NotFoundException("Файл", id);
        if (meta.Category is FileCategory.Backup or FileCategory.Import) throw new ForbiddenException();
        if (meta.EntityType is not null && FileService.AttachableEntities.ContainsKey(meta.EntityType)) EnsureEntityAccess(meta.EntityType);
        var (file, stream) = await _files.OpenAsync(id, Ct);
        var isImage = file.ContentType.StartsWith("image/") && file.ContentType != "image/svg+xml";
        if (inline && (isImage || file.ContentType == "application/pdf"))
        {
            Response.Headers.ContentDisposition = $"inline; filename*=UTF-8''{Uri.EscapeDataString(file.FileName)}";
            return File(stream, file.ContentType);
        }
        return File(stream, file.ContentType, file.FileName);
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Delete(Guid id)
    {
        if (!_user.Has(Permissions.FilesUpload)) throw new ForbiddenException();
        var meta = await _db.StoredFiles.AsNoTracking().FirstOrDefaultAsync(f => f.Id == id, Ct) ?? throw new NotFoundException("Файл", id);
        if (meta.Category is not (FileCategory.Attachment or FileCategory.Photo)) throw new ForbiddenException("Системные файлы удалять нельзя");
        await _files.DeleteAsync(id, Ct);
        return Ok(new { success = true });
    }
}
