using ITAM.Api.Auth;
using ITAM.Application.Access;
using ITAM.Application.Common;
using ITAM.Application.Reports;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

public sealed class AccessController : ApiControllerBase
{
    private readonly AccessService _service;

    public AccessController(AccessService service) => _service = service;

    [HttpGet, HasPermission(Permissions.AccessView)]
    public Task<PagedResult<AccessDto>> List([FromQuery] AccessQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("export"), HasPermission(Permissions.ExportRun)]
    public async Task<IActionResult> Export([FromQuery] AccessQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.AccessAsync(q, Ct), format, "access");

    [HttpGet("{id:guid}"), HasPermission(Permissions.AccessView)]
    public Task<AccessDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.AccessManage)]
    public Task<AccessDto> Create([FromBody] AccessInput input) => _service.SaveAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.AccessManage)]
    public Task<AccessDto> Update(Guid id, [FromBody] AccessInput input) => _service.SaveAsync(id, input, Ct);

    [HttpPost("{id:guid}/revoke"), HasPermission(Permissions.AccessManage)]
    public Task<AccessDto> Revoke(Guid id, [FromBody] AccessRevokeRequest req) => _service.RevokeAsync(id, req, Ct);

    [HttpPost("{id:guid}/review"), HasPermission(Permissions.AccessManage)]
    public Task<AccessDto> Review(Guid id, [FromBody] AccessReviewRequest req) => _service.ReviewAsync(id, req, Ct);

    public sealed record RevokeAllRequest(DateTime? RevokedAt, string? Reason);

    [HttpPost("employee/{employeeId:guid}/revoke-all"), HasPermission(Permissions.AccessManage)]
    public async Task<IActionResult> RevokeAll(Guid employeeId, [FromBody] RevokeAllRequest req)
        => Ok(new { revoked = await _service.RevokeAllAsync(employeeId, req.RevokedAt, req.Reason, Ct) });
}
