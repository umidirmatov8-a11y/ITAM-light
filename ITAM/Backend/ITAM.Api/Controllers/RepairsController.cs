using ITAM.Api.Auth;
using ITAM.Application.Common;
using ITAM.Application.Repairs;
using ITAM.Application.Reports;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

public sealed class RepairsController : ApiControllerBase
{
    private readonly RepairService _service;

    public RepairsController(RepairService service) => _service = service;

    [HttpGet, HasPermission(Permissions.AssetsView)]
    public Task<PagedResult<RepairListItem>> List([FromQuery] RepairQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("export"), HasPermission(Permissions.ExportRun)]
    public async Task<IActionResult> Export([FromQuery] RepairQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.RepairsAsync(q, Ct), format, "repairs");

    [HttpGet("{id:guid}"), HasPermission(Permissions.AssetsView)]
    public Task<RepairDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.AssetsRepair)]
    public Task<RepairDto> Create([FromBody] RepairInput input) => _service.CreateAsync(input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.AssetsRepair)]
    public Task<RepairDto> Update(Guid id, [FromBody] RepairInput input) => _service.UpdateAsync(id, input, Ct);

    [HttpPost("{id:guid}/status"), HasPermission(Permissions.AssetsRepair)]
    public Task<RepairDto> Status(Guid id, [FromBody] RepairStatusRequest req) => _service.ChangeStatusAsync(id, req, Ct);
}
