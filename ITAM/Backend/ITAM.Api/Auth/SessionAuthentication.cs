using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using ITAM.Application.Auth;
using ITAM.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Options;

namespace ITAM.Api.Auth;

public sealed class SessionAuthenticationOptions : AuthenticationSchemeOptions
{
    public string CookieName { get; set; } = "itam.sid";
    public bool SecureCookies { get; set; }
}

/// <summary>
/// Authentication: an HttpOnly cookie carrying a protected server-side session id (revocable, idle timeout),
/// or "Authorization: Bearer itam_..." personal API tokens for integrations.
/// </summary>
public sealed class SessionAuthenticationHandler : AuthenticationHandler<SessionAuthenticationOptions>
{
    public new const string Scheme = "ItamSession";
    private const string Purpose = "ITAM.Session.v1";
    private readonly IDataProtector _protector;
    private readonly IMemoryCache _cache;

    public SessionAuthenticationHandler(IOptionsMonitor<SessionAuthenticationOptions> options, ILoggerFactory logger, UrlEncoder encoder,
        IDataProtectionProvider dp, IMemoryCache cache) : base(options, logger, encoder)
    {
        _protector = dp.CreateProtector(Purpose);
        _cache = cache;
    }

    public static string CacheKey(Guid sessionId) => "session:" + sessionId;

    protected override async Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        var auth = Request.Headers.Authorization.ToString();
        if (auth.StartsWith("Bearer itam_", StringComparison.Ordinal)) return await AuthenticateTokenAsync(auth["Bearer ".Length..]);

        if (!Request.Cookies.TryGetValue(Options.CookieName, out var raw) || string.IsNullOrEmpty(raw)) return AuthenticateResult.NoResult();
        Guid sessionId;
        try { sessionId = Guid.Parse(_protector.Unprotect(raw)); }
        catch (Exception ex) when (ex is CryptographicException or FormatException) { return AuthenticateResult.Fail("invalid session cookie"); }

