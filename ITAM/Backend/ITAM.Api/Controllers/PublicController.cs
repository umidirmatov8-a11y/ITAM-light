using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Api.Controllers;

/// <summary>Anonymous endpoints: public info and the limited QR view of an asset (no personal data, no license keys).</summary>
[AllowAnonymous]
public sealed class PublicController : ApiControllerBase
{
    public sealed record PublicInfo(string OrganizationName, string Version, string DefaultLanguage, bool SetupCompleted, bool QrPublicView);
    public sealed record PublicAsset(Guid Id, string InventoryNumber, string? Name, string? Model, string? Status, string? StatusColor, string? Location, string OrganizationName);

    [HttpGet("info")]
    public async Task<PublicInfo> Info([FromServices] ISettingsService settings, [FromServices] AppDbContext db)
    {
        var general = await settings.GetAsync<GeneralSettings>(Ct);
        var qr = await settings.GetAsync<QrSettings>(Ct);
        bool completed;
        try { completed = await db.Users.IgnoreQueryFilters().AnyAsync(Ct); } catch { completed = false; }
        return new PublicInfo(general.OrganizationName, typeof(PublicController).Assembly.GetName().Version?.ToString(3) ?? "1.0.0", general.DefaultLanguage, completed, qr.PublicViewEnabled);
    }

    [HttpGet("assets/{id:guid}")]
    public async Task<PublicAsset> Asset(Guid id, [FromServices] ISettingsService settings, [FromServices] AppDbContext db)
    {
        var qr = await settings.GetAsync<QrSettings>(Ct);
        if (!qr.PublicViewEnabled) throw new ForbiddenException("Публичный просмотр по QR отключён администратором");
        var general = await settings.GetAsync<GeneralSettings>(Ct);
        var a = await db.Assets.AsNoTracking().Where(x => x.Id == id)
            .Select(x => new { x.Id, x.InventoryNumber, x.Name, x.Model, Manufacturer = x.Manufacturer != null ? x.Manufacturer.Name : null,
                Status = x.Status!.Name, x.Status.Color, Location = x.Location != null ? x.Location.Name : null })
            .FirstOrDefaultAsync(Ct) ?? throw new NotFoundException("Актив", id);
        return new PublicAsset(a.Id, a.InventoryNumber, a.Name, qr.ShowModel ? string.Join(' ', new[] { a.Manufacturer, a.Model }.Where(s => s is not null)) : null,
            qr.ShowStatus ? a.Status : null, qr.ShowStatus ? a.Color : null, qr.ShowLocation ? a.Location : null, general.OrganizationName);
    }
}
