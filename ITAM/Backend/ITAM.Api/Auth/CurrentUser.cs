using System.Security.Claims;
using ITAM.Application.Common;
using ITAM.Domain.Security;

namespace ITAM.Api.Auth;

public static class ItamClaims
{
    public const string UserId = "itam:uid";
    public const string SessionId = "itam:sid";
    public const string Permission = "itam:perm";
    public const string Region = "itam:region";
    public const string AllRegions = "itam:allregions";
    public const string MustChangePassword = "itam:mustchange";
    public const string DisplayName = "itam:display";
}

/// <summary>Current user resolved from the authenticated principal; background jobs/CLI/setup run as "system".</summary>
public sealed class HttpCurrentUser : ICurrentUser
{
    private readonly IHttpContextAccessor _http;
    private readonly SystemContext _system;
    private HashSet<string>? _permissions;
    private List<Guid>? _regions;

    public HttpCurrentUser(IHttpContextAccessor http, SystemContext system) { _http = http; _system = system; }

    private ClaimsPrincipal? Principal => _http.HttpContext?.User is { Identity.IsAuthenticated: true } p ? p : null;
    private bool IsSystem => _system.Enabled || _http.HttpContext is null;

    public Guid? UserId => Guid.TryParse(Principal?.FindFirstValue(ItamClaims.UserId), out var id) ? id : null;
    public string? UserName => Principal?.Identity?.Name ?? (IsSystem ? "system" : null);
    public string? DisplayName => Principal?.FindFirstValue(ItamClaims.DisplayName) ?? UserName;
    public bool IsAuthenticated => Principal is not null && !_system.Enabled;
    public bool AllRegions => IsSystem || Principal?.FindFirstValue(ItamClaims.AllRegions) == "true";
    public IReadOnlyCollection<Guid> RegionIds => _regions ??= Principal?.FindAll(ItamClaims.Region).Select(c => Guid.Parse(c.Value)).ToList() ?? new List<Guid>();
    public IReadOnlySet<string> Permissions => _permissions ??= IsSystem && Principal is null
        ? Domain.Security.Permissions.All.ToHashSet()
        : Principal?.FindAll(ItamClaims.Permission).Select(c => c.Value).ToHashSet() ?? new HashSet<string>();
    public string? IpAddress => _http.HttpContext?.Connection.RemoteIpAddress?.ToString();
    public string? UserAgent => _http.HttpContext?.Request.Headers.UserAgent.ToString();

    public bool Has(string permission)
    {
        if (IsSystem) return true;
        if (permission == Domain.Security.Permissions.ScopeOwnDepartment) return Permissions.Contains(permission);
        return Permissions.Contains(permission) || Permissions.Contains(Domain.Security.Permissions.SystemAdmin);
    }
}
