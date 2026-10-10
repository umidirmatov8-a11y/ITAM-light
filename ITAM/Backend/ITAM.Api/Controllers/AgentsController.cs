using System.IO.Compression;
using System.Text;
using System.Text.Json;
using ITAM.Api.Auth;
using ITAM.Application.Agents;
using ITAM.Application.Common;
using ITAM.Domain.Security;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

/// <summary>
/// Protocol of the Windows inventory agent. Anonymous at the HTTP level: registration is authorized by the enrollment key,
/// inventory by the per-device token in the <c>X-ITAM-Agent-Token</c> header.
/// </summary>
[AllowAnonymous]
[Route("api/agent")]
public sealed class AgentProtocolController : ApiControllerBase
{
    public const string TokenHeader = "X-ITAM-Agent-Token";
    private readonly AgentService _service;
    private readonly SystemContext _system;

    public AgentProtocolController(AgentService service, SystemContext system) { _service = service; _system = system; }

    private string? Ip => HttpContext.Connection.RemoteIpAddress?.ToString();

    [HttpPost("register")]
    public Task<AgentRegisterResponse> Register([FromBody] AgentRegisterRequest req)
    {
        _system.Enabled = true;
        _system.ActorName = "agent:" + req.Hostname;
        return _service.RegisterAsync(req, Ip, Ct);
    }

    [HttpPost("inventory")]
    [RequestSizeLimit(20 * 1024 * 1024)]
    public async Task<IActionResult> Inventory([FromBody] AgentInventoryReport report)
    {
        _system.Enabled = true;
        var device = await _service.AuthenticateAsync(Request.Headers[TokenHeader].ToString(), Ct);
        if (device is null)
            return StatusCode(401, new { success = false, error = new { code = "AGENT_NOT_REGISTERED", message = "Агент не зарегистрирован или удалён — требуется повторная регистрация" } });
        _system.ActorName = "agent:" + device.Hostname;
        return Ok(await _service.SubmitInventoryAsync(device, report, Ip, Ct));
    }

    /// <summary>Agent package without credentials (scripts + GPO templates); used by GPO deployments from a share.</summary>
    [HttpGet("package")]
    public IActionResult Package() => File(AgentPackage.Build(null), "application/zip", "ITAM-Agent.zip");
}

/// <summary>Administration of agent-reported computers.</summary>
[Route("api/agents")]
public sealed class AgentsController : ApiControllerBase
{
    private readonly AgentService _service;
    public AgentsController(AgentService service) => _service = service;

    [HttpGet, HasPermission(Permissions.AgentsView)]
    public Task<PagedResult<AgentDeviceListItem>> List([FromQuery] AgentDeviceQuery q) => _service.ListAsync(q, Ct);

    [HttpGet("summary"), HasPermission(Permissions.AgentsView)]
    public Task<AgentSummaryDto> Summary() => _service.SummaryAsync(Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.AgentsView)]
    public Task<AgentDeviceDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpGet("{id:guid}/software"), HasPermission(Permissions.AgentsView)]
    public Task<IReadOnlyList<DiscoveredSoftwareDto>> Software(Guid id) => _service.SoftwareAsync(id, Ct);

    [HttpGet("by-asset/{assetId:guid}"), HasPermission(Permissions.AssetsView)]
    public async Task<IActionResult> ByAsset(Guid assetId)
    {
        var d = await _service.ByAssetAsync(assetId, Ct);
        return d is null ? NoContent() : Ok(d);
    }

    [HttpPost("{id:guid}/link"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentDeviceDto> Link(Guid id, [FromBody] AgentLinkRequest req) => _service.LinkAsync(id, req.AssetId, Ct);

    [HttpPost("{id:guid}/unlink"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentDeviceDto> Unlink(Guid id) => _service.UnlinkAsync(id, Ct);

    [HttpPost("{id:guid}/create-asset"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentDeviceDto> CreateAsset(Guid id, [FromBody] AgentCreateAssetRequest req)
    {
        EnsurePermission(Permissions.AssetsCreate);
        return _service.CreateAssetAsync(id, req, Ct);
    }

    [HttpPost("{id:guid}/ignore"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentDeviceDto> Ignore(Guid id, [FromQuery] bool ignored = true) => _service.SetIgnoredAsync(id, ignored, Ct);

    [HttpDelete("{id:guid}"), HasPermission(Permissions.AgentsManage)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return NoContent(); }

    [HttpGet("software"), HasPermission(Permissions.AgentsView)]
    public Task<PagedResult<SoftwareSummaryItem>> SoftwareSummary([FromQuery] AgentSoftwareQuery q) => _service.SoftwareSummaryAsync(q, Ct);

    [HttpGet("software/devices"), HasPermission(Permissions.AgentsView)]
    public Task<IReadOnlyList<object>> SoftwareDevices([FromQuery] string name) => _service.SoftwareDevicesAsync(name, Ct);

    [HttpGet("settings"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentSettingsDto> Settings() => _service.GetSettingsAsync(Ct);

    [HttpPut("settings"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentSettingsDto> SaveSettings([FromBody] AgentSettingsDto req) => _service.SaveSettingsAsync(req, Ct);

    [HttpPost("settings/regenerate-key"), HasPermission(Permissions.AgentsManage)]
    public Task<AgentSettingsDto> RegenerateKey() => _service.RegenerateKeyAsync(Ct);

    /// <summary>
    /// Ready-to-run package for manual installation: the scripts plus agent.config.json with this server's address and the
    /// enrollment key, so <c>install.cmd</c> needs no parameters.
    /// </summary>
    [HttpGet("package"), HasPermission(Permissions.AgentsManage)]
    public async Task<IActionResult> Package([FromServices] ISettingsService settings)
    {
        var s = await _service.GetSettingsAsync(Ct);
        var general = await settings.GetAsync<GeneralSettings>(Ct);
        var server = !string.IsNullOrWhiteSpace(general.PublicBaseUrl) ? general.PublicBaseUrl.TrimEnd('/') : $"{Request.Scheme}://{Request.Host}";
        return File(AgentPackage.Build(new { serverUrl = server, enrollmentKey = s.EnrollmentKey }), "application/zip", "ITAM-Agent.zip");
    }
}

/// <summary>Builds the agent zip from the <c>agent</c> folder shipped next to the server.</summary>
public static class AgentPackage
{
    public static string Directory => Path.Combine(AppContext.BaseDirectory, "agent");

    public static byte[] Build(object? config)
    {
        if (!System.IO.Directory.Exists(Directory))
            throw new ITAM.Domain.Common.NotFoundException("Пакет агента", "agent");
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, true))
        {
            foreach (var file in System.IO.Directory.EnumerateFiles(Directory, "*", SearchOption.AllDirectories))
                zip.CreateEntryFromFile(file, Path.GetRelativePath(Directory, file).Replace('\\', '/'), CompressionLevel.Optimal);
            if (config is not null)
            {
                var entry = zip.CreateEntry("agent.config.json");
                using var w = new StreamWriter(entry.Open(), new UTF8Encoding(false));
                w.Write(JsonSerializer.Serialize(config, new JsonSerializerOptions { WriteIndented = true }));
            }
        }
        return ms.ToArray();
    }
}
