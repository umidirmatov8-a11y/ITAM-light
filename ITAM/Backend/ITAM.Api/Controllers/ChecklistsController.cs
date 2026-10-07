using ITAM.Api.Auth;
using ITAM.Application.Checklists;
using ITAM.Application.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

/// <summary>Onboarding / offboarding checklists and their templates.</summary>
public sealed class ChecklistsController : ApiControllerBase
{
    private readonly ChecklistService _service;

    public ChecklistsController(ChecklistService service) => _service = service;

    [HttpGet, HasPermission(Permissions.ChecklistsView)]
    public Task<PagedResult<ChecklistListItem>> List([FromQuery] ChecklistQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.ChecklistsView)]
    public Task<ChecklistDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPut("{id:guid}/items/{itemId:guid}"), HasPermission(Permissions.ChecklistsManage)]
    public Task<ChecklistDto> UpdateItem(Guid id, Guid itemId, [FromBody] ChecklistItemUpdate req) => _service.UpdateItemAsync(id, itemId, req, Ct);

    [HttpPost("{id:guid}/complete"), HasPermission(Permissions.ChecklistsManage)]
    public Task<ChecklistDto> Complete(Guid id, [FromQuery] bool force = false) => _service.CompleteAsync(id, force, Ct);

    public sealed record CancelRequest(string? Reason);

    [HttpPost("{id:guid}/cancel"), HasPermission(Permissions.ChecklistsManage)]
    public Task<ChecklistDto> Cancel(Guid id, [FromBody] CancelRequest req) => _service.CancelAsync(id, req.Reason, Ct);

    [HttpGet("templates"), HasPermission(Permissions.ChecklistsView)]
    public Task<IReadOnlyList<ChecklistTemplateDto>> Templates([FromQuery] ChecklistKind? kind, [FromQuery] bool includeArchived = false)
        => _service.TemplatesAsync(kind, includeArchived, Ct);

    [HttpGet("templates/{id:guid}"), HasPermission(Permissions.ChecklistsView)]
    public Task<ChecklistTemplateDto> Template(Guid id) => _service.TemplateAsync(id, Ct);

    [HttpPost("templates"), HasPermission(Permissions.ChecklistTemplatesManage)]
    public Task<ChecklistTemplateDto> CreateTemplate([FromBody] ChecklistTemplateInput input) => _service.SaveTemplateAsync(null, input, Ct);

    [HttpPut("templates/{id:guid}"), HasPermission(Permissions.ChecklistTemplatesManage)]
    public Task<ChecklistTemplateDto> UpdateTemplate(Guid id, [FromBody] ChecklistTemplateInput input) => _service.SaveTemplateAsync(id, input, Ct);

    [HttpPost("templates/{id:guid}/archive"), HasPermission(Permissions.ChecklistTemplatesManage)]
    public async Task<IActionResult> ArchiveTemplate(Guid id, [FromQuery] bool archived = true)
    {
        await _service.ArchiveTemplateAsync(id, archived, Ct);
        return Ok(new { success = true });
    }
}
