using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace ITAM.Api.Middleware;

public sealed record ApiErrorBody(string Code, string Message, object? Details);
public sealed record ApiErrorEnvelope(bool Success, ApiErrorBody Error);

/// <summary>Converts exceptions into the unified error envelope { success:false, error:{ code, message, details } }.</summary>
public sealed class ErrorHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ErrorHandlingMiddleware> _log;
    private readonly IHostEnvironment _env;

    public ErrorHandlingMiddleware(RequestDelegate next, ILogger<ErrorHandlingMiddleware> log, IHostEnvironment env)
    {
        _next = next; _log = log; _env = env;
    }

    public async Task InvokeAsync(HttpContext ctx)
    {
        try
        {
            await _next(ctx);
        }
        catch (Exception ex) when (!ctx.Response.HasStarted)
        {
            var (status, code, message, details) = Map(ex);
            if (status >= 500) _log.LogError(ex, "Unhandled error on {Method} {Path}", ctx.Request.Method, ctx.Request.Path);
            else if (status == 409) _log.LogInformation("Conflict {Code} on {Method} {Path}: {Message}", code, ctx.Request.Method, ctx.Request.Path, message);
            ctx.Response.Clear();
            ctx.Response.StatusCode = status;
            ctx.Response.ContentType = "application/json; charset=utf-8";
            await ctx.Response.WriteAsync(JsonSerializer.Serialize(new ApiErrorEnvelope(false, new ApiErrorBody(code, message, details)), Json.Options));
        }
    }

    private (int, string, string, object?) Map(Exception ex)
    {
        switch (ex)
        {
            case BusinessException be:
                return (be.StatusCode, be.Code, be.Message, be.Details);
            case DbUpdateConcurrencyException:
                return (409, ErrorCodes.ConcurrentModification, "Данные были изменены другим пользователем. Обновите страницу и повторите операцию.", null);
            case DbUpdateException { InnerException: PostgresException pg }:
                return MapPostgres(pg);
            case PostgresException pg2:
                return MapPostgres(pg2);
            case AntiforgeryValidationException:
                return (400, "CSRF_INVALID", "Недействительный CSRF-токен. Обновите страницу.", null);
            case BadHttpRequestException bad:
                return (bad.StatusCode, "BAD_REQUEST", "Некорректный запрос", null);
            case OperationCanceledException:
                return (499, "CANCELLED", "Запрос отменён", null);
            case JsonException:
                return (400, "BAD_JSON", "Некорректный JSON", null);
            default:
                return (500, "INTERNAL_ERROR", _env.IsDevelopment() ? ex.Message : "Внутренняя ошибка сервера. Подробности в журнале.", null);
        }
    }

    private static (int, string, string, object?) MapPostgres(PostgresException pg) => pg.SqlState switch
    {
        PostgresErrorCodes.UniqueViolation when pg.ConstraintName == "UX_Assignments_OneOpenPerAsset"
            => (409, ErrorCodes.AssetAlreadyAssigned, "Актив уже выдан другому сотруднику", null),
        PostgresErrorCodes.UniqueViolation => (409, ErrorCodes.Duplicate, "Запись с такими данными уже существует", new { constraint = pg.ConstraintName }),
        PostgresErrorCodes.ForeignKeyViolation => (409, ErrorCodes.HasDependencies, "Операция нарушает связи данных (объект используется или ссылка недействительна)", new { constraint = pg.ConstraintName }),
        PostgresErrorCodes.SerializationFailure or PostgresErrorCodes.DeadlockDetected
            => (409, ErrorCodes.ConcurrentModification, "Конфликт параллельных изменений. Повторите операцию.", null),
        PostgresErrorCodes.RaiseException => (409, "DB_RULE", pg.MessageText, null),
        _ => (500, "DATABASE_ERROR", "Ошибка базы данных", null)
    };
}

public sealed class SecurityHeadersMiddleware
{
    private readonly RequestDelegate _next;
    public SecurityHeadersMiddleware(RequestDelegate next) => _next = next;

    public Task InvokeAsync(HttpContext ctx)
    {
        var h = ctx.Response.Headers;
        h["X-Content-Type-Options"] = "nosniff";
        h["X-Frame-Options"] = "DENY";
        h["Referrer-Policy"] = "strict-origin-when-cross-origin";
        h["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()";
        h["Cross-Origin-Opener-Policy"] = "same-origin";
        if (!ctx.Request.Path.StartsWithSegments("/swagger"))
            h["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; " +
                                           "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'";
        if (ctx.Request.Path.StartsWithSegments("/api")) h["Cache-Control"] = "no-store";
        return _next(ctx);
    }
}

/// <summary>CSRF protection for cookie-authenticated state-changing requests (double submit: cookie XSRF-TOKEN → header X-XSRF-TOKEN).</summary>
public sealed class AntiforgeryMiddleware
{
    private static readonly HashSet<string> Safe = new(StringComparer.OrdinalIgnoreCase) { "GET", "HEAD", "OPTIONS", "TRACE" };
    private readonly RequestDelegate _next;
    public AntiforgeryMiddleware(RequestDelegate next) => _next = next;

    public async Task InvokeAsync(HttpContext ctx, IAntiforgery antiforgery)
    {
        var path = ctx.Request.Path;
        if (path.StartsWithSegments("/api") && !Safe.Contains(ctx.Request.Method)
            && ctx.User.Identity?.IsAuthenticated == true && ctx.User.FindFirst("itam:auth")?.Value == "cookie")
        {
            await antiforgery.ValidateRequestAsync(ctx);
        }
        await _next(ctx);
    }

    public static void IssueToken(HttpContext ctx, IAntiforgery antiforgery)
    {
        var tokens = antiforgery.GetAndStoreTokens(ctx);
        ctx.Response.Cookies.Append("XSRF-TOKEN", tokens.RequestToken!, new CookieOptions
        {
            HttpOnly = false, SameSite = SameSiteMode.Strict, Secure = ctx.Request.IsHttps, Path = "/", IsEssential = true
        });
    }
}

/// <summary>Users who must change their password can only use the auth endpoints.</summary>
public sealed class PasswordChangeMiddleware
{
    private readonly RequestDelegate _next;
    public PasswordChangeMiddleware(RequestDelegate next) => _next = next;

    public async Task InvokeAsync(HttpContext ctx)
    {
        if (ctx.User.FindFirst(Auth.ItamClaims.MustChangePassword)?.Value == "true"
            && ctx.Request.Path.StartsWithSegments("/api") && !ctx.Request.Path.StartsWithSegments("/api/auth")
            && !ctx.Request.Path.StartsWithSegments("/api/setup") && !ctx.Request.Path.StartsWithSegments("/api/public"))
        {
            ctx.Response.StatusCode = 403;
            ctx.Response.ContentType = "application/json; charset=utf-8";
            await ctx.Response.WriteAsync("{\"success\":false,\"error\":{\"code\":\"PASSWORD_CHANGE_REQUIRED\",\"message\":\"Необходимо сменить пароль\"}}");
            return;
        }
        await _next(ctx);
    }
}
