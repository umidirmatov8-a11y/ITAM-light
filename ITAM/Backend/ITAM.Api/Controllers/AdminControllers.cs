using System.Text.Json;
using ITAM.Api.Auth;
using ITAM.Api.Hosting;
using ITAM.Application.Admin;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;
using ITAM.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Api.Controllers;

[Route("api/admin/users")]
public sealed class UsersController : ApiControllerBase
{
    private readonly UserAdminService _service;
    public UsersController(UserAdminService service) => _service = service;

    [HttpGet, HasPermission(Permissions.UsersManage)]
    public Task<PagedResult<UserDto>> List([FromQuery] PagedRequest q) => _service.ListAsync(q, Ct);

    [HttpGet("{id:guid}"), HasPermission(Permissions.UsersManage)]
    public Task<UserDto> Get(Guid id) => _service.GetAsync(id, Ct);

    [HttpPost, HasPermission(Permissions.UsersManage)]
    public Task<UserDto> Create([FromBody] UserInput input) => _service.SaveAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.UsersManage)]
    public Task<UserDto> Update(Guid id, [FromBody] UserInput input) => _service.SaveAsync(id, input, Ct);

    [HttpPost("{id:guid}/reset-password"), HasPermission(Permissions.UsersManage)]
    public async Task<IActionResult> ResetPassword(Guid id, [FromBody] ResetPasswordRequest req) { await _service.ResetPasswordAsync(id, req, Ct); return Ok(new { success = true }); }

    [HttpPost("{id:guid}/unlock"), HasPermission(Permissions.UsersManage)]
    public async Task<IActionResult> Unlock(Guid id) { await _service.UnlockAsync(id, Ct); return Ok(new { success = true }); }

    [HttpDelete("{id:guid}"), HasPermission(Permissions.UsersManage)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return Ok(new { success = true }); }

    [HttpGet("sessions"), HasPermission(Permissions.UsersManage)]
    public Task<IReadOnlyList<SessionDto>> Sessions([FromQuery] Guid? userId)
        => _service.SessionsAsync(userId, Guid.TryParse(User.FindFirst(ItamClaims.SessionId)?.Value, out var s) ? s : Guid.Empty, Ct);

    [HttpDelete("sessions/{sessionId:guid}"), HasPermission(Permissions.UsersManage)]
    public async Task<IActionResult> RevokeSession(Guid sessionId, [FromServices] SessionCookieService cookies)
    {
        await _service.RevokeSessionAsync(sessionId, Ct);
        cookies.Invalidate(sessionId);
        return Ok(new { success = true });
    }
}

[Route("api/admin/roles")]
public sealed class RolesController : ApiControllerBase
{
    private readonly UserAdminService _service;
    public RolesController(UserAdminService service) => _service = service;

    [HttpGet, HasPermission(Permissions.RolesManage)]
    public Task<IReadOnlyList<RoleDto>> List() => _service.RolesAsync(Ct);

    /// <summary>Role options for user editing (users.manage).</summary>
    [HttpGet("options"), HasPermission(Permissions.UsersManage)]
    public async Task<IReadOnlyList<RoleRef>> Options() => (await _service.RolesAsync(Ct)).Select(r => new RoleRef(r.Id, r.Name, r.Code)).ToList();

    [HttpGet("permissions"), HasPermission(Permissions.RolesManage)]
    public IReadOnlyList<PermissionDto> Catalogue() => _service.PermissionCatalogue();

    [HttpPost, HasPermission(Permissions.RolesManage)]
    public Task<RoleDto> Create([FromBody] RoleInput input) => _service.SaveRoleAsync(null, input, Ct);

    [HttpPut("{id:guid}"), HasPermission(Permissions.RolesManage)]
    public Task<RoleDto> Update(Guid id, [FromBody] RoleInput input) => _service.SaveRoleAsync(id, input, Ct);

    [HttpDelete("{id:guid}"), HasPermission(Permissions.RolesManage)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteRoleAsync(id, Ct); return Ok(new { success = true }); }
}

[Route("api/admin/settings")]
public sealed class SettingsController : ApiControllerBase
{
    private readonly SettingsAdminService _service;
    public SettingsController(SettingsAdminService service) => _service = service;

    [HttpGet, HasPermission(Permissions.SettingsManage)]
    public Task<AllSettingsDto> Get() => _service.GetAsync(Ct);

    [HttpPut("{group}"), HasPermission(Permissions.SettingsManage)]
    public async Task<AllSettingsDto> Save(string group, [FromBody] JsonElement body)
    {
        await _service.SaveAsync(group, body, Ct);
        return await _service.GetAsync(Ct);
    }

    public sealed record TestChannelRequest(string Channel, string Recipient);

    [HttpPost("test-channel"), HasPermission(Permissions.SettingsManage)]
    public async Task<IActionResult> TestChannel([FromBody] TestChannelRequest req) => Ok(new { result = await _service.TestChannelAsync(req.Channel, req.Recipient, Ct) });

