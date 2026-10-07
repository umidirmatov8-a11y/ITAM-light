using ITAM.Api.Hosting;
using ITAM.Application.Common;
using ITAM.Application.Setup;
using ITAM.Domain.Common;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace ITAM.Api.Controllers;

/// <summary>First-run setup wizard (available only until the first administrator exists).</summary>
[AllowAnonymous]
public sealed class SetupController : ApiControllerBase
{
    private readonly SetupService _setup;
    private readonly SystemContext _system;

    public SetupController(SetupService setup, SystemContext system) { _setup = setup; _system = system; }

    [HttpGet("status")]
    public async Task<SetupStatus> Status()
    {
        var status = await _setup.StatusAsync(Ct);
        return status with { Error = status.Error ?? (DatabaseInitializer.Ready ? null : DatabaseInitializer.LastError) };
    }

    [HttpPost("complete")]
    [EnableRateLimiting("login")]
    public async Task<IActionResult> Complete([FromBody] SetupRequest req)
    {
        if (!DatabaseInitializer.Ready) throw new BusinessException("DATABASE_NOT_READY", "База данных не инициализирована: " + DatabaseInitializer.LastError);
        _system.Enabled = true;
        await _setup.CompleteAsync(req, Ct);
        return Ok(new { success = true });
    }
}
