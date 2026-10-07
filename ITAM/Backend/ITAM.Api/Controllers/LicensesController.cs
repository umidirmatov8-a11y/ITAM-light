using ITAM.Api.Auth;
using ITAM.Application.Common;
using ITAM.Application.Licenses;
using ITAM.Application.Reports;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

public sealed class LicensesController : ApiControllerBase
{
    private readonly LicenseService _service;

    public LicensesController(LicenseService service) => _service = service;

    [HttpGet, HasPermission(Permissions.LicensesView)]
    public Task<PagedResult<LicenseListItem>> List([FromQuery] LicenseQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("summary"), HasPermission(Permissions.LicensesView)]
    public Task<LicenseSummary> Summary() => _service.SummaryAsync(Ct);

    [HttpGet("export"), HasPermission(Permissions.ExportRun)]
    public async Task<IActionResult> Export([FromQuery] LicenseQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.LicensesAsync(q, Ct), format, "licenses");

    [HttpGet("{id:guid}"), HasPermission(Permissions.LicensesView)]
    public Task<LicenseDto> Get(Guid id) => _service.GetAsync(id, Ct);

    /// <summary>Reveals the license key. Requires licenses.keys.view; every access is audited.</summary>
    [HttpGet("{id:guid}/key"), HasPermission(Permissions.LicensesKeysView)]
    public async Task<IActionResult> Key(Guid id) => Ok(new { key = await _service.RevealKeyAsync(id, Ct) });

    [HttpPost, HasPermission(Permissions.LicensesManage)]
    public Task<LicenseDto> Create([FromBody] LicenseInput input) => _service.SaveAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.LicensesManage)]
    public Task<LicenseDto> Update(Guid id, [FromBody] LicenseInput input) => _service.SaveAsync(id, input, Ct);

    [HttpPost("{id:guid}/archive"), HasPermission(Permissions.LicensesManage)]
    public async Task<IActionResult> Archive(Guid id) { await _service.ArchiveAsync(id, true, Ct); return Ok(new { success = true }); }

    [HttpPost("{id:guid}/restore"), HasPermission(Permissions.LicensesManage)]
    public async Task<IActionResult> Restore(Guid id) { await _service.ArchiveAsync(id, false, Ct); return Ok(new { success = true }); }

    [HttpGet("{id:guid}/assignments"), HasPermission(Permissions.LicensesView)]
    public Task<IReadOnlyList<LicenseAssignmentDto>> Assignments(Guid id, [FromQuery] bool includeRevoked = true)
        => _service.AssignmentsAsync(id, null, null, includeRevoked, Ct);

    [HttpPost("{id:guid}/assignments"), HasPermission(Permissions.LicensesManage)]
    public Task<LicenseAssignmentDto> Assign(Guid id, [FromBody] LicenseAssignRequest req) => _service.AssignAsync(id, req, Ct);

    [HttpPost("assignments/{assignmentId:guid}/revoke"), HasPermission(Permissions.LicensesManage)]
    public Task<LicenseAssignmentDto> Revoke(Guid assignmentId, [FromBody] LicenseRevokeRequest req) => _service.RevokeAsync(assignmentId, req, Ct);

    [HttpGet("by-employee/{employeeId:guid}"), HasPermission(Permissions.LicensesView)]
    public Task<IReadOnlyList<LicenseAssignmentDto>> ByEmployee(Guid employeeId) => _service.AssignmentsAsync(null, employeeId, null, true, Ct);

    [HttpGet("by-software/{softwareId:guid}"), HasPermission(Permissions.LicensesView)]
    public Task<PagedResult<LicenseListItem>> BySoftware(Guid softwareId) => _service.ListAsync(new LicenseQuery { SoftwareId = softwareId, PageSize = 500, IncludeArchived = true }, Ct);
}