        if (!_cache.TryGetValue(CacheKey(sessionId), out SessionPrincipal? principal))
        {
            var auth2 = Context.RequestServices.GetRequiredService<AuthService>();
            principal = await auth2.ValidateSessionAsync(sessionId, Context.RequestAborted);
            if (principal is null) return AuthenticateResult.Fail("session expired");
            _cache.Set(CacheKey(sessionId), principal, TimeSpan.FromSeconds(30));
        }
        return AuthenticateResult.Success(new AuthenticationTicket(BuildPrincipal(principal!, "cookie"), Scheme));
    }

    private async Task<AuthenticateResult> AuthenticateTokenAsync(string token)
    {
        var hash = HashToken(token);
        var db = Context.RequestServices.GetRequiredService<AppDbContext>();
        var now = DateTime.UtcNow;
        var row = await db.ApiTokens.Include(t => t.User).FirstOrDefaultAsync(t => t.TokenHash == hash, Context.RequestAborted);
        if (row is null || row.RevokedAt is not null || row.ExpiresAt < now || row.User is null || !row.User.IsActive || row.User.IsDeleted)
            return AuthenticateResult.Fail("invalid token");
        if (row.LastUsedAt is null || row.LastUsedAt < now.AddMinutes(-5))
        {
            row.LastUsedAt = now;
            await db.SaveChangesAsync(Context.RequestAborted);
        }
        var roleIds = await db.UserRoles.Where(r => r.UserId == row.UserId).Select(r => r.RoleId).ToListAsync();
        var perms = await db.RolePermissions.Where(rp => roleIds.Contains(rp.RoleId)).Select(rp => rp.PermissionCode).Distinct().ToListAsync();
        var regions = await db.UserRegions.Where(r => r.UserId == row.UserId).Select(r => r.RegionId).ToListAsync();
        var p = new SessionPrincipal(Guid.Empty, row.UserId, row.User.UserName, row.User.DisplayName,
            row.User.AllRegions || perms.Contains(Domain.Security.Permissions.SystemAdmin), regions, perms, false);
        return AuthenticateResult.Success(new AuthenticationTicket(BuildPrincipal(p, "token"), Scheme));
    }

    public static string HashToken(string token) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(token))).ToLowerInvariant();

    public static ClaimsPrincipal BuildPrincipal(SessionPrincipal p, string method)
    {
        var claims = new List<Claim>
        {
            new(ClaimTypes.Name, p.UserName),
            // Stable identity claim: antiforgery binds CSRF tokens to it. Without it the token would be bound to a hash of all
            // claims (including the permission list), and a reloaded session could invalidate a valid token.
            new(ClaimTypes.NameIdentifier, p.UserId.ToString()),
            new(ItamClaims.UserId, p.UserId.ToString()),
            new(ItamClaims.SessionId, p.SessionId.ToString()),
            new(ItamClaims.DisplayName, p.DisplayName),
            new(ItamClaims.AllRegions, p.AllRegions ? "true" : "false"),
            new(ItamClaims.MustChangePassword, p.MustChangePassword ? "true" : "false"),
            new("itam:auth", method),
        };
        claims.AddRange(p.Permissions.Select(x => new Claim(ItamClaims.Permission, x)));
        claims.AddRange(p.RegionIds.Select(x => new Claim(ItamClaims.Region, x.ToString())));
        return new ClaimsPrincipal(new ClaimsIdentity(claims, Scheme, ClaimTypes.Name, ClaimTypes.Role));
    }

    protected override Task HandleChallengeAsync(AuthenticationProperties properties)
    {
        Response.StatusCode = 401;
        Response.ContentType = "application/json";
        return Response.WriteAsync("{\"success\":false,\"error\":{\"code\":\"UNAUTHORIZED\",\"message\":\"Требуется вход в систему\"}}");
    }

    protected override Task HandleForbiddenAsync(AuthenticationProperties properties)
    {
        Response.StatusCode = 403;
        Response.ContentType = "application/json";
        return Response.WriteAsync("{\"success\":false,\"error\":{\"code\":\"FORBIDDEN\",\"message\":\"Недостаточно прав\"}}");
    }

    public string Protect(Guid sessionId) => _protector.Protect(sessionId.ToString());
}

/// <summary>Issues and clears the session cookie.</summary>
public sealed class SessionCookieService
{
    private readonly IDataProtector _protector;
    private readonly IOptionsMonitor<SessionAuthenticationOptions> _options;
    private readonly IMemoryCache _cache;

    public SessionCookieService(IDataProtectionProvider dp, IOptionsMonitor<SessionAuthenticationOptions> options, IMemoryCache cache)
    {
        _protector = dp.CreateProtector("ITAM.Session.v1");
        _options = options;
        _cache = cache;
    }

    private CookieOptions CookieOptions(HttpContext ctx, DateTimeOffset? expires)
    {
        var o = _options.Get(SessionAuthenticationHandler.Scheme);
        return new CookieOptions
        {
            HttpOnly = true,
            Secure = o.SecureCookies || ctx.Request.IsHttps,
            SameSite = SameSiteMode.Strict,
            Path = "/",
            Expires = expires,
            IsEssential = true,
        };
    }

    public void Issue(HttpContext ctx, Guid sessionId, DateTime expiresAt)
        => ctx.Response.Cookies.Append(_options.Get(SessionAuthenticationHandler.Scheme).CookieName, _protector.Protect(sessionId.ToString()),
            CookieOptions(ctx, new DateTimeOffset(expiresAt)));

    public void Clear(HttpContext ctx, Guid? sessionId)
    {
        ctx.Response.Cookies.Delete(_options.Get(SessionAuthenticationHandler.Scheme).CookieName, CookieOptions(ctx, null));
        if (sessionId is not null) _cache.Remove(SessionAuthenticationHandler.CacheKey(sessionId.Value));
    }

    public void Invalidate(Guid sessionId) => _cache.Remove(SessionAuthenticationHandler.CacheKey(sessionId));
}
