using System.ComponentModel.DataAnnotations;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Auth;

public sealed class LoginRequest
{
    [Required, MaxLength(128)] public string UserName { get; set; } = string.Empty;
    [Required, MaxLength(256)] public string Password { get; set; } = string.Empty;
}

public sealed class ChangePasswordRequest
{
    [Required] public string CurrentPassword { get; set; } = string.Empty;
    [Required, MaxLength(256)] public string NewPassword { get; set; } = string.Empty;
}

public sealed record SessionPrincipal(Guid SessionId, Guid UserId, string UserName, string DisplayName, bool AllRegions,
    IReadOnlyList<Guid> RegionIds, IReadOnlyList<string> Permissions, bool MustChangePassword);

public sealed record MeDto(Guid Id, string UserName, string DisplayName, string? Email, Guid? EmployeeId, bool AllRegions,
    IReadOnlyList<RegionRef> Regions, IReadOnlyList<string> Roles, IReadOnlyList<string> Permissions, bool MustChangePassword,
    string? Language, string? TimeZone, string? Preferences, DateTime? LastLoginAt, string OrganizationName, string OrgTimeZone, string Currency, string DateFormat);

public sealed record RegionRef(Guid Id, string Name);

public sealed record LoginResult(SessionPrincipal Principal, DateTime ExpiresAt);

public static class PasswordPolicy
{
    public static IReadOnlyList<string> Validate(string password, SecuritySettings s)
    {
        var errors = new List<string>();
        if (password.Length < s.PasswordMinLength) errors.Add($"Минимальная длина пароля — {s.PasswordMinLength} символов");
        if (s.RequireUppercase && !password.Any(char.IsUpper)) errors.Add("Нужна хотя бы одна заглавная буква");
        if (s.RequireLowercase && !password.Any(char.IsLower)) errors.Add("Нужна хотя бы одна строчная буква");
        if (s.RequireDigit && !password.Any(char.IsDigit)) errors.Add("Нужна хотя бы одна цифра");
        if (s.RequireSpecial && password.All(char.IsLetterOrDigit)) errors.Add("Нужен хотя бы один спецсимвол");
        if (password.Length > 256) errors.Add("Пароль слишком длинный");
        return errors;
    }

    public static void Ensure(string password, SecuritySettings s)
    {
        var errors = Validate(password, s);
        if (errors.Count > 0)
            throw new ValidationFailedException(string.Join("; ", errors), new Dictionary<string, string[]> { ["password"] = errors.ToArray() });
    }
}

public sealed class AuthService
{
    private readonly IAppDbContext _db;
    private readonly IPasswordHasher _hasher;
    private readonly ISettingsService _settings;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly ICurrentUser _current;
    private readonly IEnumerable<IExternalAuthProvider> _external;

    public AuthService(IAppDbContext db, IPasswordHasher hasher, ISettingsService settings, IClock clock, IAuditService audit, ICurrentUser current,
        IEnumerable<IExternalAuthProvider> external)
    {
        _db = db; _hasher = hasher; _settings = settings; _clock = clock; _audit = audit; _current = current; _external = external;
    }

