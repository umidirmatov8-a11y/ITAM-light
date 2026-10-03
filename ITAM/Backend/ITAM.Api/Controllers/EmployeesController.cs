using ITAM.Api.Auth;
using ITAM.Application.Assets;
using ITAM.Application.Checklists;
using ITAM.Application.Common;
using ITAM.Application.Employees;
using ITAM.Application.Reports;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

public sealed class EmployeesController : ApiControllerBase
{
    private readonly EmployeeService _service;

    public EmployeesController(EmployeeService service) => _service = service;

    [HttpGet, HasPermission(Permissions.EmployeesView)]
    public Task<PagedResult<EmployeeListItem>> List([FromQuery] EmployeeQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("export"), HasPermission(Permissions.ExportRun)]
    public async Task<IActionResult> Export([FromQuery] EmployeeQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.EmployeesAsync(q, Ct), format, "employees");

    [HttpGet("{id:guid}"), HasPermission(Permissions.EmployeesView)]
    public Task<EmployeeDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.EmployeesCreate)]
    public Task<EmployeeDto> Create([FromBody] EmployeeInput input) => _service.CreateAsync(input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.EmployeesEdit)]
    public Task<EmployeeDto> Update(Guid id, [FromBody] EmployeeInput input) => _service.UpdateAsync(id, input, Ct);

    /// <summary>Open items: equipment, licenses, accesses, repairs, unsigned documents, open checklists.</summary>
    [HttpGet("{id:guid}/open-items"), HasPermission(Permissions.EmployeesView)]
    public Task<OpenItemsDto> OpenItems(Guid id) => _service.OpenItemsAsync(id, Ct);

    [HttpPost("{id:guid}/terminate"), HasPermission(Permissions.EmployeesTerminate)]
    public Task<EmployeeDto> Terminate(Guid id, [FromBody] TerminateRequest req) => _service.TerminateAsync(id, req, Ct);

    [HttpPost("{id:guid}/archive"), HasPermission(Permissions.EmployeesDelete)]
    public async Task<IActionResult> Archive(Guid id) { await _service.ArchiveAsync(id, Ct); return Ok(new { success = true }); }

    [HttpDelete("{id:guid}"), HasPermission(Permissions.EmployeesDelete)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return Ok(new { success = true }); }

    [HttpPost("bulk"), HasPermission(Permissions.EmployeesBulk)]
    public Task<BulkResult> Bulk([FromBody] EmployeeBulkRequest req) => _service.BulkAsync(req, Ct);

    [HttpGet("{id:guid}/timeline"), HasPermission(Permissions.EmployeesView)]
    public Task<IReadOnlyList<TimelineItem>> Timeline(Guid id) => _service.TimelineAsync(id, Ct);

    [HttpGet("{id:guid}/org-history"), HasPermission(Permissions.EmployeesView)]
    public Task<IReadOnlyList<EmployeeOrgHistoryDto>> OrgHistory(Guid id) => _service.OrgHistoryAsync(id, Ct);

    [HttpGet("{id:guid}/assets"), HasPermission(Permissions.AssetsView)]
    public Task<IReadOnlyList<AssetListItem>> Assets(Guid id, [FromServices] AssetService assets) => _service.CurrentAssetsAsync(id, assets, Ct);

    [HttpGet("{id:guid}/checklists"), HasPermission(Permissions.ChecklistsView)]
    public async Task<IReadOnlyList<ChecklistDto>> Checklists(Guid id, [FromServices] ChecklistService checklists)
    {
        await _service.EnsureVisibleAsync(id, Ct);
        return await checklists.ForEmployeeAsync(id, Ct);
    }

    public sealed record StartChecklistRequest(ChecklistKind Kind, Guid? TemplateId);

    [HttpPost("{id:guid}/checklists"), HasPermission(Permissions.ChecklistsManage)]
    public Task<ChecklistDto> StartChecklist(Guid id, [FromBody] StartChecklistRequest req, [FromServices] ChecklistService checklists)
        => checklists.StartAsync(id, req.Kind, req.TemplateId, Ct);
}