    /// <summary>Organization logo upload.</summary>
    [HttpPost("logo"), HasPermission(Permissions.SettingsManage)]
    public async Task<AllSettingsDto> Logo(IFormFile file, [FromServices] IFileService files, [FromServices] ISettingsService settings, [FromServices] AppDbContext db)
    {
        if (!file.ContentType.StartsWith("image/") || file.ContentType == "image/svg+xml") throw new ValidationFailedException("Логотип должен быть изображением PNG/JPG");
        await using var s = file.OpenReadStream();
        var stored = await files.SaveAsync(s, file.FileName, file.ContentType, FileCategory.Logo, "Organization", null, null, Ct);
        await db.SaveChangesAsync(Ct);
        var general = await settings.GetAsync<GeneralSettings>(Ct);
        general.LogoFileId = stored.Id;
        await settings.SaveAsync(general, Ct);
        return await _service.GetAsync(Ct);
    }
}

[Route("api/admin/backups")]
public sealed class BackupsController : ApiControllerBase
{
    private readonly BackupService _service;
    public BackupsController(BackupService service) => _service = service;

    [HttpGet, HasPermission(Permissions.BackupManage)]
    public Task<IReadOnlyList<BackupDto>> List() => _service.ListAsync(Ct);

    [HttpPost, HasPermission(Permissions.BackupManage)]
    public Task<BackupDto> Create() => _service.CreateAsync(BackupKind.Manual, Ct);

    [HttpGet("{id:guid}/download"), HasPermission(Permissions.BackupManage)]
    public async Task<IActionResult> Download(Guid id)
    {
        var (path, name) = await _service.GetFileAsync(id, Ct);
        return PhysicalFile(path, "application/zip", name);
    }

    [HttpDelete("{id:guid}"), HasPermission(Permissions.BackupManage)]
    public async Task<IActionResult> Delete(Guid id) { await _service.DeleteAsync(id, Ct); return Ok(new { success = true }); }

    /// <summary>Restore from an existing backup (super administrator only). A safety backup is taken first.</summary>
    [HttpPost("{id:guid}/restore"), HasPermission(Permissions.BackupRestore)]
    public async Task<IActionResult> Restore(Guid id) { await _service.RestoreAsync(id, Ct); return Ok(new { success = true }); }

    /// <summary>Upload a backup archive (e.g. from another server) and restore it.</summary>
    [HttpPost("upload-restore"), HasPermission(Permissions.BackupRestore)]
    [RequestSizeLimit(4L * 1024 * 1024 * 1024)]
    [RequestFormLimits(MultipartBodyLengthLimit = 4L * 1024 * 1024 * 1024)]
    public async Task<IActionResult> UploadRestore(IFormFile file)
    {
        if (!file.FileName.EndsWith(".zip", StringComparison.OrdinalIgnoreCase)) throw new ValidationFailedException("Ожидается архив .zip резервной копии ITAM");
        var dir = await _service.DirectoryAsync(Ct);
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, "uploaded-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + ".zip");
        await using (var fs = System.IO.File.Create(path)) await file.CopyToAsync(fs, Ct);
        await _service.RestoreFromFileAsync(path, file.FileName, Ct);
        return Ok(new { success = true });
    }
}

[Route("api/admin/system")]
public sealed class SystemController : ApiControllerBase
{
    public sealed record SystemInfo(string Version, string Environment, string DataRoot, string? Database, string? DatabaseVersion, string OsDescription,
        string Framework, DateTime ServerTimeUtc, long DatabaseSizeBytes, int Users, int Employees, int Assets, int AuditRecords, bool DatabaseReady);

    [HttpGet, HasPermission(Permissions.SettingsManage)]
    public async Task<SystemInfo> Get([FromServices] AppDbContext db, [FromServices] IConfiguration config, [FromServices] IWebHostEnvironment env)
    {
        var version = (await db.Database.SqlQueryRaw<string>("SELECT version() AS \"Value\"").ToListAsync(Ct)).FirstOrDefault();
        var size = (await db.Database.SqlQueryRaw<long>("SELECT pg_database_size(current_database()) AS \"Value\"").ToListAsync(Ct)).FirstOrDefault();
        return new SystemInfo(typeof(SystemController).Assembly.GetName().Version?.ToString(3) ?? "1.0.0", env.EnvironmentName, config["Itam:ResolvedDataRoot"] ?? "",
            db.Database.GetDbConnection().Database, version?.Split(',')[0], System.Runtime.InteropServices.RuntimeInformation.OSDescription,
            System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription, DateTime.UtcNow, size,
            await db.Users.CountAsync(Ct), await db.Employees.CountAsync(Ct), await db.Assets.CountAsync(Ct), await db.AuditLogs.CountAsync(Ct), DatabaseInitializer.Ready);
    }
}