    public async Task<LoginResult> LoginAsync(LoginRequest req, string? ip, string? userAgent, CancellationToken ct)
    {
        var security = await _settings.GetAsync<SecuritySettings>(ct);
        var normalized = req.UserName.Trim().ToUpperInvariant();
        var user = await _db.Users.FirstOrDefaultAsync(u => u.NormalizedUserName == normalized, ct);
        var now = _clock.UtcNow;

        if (user is null || !user.IsActive)
        {
            // Same response for unknown and disabled users (no user enumeration); hash anyway against timing attacks.
            _hasher.Hash(req.Password);
            await _audit.LogNowAsync("auth.login.failed", nameof(User), user?.Id, req.UserName, null, null, user is null ? "unknown user" : "disabled", false, req.UserName, user?.Id, ct);
            throw new BusinessException(ErrorCodes.InvalidCredentials, "Неверное имя пользователя или пароль") ;
        }
        if (user.LockoutEnd is not null && user.LockoutEnd > now)
        {
            await _audit.LogNowAsync("auth.login.locked", nameof(User), user.Id, user.UserName, null, null, null, false, user.UserName, user.Id, ct);
            throw new BusinessException(ErrorCodes.AccountLocked, $"Учётная запись временно заблокирована до {user.LockoutEnd:HH:mm} UTC после неудачных попыток входа");
        }

        bool ok;
        if (user.AuthProvider == "Local")
        {
            var rehash = false;
            ok = user.PasswordHash is not null && _hasher.Verify(user.PasswordHash, req.Password, out rehash);
            if (ok && rehash) user.PasswordHash = _hasher.Hash(req.Password);
        }
        else
        {
            var provider = _external.FirstOrDefault(p => p.Name == user.AuthProvider)
                           ?? throw new BusinessException("AUTH_PROVIDER_UNAVAILABLE", $"Провайдер аутентификации {user.AuthProvider} не настроен");
            ok = await provider.AuthenticateAsync(user.UserName, req.Password, ct) is not null;
        }

        if (!ok)
        {
            user.FailedLoginCount++;
            if (security.LockoutThreshold > 0 && user.FailedLoginCount >= security.LockoutThreshold)
            {
                user.LockoutEnd = now.AddMinutes(security.LockoutMinutes);
                user.FailedLoginCount = 0;
            }
            await _db.SaveChangesAsync(ct);
            await _audit.LogNowAsync("auth.login.failed", nameof(User), user.Id, user.UserName, null, null,
                user.LockoutEnd > now ? "account locked" : "bad password", false, user.UserName, user.Id, ct);
            throw new BusinessException(ErrorCodes.InvalidCredentials, "Неверное имя пользователя или пароль");
        }

        user.FailedLoginCount = 0;
        user.LockoutEnd = null;
        user.LastLoginAt = now;
        user.LastLoginIp = ip;
        var mustChange = user.MustChangePassword
                         || security.PasswordMaxAgeDays > 0 && user.PasswordChangedAt is not null && user.PasswordChangedAt < now.AddDays(-security.PasswordMaxAgeDays);
        var session = new UserSession
        {
            UserId = user.Id,
            CreatedAt = now,
            LastSeenAt = now,
            ExpiresAt = now.AddHours(security.SessionAbsoluteHours),
            IpAddress = ip,
            UserAgent = userAgent is { Length: > 500 } ? userAgent[..500] : userAgent,
        };
        _db.UserSessions.Add(session);
        await _db.SaveChangesAsync(ct);
        await _audit.LogNowAsync("auth.login", nameof(User), user.Id, user.UserName, null, new { ip }, null, true, user.UserName, user.Id, ct);
        var principal = await BuildPrincipalAsync(user, session.Id, mustChange, ct);
        return new LoginResult(principal, session.ExpiresAt);
    }

    private async Task<SessionPrincipal> BuildPrincipalAsync(User user, Guid sessionId, bool mustChange, CancellationToken ct)
    {
        var roleIds = await _db.UserRoles.Where(r => r.UserId == user.Id).Select(r => r.RoleId).ToListAsync(ct);
        var permissions = await _db.RolePermissions.Where(rp => roleIds.Contains(rp.RoleId)).Select(rp => rp.PermissionCode).Distinct().ToListAsync(ct);
        var regions = await _db.UserRegions.Where(r => r.UserId == user.Id).Select(r => r.RegionId).ToListAsync(ct);
        var all = user.AllRegions || permissions.Contains(Permissions.SystemAdmin);
        return new SessionPrincipal(sessionId, user.Id, user.UserName, user.DisplayName, all, regions, permissions, mustChange);
    }

    /// <summary>Validates a session (revocation, idle timeout, absolute expiry, user state). Returns null when invalid.</summary>
    public async Task<SessionPrincipal?> ValidateSessionAsync(Guid sessionId, CancellationToken ct)
    {
        var security = await _settings.GetAsync<SecuritySettings>(ct);
        var now = _clock.UtcNow;
        var session = await _db.UserSessions.Include(s => s.User).FirstOrDefaultAsync(s => s.Id == sessionId, ct);
        if (session is null || session.RevokedAt is not null || session.ExpiresAt < now) return null;
        if (session.LastSeenAt.AddMinutes(security.SessionIdleMinutes) < now)
        {
            session.RevokedAt = now;
            session.RevokeReason = "idle timeout";
            await _db.SaveChangesAsync(ct);
            return null;
        }
        var user = session.User;
        if (user is null || user.IsDeleted || !user.IsActive) return null;
        if (session.LastSeenAt < now.AddSeconds(-60))
        {
            session.LastSeenAt = now;
            await _db.SaveChangesAsync(ct);
        }
        return await BuildPrincipalAsync(user, session.Id, user.MustChangePassword, ct);
    }

