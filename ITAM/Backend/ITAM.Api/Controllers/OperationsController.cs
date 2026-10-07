using ITAM.Api.Auth;
using ITAM.Application.Common;
using ITAM.Application.Operations;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

/// <summary>Asset operations: issue, return, transfer, status change, cancellation (correction) and the operations journal.</summary>
public sealed class OperationsController : ApiControllerBase
{
    private readonly AssetOperationService _service;

    public OperationsController(AssetOperationService service) => _service = service;

    [HttpPost("issue"), HasPermission(Permissions.AssetsAssign)]
    public Task<OperationResult> Issue([FromBody] IssueRequest req) => _service.IssueAsync(req, Ct);

    [HttpPost("return"), HasPermission(Permissions.AssetsReturn)]
    public Task<OperationResult> Return([FromBody] ReturnRequest req) => _service.ReturnAsync(req, Ct);

    [HttpPost("transfer"), HasPermission(Permissions.AssetsTransfer)]
    public Task<OperationResult> Transfer([FromBody] TransferRequest req) => _service.TransferAsync(req, Ct);

    [HttpPost("status"), HasPermission(Permissions.AssetsStatus)]
    public Task<OperationResult> Status([FromBody] StatusChangeRequest req) => _service.ChangeStatusAsync(req, Ct);

    [HttpGet, HasPermission(Permissions.AssetsView)]
    public Task<PagedResult<BatchListItem>> List([FromQuery] BatchQuery q) => _service.ListBatchesAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.AssetsView)]
    public Task<BatchDto> Get(Guid id) => _service.GetBatchAsync(id, Ct);

    /// <summary>Cancels an operation (history correction). Events are kept and marked cancelled; the stream is replayed.</summary>
    [HttpPost("{id:guid}/cancel"), HasPermission(Permissions.AssetsCorrect)]
    public Task<BatchDto> Cancel(Guid id, [FromBody] CancelOperationRequest req) => _service.CancelAsync(id, req, Ct);

    [HttpPut("{id:guid}/signature"), HasPermission(Permissions.DocumentsSign)]
    public Task<BatchDto> Signature(Guid id, [FromBody] SignatureUpdate req) => _service.UpdateSignatureAsync(id, req, Ct);
}
