using System.Security.Cryptography;
using ITAM.Api.Auth;
using ITAM.Api.Middleware;
using ITAM.Application.Auth;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Infrastructure.Persistence;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Api.Controllers;

/// <summary>Authentication: login/logout, current user, password change, CSRF token, personal API tokens.</summary>
public sealed class AuthController : ApiControllerBase
{
    private readonly AuthService _auth;
    private readonly SessionCookieService _cookies;
    private readonly IAntiforgery _antiforgery;

    public AuthController(AuthService auth, SessionCookieService cookies, IAntiforgery antiforgery)
    {
        _auth = auth; _cookies = cookies; _antiforgery = antiforgery;
    }

    private Guid? SessionId => Guid.TryParse(User.FindFirst(ItamClaims.SessionId)?.Value, out var g) && g != Guid.Empty ? g : null;

    /// <summary>Signs in and issues an HttpOnly session cookie.</summary>
    [HttpPost("login")]
    [AllowAnonymous]
    [EnableRateLimiting("login")]
    public async Task<ActionResult<MeDto>> Login([FromBody] LoginRequest req)
    {
        var result = await _auth.LoginAsync(req, HttpContext.Connection.RemoteIpAddress?.ToString(), Request.Headers.UserAgent.ToString(), Ct);
        _cookies.Issue(HttpContext, result.Principal.SessionId, result.ExpiresAt);
        HttpContext.User = SessionAuthenticationHandler.BuildPrincipal(result.Principal, "cookie");
        AntiforgeryMiddleware.IssueToken(HttpContext, _antiforgery);
        return await _auth.MeAsync(Ct);
    }

    [HttpPost("logout")]
    [AllowAnonymous]
    public async Task<IActionResult> Logout()
    {
        if (SessionId is { } sid) await _auth.LogoutAsync(sid, Ct);
        _cookies.Clear(HttpContext, SessionId);
        return Ok(new { success = true });
    }

    /// <summary>Current user, permissions and regional scope. Also refreshes the CSRF token.</summary>
    [HttpGet("me")]
    [Authorize]
    public async Task<ActionResult<MeDto>> Me()
    {
        AntiforgeryMiddleware.IssueToken(HttpContext, _antiforgery);
        return await _auth.MeAsync(Ct);
    }

    [HttpGet("csrf")]
    [AllowAnonymous]
    public IActionResult Csrf()
    {
        AntiforgeryMiddleware.IssueToken(HttpContext, _antiforgery);
        return Ok(new { success = true });
    }

    [HttpPost("change-password")]
    [Authorize]
    public async Task<IActionResult> ChangePassword([FromBody] ChangePasswordRequest req)
    {
        await _auth.ChangePasswordAsync(req, SessionId ?? Guid.Empty, Ct);
        if (SessionId is { } sid) _cookies.Invalidate(sid);
        return Ok(new { success = true });
    }

    public sealed record PreferencesRequest(string? Preferences, string? Language);

    [HttpPut("preferences")]
    [Authorize]
    public async Task<IActionResult> Preferences([FromBody] PreferencesRequest req)
    {
        await _auth.SavePreferencesAsync(req.Preferences, req.Language, Ct);
        return Ok(new { success = true });
    }

    public sealed record ApiTokenDto(Guid Id, string Name, string Prefix, DateTime CreatedAt, DateTime? ExpiresAt, DateTime? LastUsedAt, DateTime? RevokedAt);
    public sealed record CreateTokenRequest(string Name, int? ExpiresInDays);
    public sealed record CreatedTokenDto(ApiTokenDto Token, string Secret);

    /// <summary>Personal API tokens of the current user (for integrations, Power BI, scripts).</summary>
    [HttpGet("tokens")]
    [Authorize]
    public async Task<IReadOnlyList<ApiTokenDto>> Tokens([FromServices] AppDbContext db, [FromServices] ICurrentUser user)
        => await db.ApiTokens.Where(t => t.UserId == user.UserId).OrderByDescending(t => t.CreatedAt)
            .Select(t => new ApiTokenDto(t.Id, t.Name, t.Prefix, t.CreatedAt, t.ExpiresAt, t.LastUsedAt, t.RevokedAt)).ToListAsync(Ct);

    [HttpPost("tokens")]
    [Authorize]
    public async Task<CreatedTokenDto> CreateToken([FromBody] CreateTokenRequest req, [FromServices] AppDbContext db, [FromServices] ICurrentUser user, [FromServices] IAuditService audit)
    {
        if (string.IsNullOrWhiteSpace(req.Name) || req.Name.Length > 128) throw new ValidationFailedException("Укажите название токена");
        var secret = "itam_" + Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).Replace("+", "").Replace("/", "").Replace("=", "");
        var token = new ApiToken
        {
            UserId = user.UserId!.Value, Name = req.Name.Trim(), TokenHash = SessionAuthenticationHandler.HashToken(secret), Prefix = secret[..10],
            CreatedAt = DateTime.UtcNow, ExpiresAt = req.ExpiresInDays is > 0 ? DateTime.UtcNow.AddDays(req.ExpiresInDays.Value) : null
        };
        db.ApiTokens.Add(token);
        audit.Log("apitoken.create", nameof(ApiToken), token.Id, token.Name);
        await db.SaveChangesAsync(Ct);
        return new CreatedTokenDto(new ApiTokenDto(token.Id, token.Name, token.Prefix, token.CreatedAt, token.ExpiresAt, null, null), secret);
    }

    [HttpDelete("tokens/{id:guid}")]
    [Authorize]
    public async Task<IActionResult> RevokeToken(Guid id, [FromServices] AppDbContext db, [FromServices] ICurrentUser user, [FromServices] IAuditService audit)
    {
        var token = await db.ApiTokens.FirstOrDefaultAsync(t => t.Id == id && t.UserId == user.UserId, Ct) ?? throw new NotFoundException("Токен", id);
        token.RevokedAt = DateTime.UtcNow;
        audit.Log("apitoken.revoke", nameof(ApiToken), token.Id, token.Name);
        await db.SaveChangesAsync(Ct);
        return Ok(new { success = true });
    }
}
