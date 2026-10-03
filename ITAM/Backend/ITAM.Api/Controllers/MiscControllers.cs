using ITAM.Api.Auth;
using ITAM.Application.Admin;
using ITAM.Application.Audit;
using ITAM.Application.Common;
using ITAM.Application.Contracts;
using ITAM.Application.Dashboard;
using ITAM.Application.DataExchange;
using ITAM.Application.Inventory;
using ITAM.Application.Notifications;
using ITAM.Application.Reports;
using ITAM.Application.Search;
using ITAM.Application.Stock;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

[Authorize]
public sealed class DashboardController : ApiControllerBase
{
    [HttpGet]
    public Task<DashboardDto> Get([FromQuery] Guid? regionId, [FromServices] DashboardService service) => service.GetAsync(regionId, Ct);
}

[Authorize]
public sealed class SearchController : ApiControllerBase
{
    [HttpGet]
    public Task<SearchResult> Search([FromQuery] string q, [FromServices] SearchService service) => service.SearchAsync(q, Ct);
}

[Authorize]
public sealed class NotificationsController : ApiControllerBase
{
    private readonly NotificationService _service;
    public NotificationsController(NotificationService service) => _service = service;

    [HttpGet]
    public Task<PagedResult<NotificationDto>> List([FromQuery] NotificationQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("unread-count")]
    public async Task<IActionResult> Unread() => Ok(new { count = await _service.UnreadCountAsync(Ct) });

    public sealed record MarkReadRequest(List<Guid>? Ids);

    [HttpPost("read")]
    public async Task<IActionResult> MarkRead([FromBody] MarkReadRequest req) { await _service.MarkReadAsync(req.Ids, Ct); return Ok(new { success = true }); }

    /// <summary>Runs the notification rules immediately (normally hourly).</summary>
    [HttpPost("run"), HasPermission(Permissions.SettingsManage)]
    public async Task<IActionResult> Run() => Ok(new { created = await _service.GenerateAsync(Ct) });
}

public sealed class AuditController : ApiControllerBase
{
    private readonly AuditQueryService _service;
    public AuditController(AuditQueryService service) => _service = service;

    [HttpGet, HasPermission(Permissions.AuditView)]
    public Task<PagedResult<AuditLogDto>> List([FromQuery] AuditQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("actions"), HasPermission(Permissions.AuditView)]
    public Task<IReadOnlyList<string>> Actions() => _service.ActionsAsync(Ct);

    [HttpGet("entity/{entityType}/{entityId:guid}"), HasPermission(Permissions.AuditView)]
    public Task<IReadOnlyList<AuditLogDto>> ForEntity(string entityType, Guid entityId) => _service.ForEntityAsync(entityType, entityId, Ct);

    [HttpGet("export"), HasPermission(Permissions.AuditView)]
    public async Task<IActionResult> Export([FromQuery] AuditQuery q, [FromQuery] string? format, [FromServices] ExportService export)
        => Export(await export.AuditAsync(q, Ct), format, "audit");
}

[Authorize]
public sealed class ReportsController : ApiControllerBase
{
    private readonly ReportService _service;
    public ReportsController(ReportService service) => _service = service;

    [HttpGet]
    public IReadOnlyList<ReportDefinition> Definitions() => _service.Available();

    /// <summary>Runs a report and returns the table (preview).</summary>
    [HttpGet("{key}")]
    public async Task<TabularData> Run(string key, [FromQuery] ReportParameters p)
    {
        var data = await _service.RunAsync(key, p, Ct);
        return data with { Rows = data.Rows.Take(1000).ToList() };
    }

    [HttpGet("{key}/export")]
    public async Task<IActionResult> Export(string key, [FromQuery] ReportParameters p, [FromQuery] string? format)
    {
        EnsurePermission(Permissions.ExportRun);
        return Export(await _service.RunAsync(key, p, Ct), format, "report-" + key);
    }
}

[Route("api/import")]
public sealed class ImportController : ApiControllerBase
{
    private readonly ImportService _service;
    public ImportController(ImportService service) => _service = service;

    [HttpGet("fields"), HasPermission(Permissions.ImportRun)]
    public IReadOnlyDictionary<string, ImportField[]> Fields() => ImportService.Fields;

    [HttpGet("template/{entityType}"), HasPermission(Permissions.ImportRun)]
    public IActionResult Template(string entityType, [FromQuery] string? format) => Export(ImportService.Template(entityType), format ?? "xlsx", "import-" + entityType);

    [HttpPost("{entityType}/upload"), HasPermission(Permissions.ImportRun)]
    [RequestSizeLimit(60 * 1024 * 1024)]
    public async Task<ImportPreview> Upload(string entityType, IFormFile file)
    {
        await using var s = file.OpenReadStream();
        return await _service.UploadAsync(entityType, s, file.FileName, Ct);
    }

    [HttpPost("{jobId:guid}/validate"), HasPermission(Permissions.ImportRun)]
    public Task<ImportValidation> Validate(Guid jobId, [FromBody] ImportMappingRequest req) => _service.ValidateAsync(jobId, req, Ct);