    public async Task LogoutAsync(Guid sessionId, CancellationToken ct)
    {
        var session = await _db.UserSessions.FirstOrDefaultAsync(s => s.Id == sessionId, ct);
        if (session is null || session.RevokedAt is not null) return;
        session.RevokedAt = _clock.UtcNow;
        session.RevokeReason = "logout";
        await _db.SaveChangesAsync(ct);
        await _audit.LogNowAsync("auth.logout", nameof(User), session.UserId, _current.UserName, ct: ct);
    }

    public async Task<MeDto> MeAsync(CancellationToken ct)
    {
        var userId = _current.UserId ?? throw new ForbiddenException();
        var user = await _db.Users.AsNoTracking().FirstAsync(u => u.Id == userId, ct);
        var roles = await _db.UserRoles.Where(r => r.UserId == userId).Select(r => r.Role!.Name).ToListAsync(ct);
        var regions = _current.AllRegions
            ? await _db.Regions.Where(r => !r.IsArchived).OrderBy(r => r.SortOrder).ThenBy(r => r.Name).Select(r => new RegionRef(r.Id, r.Name)).ToListAsync(ct)
            : await _db.UserRegions.Where(r => r.UserId == userId).Select(r => new RegionRef(r.RegionId, r.Region!.Name)).ToListAsync(ct);
        var general = await _settings.GetAsync<GeneralSettings>(ct);
        return new MeDto(user.Id, user.UserName, user.DisplayName, user.Email, user.EmployeeId, _current.AllRegions, regions, roles,
            _current.Permissions.OrderBy(p => p).ToList(), user.MustChangePassword, user.Language ?? general.DefaultLanguage, user.TimeZone,
            user.Preferences, user.LastLoginAt, general.OrganizationName, general.TimeZone, general.Currency, general.DateFormat);
    }

    public async Task ChangePasswordAsync(ChangePasswordRequest req, Guid currentSessionId, CancellationToken ct)
    {
        var userId = _current.UserId ?? throw new ForbiddenException();
        var user = await _db.Users.FirstAsync(u => u.Id == userId, ct);
        if (user.AuthProvider != "Local") throw new BusinessException("EXTERNAL_ACCOUNT", "Пароль управляется внешним каталогом");
        if (user.PasswordHash is null || !_hasher.Verify(user.PasswordHash, req.CurrentPassword, out _))
            throw new BusinessException(ErrorCodes.InvalidCredentials, "Текущий пароль указан неверно");
        if (req.CurrentPassword == req.NewPassword) throw new ValidationFailedException("Новый пароль должен отличаться от текущего");
        PasswordPolicy.Ensure(req.NewPassword, await _settings.GetAsync<SecuritySettings>(ct));
        user.PasswordHash = _hasher.Hash(req.NewPassword);
        user.PasswordChangedAt = _clock.UtcNow;
        user.MustChangePassword = false;
        // Sign out all other sessions.
        foreach (var s in await _db.UserSessions.Where(s => s.UserId == userId && s.RevokedAt == null && s.Id != currentSessionId).ToListAsync(ct))
        {
            s.RevokedAt = _clock.UtcNow;
            s.RevokeReason = "password changed";
        }
        _audit.Log("auth.password.change", nameof(User), user.Id, user.UserName);
        await _db.SaveChangesAsync(ct);
    }

    public async Task SavePreferencesAsync(string? preferencesJson, string? language, CancellationToken ct)
    {
        var userId = _current.UserId ?? throw new ForbiddenException();
        var user = await _db.Users.FirstAsync(u => u.Id == userId, ct);
        if (preferencesJson is { Length: > 20000 }) throw new ValidationFailedException("Слишком большие настройки интерфейса");
        if (preferencesJson is not null) user.Preferences = Json.ToElement(preferencesJson) is null ? null : preferencesJson;
        if (language is not null) user.Language = language is "ru" or "en" or "uz" ? language : user.Language;
        await _db.SaveChangesAsync(ct);
    }
}
