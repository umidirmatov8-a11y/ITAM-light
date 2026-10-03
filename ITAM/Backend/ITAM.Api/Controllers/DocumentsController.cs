using ITAM.Api.Auth;
using ITAM.Application.Common;
using ITAM.Application.Documents;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

/// <summary>Generated documents registry: generation, download, signature status, signed scans, voiding.</summary>
public sealed class DocumentsController : ApiControllerBase
{
    private readonly DocumentService _service;
    private readonly IFileService _files;

    public DocumentsController(DocumentService service, IFileService files) { _service = service; _files = files; }

    [HttpGet, HasPermission(Permissions.DocumentsView)]
    public Task<PagedResult<DocumentListItem>> List([FromQuery] DocumentQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.DocumentsView)]
    public Task<DocumentListItem> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost("generate"), HasPermission(Permissions.DocumentsGenerate)]
    public async Task<DocumentListItem> Generate([FromBody] GenerateDocumentRequest req)
    {
        var id = await _service.GenerateAsync(req.SourceType, req.SourceId, req.TemplateId, Ct);
        return await _service.GetAsync(id, Ct);
    }

    /// <summary>Downloads the DOCX (format=docx), PDF (format=pdf) or signed scan (format=scan).</summary>
    [HttpGet("{id:guid}/download"), HasPermission(Permissions.DocumentsView)]
    public async Task<IActionResult> Download(Guid id, [FromQuery] string format = "pdf", [FromQuery] bool inline = false)
    {
        var doc = await _service.LoadAsync(id, Ct);
        var fileId = format switch
        {
            "docx" => doc.DocxFileId,
            "scan" => doc.SignedScanFileId,
            _ => doc.PdfFileId ?? doc.DocxFileId
        } ?? throw new NotFoundException("Файл документа", format);
        var (file, stream) = await _files.OpenAsync(fileId, Ct);
        if (inline && file.ContentType == "application/pdf")
        {
            Response.Headers.ContentDisposition = $"inline; filename*=UTF-8''{Uri.EscapeDataString(file.FileName)}";
            return File(stream, file.ContentType);
        }
        return File(stream, file.ContentType, file.FileName);
    }

    [HttpPut("{id:guid}/signature"), HasPermission(Permissions.DocumentsSign)]
    public Task<DocumentListItem> Sign(Guid id, [FromBody] DocumentSignRequest req) => _service.SignAsync(id, req, Ct);

    [HttpPost("{id:guid}/scan"), HasPermission(Permissions.DocumentsSign)]
    [RequestSizeLimit(60 * 1024 * 1024)]
    public async Task<DocumentListItem> Scan(Guid id, IFormFile file)
    {
        await using var s = file.OpenReadStream();
        return await _service.AttachSignedScanAsync(id, s, file.FileName, file.ContentType, Ct);
    }

    public sealed record VoidRequest(string Reason);

    [HttpPost("{id:guid}/void"), HasPermission(Permissions.DocumentsGenerate)]
    public async Task<IActionResult> Void(Guid id, [FromBody] VoidRequest req)
    {
        if (string.IsNullOrWhiteSpace(req.Reason)) throw new ValidationFailedException("Укажите причину аннулирования");
        await _service.VoidAsync(id, req.Reason, Ct);
        return Ok(new { success = true });
    }
}

/// <summary>Document templates with versions.</summary>
[Route("api/templates")]
public sealed class TemplatesController : ApiControllerBase
{
    private readonly DocumentTemplateService _service;
    private readonly IFileService _files;

    public TemplatesController(DocumentTemplateService service, IFileService files) { _service = service; _files = files; }

    [HttpGet, HasPermission(Permissions.DocumentsView)]
    public Task<IReadOnlyList<TemplateListItem>> List([FromQuery] DocumentType? type, [FromQuery] bool includeArchived = false) => _service.ListAsync(type, includeArchived, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.DocumentsView)]
    public Task<TemplateDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpGet("placeholders/{type}"), HasPermission(Permissions.DocumentsView)]
    public IReadOnlyList<PlaceholderInfo> Placeholders(DocumentType type) => Application.Documents.Placeholders.For(type);

    [HttpPost, HasPermission(Permissions.DocumentTemplatesManage)]
    [RequestSizeLimit(30 * 1024 * 1024)]
    public async Task<TemplateDto> Create([FromForm] TemplateMetaInput meta, IFormFile file)
    {
        await using var s = file.OpenReadStream();
        return await _service.CreateAsync(meta, s, file.FileName, Ct);
    }

    [HttpPut("{id:guid}"), HasPermission(Permissions.DocumentTemplatesManage)]
    public Task<TemplateDto> Update(Guid id, [FromBody] TemplateMetaInput meta) => _service.UpdateMetaAsync(id, meta, Ct);

    [HttpPost("{id:guid}/versions"), HasPermission(Permissions.DocumentTemplatesManage)]
    [RequestSizeLimit(30 * 1024 * 1024)]
    public async Task<TemplateDto> AddVersion(Guid id, IFormFile file, [FromForm] string? changeNote, [FromForm] bool activate = true)
    {
        await using var s = file.OpenReadStream();
        return await _service.AddVersionAsync(id, s, file.FileName, changeNote, activate, Ct);
    }

    [HttpPost("{id:guid}/versions/{versionId:guid}/activate"), HasPermission(Permissions.DocumentTemplatesManage)]
    public Task<TemplateDto> Activate(Guid id, Guid versionId) => _service.ActivateAsync(id, versionId, Ct);

    [HttpGet("{id:guid}/versions/{versionId:guid}/download"), HasPermission(Permissions.DocumentsView)]
    public async Task<IActionResult> DownloadVersion(Guid id, Guid versionId)
    {
        var dto = await _service.GetAsync(id, Ct);
        var v = dto.Versions.FirstOrDefault(x => x.Id == versionId) ?? throw new NotFoundException("Версия", versionId);
        var (file, stream) = await _files.OpenAsync(v.FileId, Ct);
        return File(stream, file.ContentType, $"{dto.Name} v{v.VersionNumber}.docx");
    }

    [HttpPost("{id:guid}/archive"), HasPermission(Permissions.DocumentTemplatesManage)]
    public async Task<IActionResult> Archive(Guid id, [FromQuery] bool archived = true)
    {
        await _service.ArchiveAsync(id, archived, Ct);
        return Ok(new { success = true });
    }
}