    [HttpPost("{jobId:guid}/commit"), HasPermission(Permissions.ImportRun)]
    public Task<ImportResultDto> Commit(Guid jobId, [FromBody] ImportMappingRequest req) => _service.CommitAsync(jobId, req, Ct);
}

public sealed class InventoryController : ApiControllerBase
{
    private readonly InventoryService _service;
    public InventoryController(InventoryService service) => _service = service;

    [HttpGet, HasPermission(Permissions.InventoryView)]
    public Task<PagedResult<InventoryListItem>> List([FromQuery] PagedRequest q) => _service.ListAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.InventoryView)]
    public Task<InventoryListItem> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.InventoryManage)]
    public Task<InventoryListItem> Create([FromBody] InventoryCreateRequest req) => _service.CreateAsync(req, Ct);

    [HttpGet("{id:guid}/items"), HasPermission(Permissions.InventoryView)]
    public Task<PagedResult<InventoryItemDto>> Items(Guid id, [FromQuery] InventoryItemResult? result, [FromQuery] PagedRequest q) => _service.ItemsAsync(id, result, q, Ct);

    /// <summary>Scan a QR code / inventory number / serial number.</summary>
    [HttpPost("{id:guid}/scan"), HasPermission(Permissions.InventoryManage)]
    public Task<InventoryItemDto> Scan(Guid id, [FromBody] InventoryScanRequest req) => _service.ScanAsync(id, req, Ct);

    [HttpPut("{id:guid}/items/{itemId:guid}"), HasPermission(Permissions.InventoryManage)]
    public Task<InventoryItemDto> UpdateItem(Guid id, Guid itemId, [FromBody] InventoryItemUpdate req) => _service.UpdateItemAsync(id, itemId, req, Ct);

    [HttpPost("{id:guid}/complete"), HasPermission(Permissions.InventoryManage)]
    public Task<InventoryListItem> Complete(Guid id) => _service.CompleteAsync(id, Ct);

    [HttpPost("{id:guid}/cancel"), HasPermission(Permissions.InventoryManage)]
    public async Task<IActionResult> Cancel(Guid id) { await _service.CancelAsync(id, Ct); return Ok(new { success = true }); }
}

public sealed class StockController : ApiControllerBase
{
    private readonly StockService _service;
    public StockController(StockService service) => _service = service;

    [HttpGet("summary"), HasPermission(Permissions.StockView)]
    public Task<IReadOnlyList<StockItemSummary>> Summary([FromQuery] string? search) => _service.SummaryAsync(search, Ct);

    [HttpGet("balances"), HasPermission(Permissions.StockView)]
    public Task<IReadOnlyList<StockBalanceDto>> Balances([FromQuery] Guid? itemId, [FromQuery] Guid? locationId) => _service.BalancesAsync(itemId, locationId, Ct);

    [HttpGet("movements"), HasPermission(Permissions.StockView)]
    public Task<PagedResult<StockMovementDto>> Movements([FromQuery] Guid? itemId, [FromQuery] PagedRequest q) => _service.MovementsAsync(itemId, q, Ct);

    [HttpPost("movements"), HasPermission(Permissions.StockManage)]
    public Task<StockMovementDto> Move([FromBody] StockMovementRequest req) => _service.MoveAsync(req, Ct);
}

public sealed class ContractsController : ApiControllerBase
{
    private readonly ContractService _service;
    public ContractsController(ContractService service) => _service = service;

    [HttpGet, HasPermission(Permissions.ContractsView)]
    public Task<PagedResult<ContractDto>> List([FromQuery] ContractQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.ContractsView)]
    public Task<ContractDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.ContractsManage)]
    public Task<ContractDto> Create([FromBody] ContractInput input) => _service.SaveAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.ContractsManage)]
    public Task<ContractDto> Update(Guid id, [FromBody] ContractInput input) => _service.SaveAsync(id, input, Ct);

    [HttpDelete("{id:guid}"), HasPermission(Permissions.ContractsManage)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return Ok(new { success = true }); }
}

[Route("api/custom-fields")]
public sealed class CustomFieldsController : ApiControllerBase
{
    private readonly CustomFieldAdminService _service;
    public CustomFieldsController(CustomFieldAdminService service) => _service = service;

    /// <summary>Field definitions (any authenticated user: needed to render forms).</summary>
    [HttpGet, Authorize]
    public Task<IReadOnlyList<CustomFieldDto>> List([FromQuery] CustomFieldEntity? entity, [FromQuery] Guid? assetTypeId, [FromQuery] bool includeArchived = false)
        => _service.ListAsync(entity, assetTypeId, includeArchived, Ct);

    [HttpPost, HasPermission(Permissions.CustomFieldsManage)]
    public Task<CustomFieldDto> Create([FromBody] CustomFieldInput input) => _service.SaveAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.CustomFieldsManage)]
    public Task<CustomFieldDto> Update(Guid id, [FromBody] CustomFieldInput input) => _service.SaveAsync(id, input, Ct);

    [HttpPost("{id:guid}/archive"), HasPermission(Permissions.CustomFieldsManage)]
    public async Task<IActionResult> Archive(Guid id, [FromQuery] bool archived = true) { await _service.ArchiveAsync(id, archived, Ct); return Ok(new { success = true }); }
}
