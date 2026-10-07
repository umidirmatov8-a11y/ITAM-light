using ITAM.Api.Auth;
using ITAM.Application.Assets;
using ITAM.Application.Audit;
using ITAM.Application.Common;
using ITAM.Application.Licenses;
using ITAM.Application.Operations;
using ITAM.Application.Repairs;
using ITAM.Application.Reports;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

public sealed class AssetsController : ApiControllerBase
{
    private readonly AssetService _service;

    public AssetsController(AssetService service) => _service = service;

    [HttpGet, HasPermission(Permissions.AssetsView)]
    public Task<PagedResult<AssetListItem>> List([FromQuery] AssetQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("export"), HasPermission(Permissions.ExportRun)]
    public async Task<IActionResult> Export([FromQuery] AssetQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.AssetsAsync(q, Ct), format, "assets");

    [HttpGet("{id:guid}"), HasPermission(Permissions.AssetsView)]
    public Task<AssetDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.AssetsCreate)]
    public Task<AssetDto> Create([FromBody] AssetInput input) => _service.CreateAsync(input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.AssetsEdit)]
    public Task<AssetDto> Update(Guid id, [FromBody] AssetInput input) => _service.UpdateAsync(id, input, Ct);

    [HttpDelete("{id:guid}"), HasPermission(Permissions.AssetsDelete)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return Ok(new { success = true }); }

    /// <summary>Full temporal history (business date + recording date) including cancelled events.</summary>
    [HttpGet("{id:guid}/history"), HasPermission(Permissions.AssetsView)]
    public Task<IReadOnlyList<AssetEventDto>> History(Guid id) => _service.HistoryAsync(id, Ct);

    [HttpGet("{id:guid}/timeline"), HasPermission(Permissions.AssetsView)]
    public Task<IReadOnlyList<TimelineItem>> Timeline(Guid id) => _service.TimelineAsync(id, Ct);

    /// <summary>State of the asset at a business date (holder, status, location).</summary>
    [HttpGet("{id:guid}/state-at"), HasPermission(Permissions.AssetsView)]
    public Task<AssetStateAtDto> StateAt(Guid id, [FromQuery] DateTime at) => _service.StateAtAsync(id, at, Ct);

    [HttpGet("{id:guid}/repairs"), HasPermission(Permissions.AssetsView)]
    public async Task<IReadOnlyList<RepairListItem>> Repairs(Guid id, [FromServices] RepairService repairs)
    {
        await _service.LoadVisibleAsync(id, Ct, false);
        return await repairs.ForAssetAsync(id, Ct);
    }

    [HttpGet("{id:guid}/licenses"), HasPermission(Permissions.LicensesView)]
    public async Task<IReadOnlyList<LicenseAssignmentDto>> Licenses(Guid id, [FromServices] LicenseService licenses)
    {
        await _service.LoadVisibleAsync(id, Ct, false);
        return await licenses.AssignmentsAsync(null, null, id, true, Ct);
    }

    [HttpGet("{id:guid}/operations"), HasPermission(Permissions.AssetsView)]
    public async Task<PagedResult<BatchListItem>> Operations(Guid id, [FromServices] AssetOperationService ops)
    {
        await _service.LoadVisibleAsync(id, Ct, false);
        return await ops.ListBatchesAsync(new BatchQuery { AssetId = id, PageSize = 200 }, Ct);
    }

    [HttpGet("{id:guid}/audit"), HasPermission(Permissions.AuditView)]
    public Task<IReadOnlyList<AuditLogDto>> Audit(Guid id, [FromServices] AuditQueryService audit) => audit.ForEntityAsync("Asset", id, Ct);

    private async Task<string> BaseUrlAsync(ISettingsService settings)
    {
        var general = await settings.GetAsync<GeneralSettings>(Ct);
        return string.IsNullOrWhiteSpace(general.PublicBaseUrl) ? $"{Request.Scheme}://{Request.Host}" : general.PublicBaseUrl.TrimEnd('/');
    }

    /// <summary>QR code (PNG or SVG) pointing to /assets/{id}.</summary>
    [HttpGet("{id:guid}/qr"), HasPermission(Permissions.AssetsView)]
    public async Task<IActionResult> Qr(Guid id, [FromQuery] string? format, [FromServices] ICodeGenerator codes, [FromServices] ISettingsService settings)
    {
        var asset = await _service.LoadVisibleAsync(id, Ct, false);
        var url = $"{await BaseUrlAsync(settings)}/assets/{id}";
        return format == "svg"
            ? Content(codes.QrSvg(url), "image/svg+xml")
            : File(codes.QrPng(url), "image/png", $"{asset.InventoryNumber}-qr.png");
    }

    [HttpGet("{id:guid}/barcode"), HasPermission(Permissions.AssetsView)]
    public async Task<IActionResult> Barcode(Guid id, [FromServices] ICodeGenerator codes)
    {
        var asset = await _service.LoadVisibleAsync(id, Ct, false);
        return Content(codes.Code128Svg(asset.InventoryNumber), "image/svg+xml");
    }

    public sealed record LabelsRequest(List<Guid> AssetIds);

    /// <summary>A4 sheet of QR labels for printing.</summary>
    [HttpPost("labels"), HasPermission(Permissions.AssetsView)]
    public async Task<IActionResult> Labels([FromBody] LabelsRequest req, [FromServices] ICodeGenerator codes, [FromServices] ISettingsService settings)
    {
        var labels = await _service.LabelsAsync(req.AssetIds, await BaseUrlAsync(settings), Ct);
        var org = (await settings.GetAsync<GeneralSettings>(Ct)).OrganizationName;
        return File(codes.LabelsPdf(labels, org), "application/pdf", "labels.pdf");
    }

    [HttpPost("bulk-edit"), HasPermission(Permissions.AssetsBulk)]
    public Task<BulkResultDto> BulkEdit([FromBody] AssetBulkEditRequest req) => _service.BulkEditAsync(req, Ct);
}
