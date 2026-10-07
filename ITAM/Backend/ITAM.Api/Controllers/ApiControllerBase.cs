using ITAM.Application.Common;
using Microsoft.AspNetCore.Mvc;

namespace ITAM.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public abstract class ApiControllerBase : ControllerBase
{
    protected CancellationToken Ct => HttpContext.RequestAborted;

    protected FileContentResult Export(TabularData data, string? format, string baseName)
    {
        var exporter = HttpContext.RequestServices.GetRequiredService<ITabularExporter>();
        var stamp = DateTime.Now.ToString("yyyyMMdd-HHmm");
        return (format ?? "xlsx").ToLowerInvariant() switch
        {
            "csv" => File(exporter.ToCsv(data), "text/csv; charset=utf-8", $"{baseName}-{stamp}.csv"),
            "pdf" => File(exporter.ToPdf(data, $"Сформировано {DateTime.Now:dd.MM.yyyy HH:mm}"), "application/pdf", $"{baseName}-{stamp}.pdf"),
            _ => File(exporter.ToXlsx(data), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", $"{baseName}-{stamp}.xlsx"),
        };
    }

    protected void EnsurePermission(string permission)
    {
        if (!HttpContext.RequestServices.GetRequiredService<ICurrentUser>().Has(permission))
            throw new ITAM.Domain.Common.ForbiddenException();
    }
}
