using System.ComponentModel.DataAnnotations;
using ITAM.Application.Auth;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Admin;

public sealed class UserInput
{
    [Required, MaxLength(128), RegularExpression(@"^[A-Za-z0-9._@\-]+$", ErrorMessage = "Логин: латинские буквы, цифры, . _ @ -")]
    public string UserName { get; set; } = string.Empty;
    [Required, MaxLength(256)] public string DisplayName { get; set; } = string.Empty;
    [EmailAddress, MaxLength(256)] public string? Email { get; set; }
    /// <summary>Required on create; ignored on update (use reset password).</summary>
    [MaxLength(256)] public string? Password { get; set; }
    public bool IsActive { get; set; } = true;
    public bool MustChangePassword { get; set; } = true;
    public bool AllRegions { get; set; }
    public List<Guid> RoleIds { get; set; } = new();
    public List<Guid> RegionIds { get; set; } = new();
    public Guid? EmployeeId { get; set; }
    [MaxLength(8)] public string? Language { get; set; }
}

public sealed class ResetPasswordRequest
{
    [Required, MaxLength(256)] public string NewPassword { get; set; } = string.Empty;
    public bool MustChangePassword { get; set; } = true;
}

public sealed record UserDto(Guid Id, string UserName, string DisplayName, string? Email, bool IsActive, bool IsLocked, DateTime? LockoutEnd,
    DateTime? LastLoginAt, string? LastLoginIp, bool MustChangePassword, bool AllRegions, string AuthProvider, Guid? EmployeeId, string? EmployeeName,
    IReadOnlyList<RoleRef> Roles, IReadOnlyList<RegionRef> Regions, DateTime CreatedAt);

public sealed record RoleRef(Guid Id, string Name, string Code);

public sealed class RoleInput
{
    [Required, MaxLength(128)] public string Name { get; set; } = string.Empty;
    [Required, MaxLength(64), RegularExpression(@"^[a-z0-9_\-]+$")] public string Code { get; set; } = string.Empty;
    [MaxLength(1000)] public string? Description { get; set; }
    public List<string> Permissions { get; set; } = new();
}

public sealed record RoleDto(Guid Id, string Name, string Code, string? Description, bool IsSystem, IReadOnlyList<string> Permissions, int UserCount);

public sealed record PermissionDto(string Code, string Group, string Description);

public sealed record SessionDto(Guid Id, Guid UserId, string UserName, DateTime CreatedAt, DateTime LastSeenAt, DateTime ExpiresAt, string? IpAddress, string? UserAgent, bool IsCurrent);

public sealed class UserAdminService
{
    private readonly IAppDbContext _db;
    private readonly IPasswordHasher _hasher;
    private readonly ISettingsService _settings;
    private readonly ICurrentUser _current;
    private readonly IClock _clock;
    private readonly IAuditService _audit;

    public UserAdminService(IAppDbContext db, IPasswordHasher hasher, ISettingsService settings, ICurrentUser current, IClock clock, IAuditService audit)
    {
        _db = db; _hasher = hasher; _settings = settings; _current = current; _clock = clock; _audit = audit;
    }

    private bool IsSuper => _current.Has(Permissions.SystemAdmin);

    public async Task<PagedResult<UserDto>> ListAsync(PagedRequest q, CancellationToken ct)
    {
        var query = _db.Users.AsNoTracking().AsQueryable();
        if (!string.IsNullOrWhiteSpace(q.Search))
        {
            var like = QueryableExtensions.LikePattern(q.Search);
            query = query.Where(u => EF.Functions.ILike(u.UserName, like) || EF.Functions.ILike(u.DisplayName, like) || (u.Email != null && EF.Functions.ILike(u.Email, like)));
        }
        if (!q.IncludeArchived) query = query.Where(u => u.IsActive);
        var total = await query.CountAsync(ct);
        var ids = await query.OrderBy(u => u.UserName).Skip((q.SafePage - 1) * q.SafePageSize).Take(q.SafePageSize).Select(u => u.Id).ToListAsync(ct);
        var items = new List<UserDto>();
        foreach (var id in ids) items.Add(await GetAsync(id, ct));
        return new PagedResult<UserDto>(items, total, q.SafePage, q.SafePageSize);
    }

    public async Task<UserDto> GetAsync(Guid id, CancellationToken ct)
    {
        var u = await _db.Users.AsNoTracking().FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException("Пользователь", id);
        var roles = await _db.UserRoles.Where(r => r.UserId == id).Select(r => new RoleRef(r.RoleId, r.Role!.Name, r.Role.Code)).ToListAsync(ct);
        var regions = await _db.UserRegions.Where(r => r.UserId == id).Select(r => new RegionRef(r.RegionId, r.Region!.Name)).ToListAsync(ct);
        var emp = u.EmployeeId is null ? null : await _db.Employees.Where(e => e.Id == u.EmployeeId).Select(e => e.FullName).FirstOrDefaultAsync(ct);
        return new UserDto(u.Id, u.UserName, u.DisplayName, u.Email, u.IsActive, u.LockoutEnd > _clock.UtcNow, u.LockoutEnd, u.LastLoginAt, u.LastLoginIp,
            u.MustChangePassword, u.AllRegions, u.AuthProvider, u.EmployeeId, emp, roles, regions, u.CreatedAt);
    }

    private async Task GuardEscalationAsync(IEnumerable<Guid> roleIds, CancellationToken ct)
    {
        if (IsSuper) return;
        var granted = await _db.RolePermissions.Where(rp => roleIds.Contains(rp.RoleId)).Select(rp => rp.PermissionCode).Distinct().ToListAsync(ct);
        var notHeld = granted.Where(p => !_current.Has(p) && p != Permissions.ScopeOwnDepartment).ToList();
        if (notHeld.Count > 0)
            throw new ForbiddenException("Нельзя назначить роль с правами, которых нет у вас: " + string.Join(", ", notHeld));
    }

    public async Task<UserDto> SaveAsync(Guid? id, UserInput input, CancellationToken ct)
    {
        var normalized = input.UserName.Trim().ToUpperInvariant();
        if (await _db.Users.AnyAsync(u => u.NormalizedUserName == normalized && u.Id != id, ct))
            throw new ConflictException(ErrorCodes.Duplicate, $"Пользователь {input.UserName} уже существует");
        await GuardEscalationAsync(input.RoleIds, ct);
        if (input.AllRegions && !_current.AllRegions) throw new ForbiddenException("Нельзя выдать доступ ко всем регионам, не имея его");
        if (!_current.AllRegions && input.RegionIds.Any(r => !_current.RegionIds.Contains(r)))
            throw new ForbiddenException("Нельзя назначить регион, к которому у вас нет доступа");

        User user;
        if (id is null)
        {
            if (string.IsNullOrEmpty(input.Password)) throw new ValidationFailedException("Укажите пароль", new Dictionary<string, string[]> { ["password"] = new[] { "Обязательное поле" } });
            PasswordPolicy.Ensure(input.Password, await _settings.GetAsync<SecuritySettings>(ct));
            user = new User { PasswordHash = _hasher.Hash(input.Password), PasswordChangedAt = _clock.UtcNow, MustChangePassword = input.MustChangePassword };
            _db.Users.Add(user);
        }
        else
        {
            user = await _db.Users.Include(u => u.Roles).Include(u => u.Regions).FirstOrDefaultAsync(u => u.Id == id, ct) ?? throw new NotFoundException("Пользователь", id);
            if (user.Id == _current.UserId && !input.IsActive) throw new BusinessException("SELF_LOCKOUT", "Нельзя отключить собственную учётную запись");
            await GuardEscalationAsync(user.Roles.Select(r => r.RoleId), ct);
            await EnsureNotLastSuperAdminAsync(user.Id, input.RoleIds, input.IsActive, ct);
            _db.UserRoles.RemoveRange(user.Roles);
            _db.UserRegions.RemoveRange(user.Regions);
            user.MustChangePassword = input.MustChangePassword && user.MustChangePassword;
        }
        user.UserName = input.UserName.Trim();
        user.NormalizedUserName = normalized;
        user.DisplayName = input.DisplayName.Trim();
        user.Email = input.Email;
        user.IsActive = input.IsActive;
        user.AllRegions = input.AllRegions;
        user.EmployeeId = input.EmployeeId;
        user.Language = input.Language;
        foreach (var r in input.RoleIds.Distinct()) _db.UserRoles.Add(new UserRole { UserId = user.Id, RoleId = r });
        foreach (var r in input.RegionIds.Distinct()) _db.UserRegions.Add(new UserRegion { UserId = user.Id, RegionId = r });
        _audit.Log(id is null ? "user.create" : "user.update", nameof(User), user.Id, user.UserName, null,
            new { roles = input.RoleIds, regions = input.RegionIds, input.AllRegions, input.IsActive });
        await _db.SaveChangesAsync(ct);
        if (!input.IsActive) await RevokeSessionsAsync(user.Id, "user disabled", ct);
        return await GetAsync(user.Id, ct);
    }

    private async Task EnsureNotLastSuperAdminAsync(Guid userId, IReadOnlyCollection<Guid> newRoleIds, bool stillActive, CancellationToken ct)
    {
        var superRole = await _db.Roles.Where(r => r.Code == BuiltInRoles.SuperAdmin).Select(r => (Guid?)r.Id).FirstOrDefaultAsync(ct);
        if (superRole is null) return;
        var isSuper = await _db.UserRoles.AnyAsync(r => r.UserId == userId && r.RoleId == superRole, ct);
        if (!isSuper || (newRoleIds.Contains(superRole.Value) && stillActive)) return;
        var others = await _db.UserRoles.CountAsync(r => r.RoleId == superRole && r.UserId != userId && r.User!.IsActive && !r.User.IsDeleted, ct);
        if (others == 0) throw new BusinessException("LAST_SUPERADMIN", "Нельзя убрать последнего суперадминистратора");
    }

    public async Task ResetPasswordAsync(Guid id, ResetPasswordRequest req, CancellationToken ct)
    {
        var user = await _db.Users.FirstOrDefaultAsync(u => u.Id == id, ct) ?? throw new NotFoundException("Пользователь", id);
        await GuardEscalationAsync(await _db.UserRoles.Where(r => r.UserId == id).Select(r => r.RoleId).ToListAsync(ct), ct);
        PasswordPolicy.Ensure(req.NewPassword, await _settings.GetAsync<SecuritySettings>(ct));
        user.PasswordHash = _hasher.Hash(req.NewPassword);
        user.PasswordChangedAt = _clock.UtcNow;
        user.MustChangePassword = req.MustChangePassword;
        user.FailedLoginCount = 0;
        user.LockoutEnd = null;
        _audit.Log("user.password.reset", nameof(User), user.Id, user.UserName);
        await _db.SaveChangesAsync(ct);
        await RevokeSessionsAsync(id, "password reset", ct);
    }

    public async Task UnlockAsync(Guid id, CancellationToken ct)
    {
        var user = await _db.Users.FirstOrDefaultAsync(u => u.Id == id, ct) ?? throw new NotFoundException("Пользователь", id);
        user.LockoutEnd = null;
        user.FailedLoginCount = 0;
        _audit.Log("user.unlock", nameof(User), user.Id, user.UserName);
        await _db.SaveChangesAsync(ct);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct)
    {
        if (id == _current.UserId) throw new BusinessException("SELF_DELETE", "Нельзя удалить собственную учётную запись");
        var user = await _db.Users.FirstOrDefaultAsync(u => u.Id == id, ct) ?? throw new NotFoundException("Пользователь", id);
        await EnsureNotLastSuperAdminAsync(id, Array.Empty<Guid>(), false, ct);
        user.IsActive = false;
        _db.Users.Remove(user); // soft delete
        await _db.SaveChangesAsync(ct);
        await RevokeSessionsAsync(id, "user deleted", ct);
    }

    public async Task RevokeSessionsAsync(Guid userId, string reason, CancellationToken ct)
    {
        var now = _clock.UtcNow;
        foreach (var s in await _db.UserSessions.Where(s => s.UserId == userId && s.RevokedAt == null).ToListAsync(ct))
        {
            s.RevokedAt = now;
            s.RevokeReason = reason;
        }
        await _db.SaveChangesAsync(ct);
    }

    public async Task<IReadOnlyList<SessionDto>> SessionsAsync(Guid? userId, Guid currentSession, CancellationToken ct)
    {
        var now = _clock.UtcNow;
        var q = _db.UserSessions.AsNoTracking().Where(s => s.RevokedAt == null && s.ExpiresAt > now);
        if (userId is not null) q = q.Where(s => s.UserId == userId);
        return await q.OrderByDescending(s => s.LastSeenAt).Take(1000)
            .Select(s => new SessionDto(s.Id, s.UserId, s.User!.UserName, s.CreatedAt, s.LastSeenAt, s.ExpiresAt, s.IpAddress, s.UserAgent, s.Id == currentSession))
            .ToListAsync(ct);
    }

    public async Task RevokeSessionAsync(Guid sessionId, CancellationToken ct)
    {
        var s = await _db.UserSessions.FirstOrDefaultAsync(x => x.Id == sessionId, ct) ?? throw new NotFoundException("Сессия", sessionId);
        s.RevokedAt = _clock.UtcNow;
        s.RevokeReason = "revoked by administrator";
        _audit.Log("session.revoke", nameof(User), s.UserId, null, null, new { session = sessionId });
        await _db.SaveChangesAsync(ct);
    }

    // ---------------- Roles ----------------

    public IReadOnlyList<PermissionDto> PermissionCatalogue()
        => Permissions.Catalogue.Select(p => new PermissionDto(p.Key, p.Value.Group, p.Value.Description)).ToList();

    public async Task<IReadOnlyList<RoleDto>> RolesAsync(CancellationToken ct)
    {
        var roles = await _db.Roles.AsNoTracking().Include(r => r.Permissions).OrderBy(r => r.Name).ToListAsync(ct);
        var counts = await _db.UserRoles.Where(ur => !ur.User!.IsDeleted).GroupBy(r => r.RoleId).Select(g => new { g.Key, Count = g.Count() }).ToDictionaryAsync(g => g.Key, g => g.Count, ct);
        return roles.Select(r => new RoleDto(r.Id, r.Name, r.Code, r.Description, r.IsSystem, r.Permissions.Select(p => p.PermissionCode).OrderBy(p => p).ToList(),
            counts.GetValueOrDefault(r.Id))).ToList();
    }

    public async Task<RoleDto> SaveRoleAsync(Guid? id, RoleInput input, CancellationToken ct)
    {
        var unknown = input.Permissions.Where(p => !Permissions.Catalogue.ContainsKey(p)).ToList();
        if (unknown.Count > 0) throw new ValidationFailedException("Неизвестные права: " + string.Join(", ", unknown));
        if (!IsSuper)
        {
            var notHeld = input.Permissions.Where(p => !_current.Has(p) && p != Permissions.ScopeOwnDepartment).ToList();
            if (notHeld.Count > 0) throw new ForbiddenException("Нельзя выдать права, которых нет у вас: " + string.Join(", ", notHeld));
        }
        if (await _db.Roles.AnyAsync(r => r.Code == input.Code && r.Id != id, ct)) throw new ConflictException(ErrorCodes.Duplicate, "Роль с таким кодом уже существует");
        Role role;
        List<string> old = new();
        if (id is null)
        {
            role = new Role();
            _db.Roles.Add(role);
        }
        else
        {
            role = await _db.Roles.Include(r => r.Permissions).FirstOrDefaultAsync(r => r.Id == id, ct) ?? throw new NotFoundException("Роль", id);
            if (role.Code == BuiltInRoles.SuperAdmin && !input.Permissions.Contains(Permissions.SystemAdmin))
                throw new BusinessException("SYSTEM_ROLE", "У роли суперадминистратора нельзя убрать право system.admin");
            old = role.Permissions.Select(p => p.PermissionCode).ToList();
            _db.RolePermissions.RemoveRange(role.Permissions);
        }
        role.Name = input.Name.Trim();
        if (!role.IsSystem) role.Code = input.Code;
        role.Description = input.Description;
        foreach (var p in input.Permissions.Distinct()) _db.RolePermissions.Add(new RolePermission { RoleId = role.Id, PermissionCode = p });
        _audit.Log(id is null ? "role.create" : "role.update", nameof(Role), role.Id, role.Name,
            new { added = (object)Array.Empty<string>(), removed = old.Except(input.Permissions).ToList() },
            new { added = input.Permissions.Except(old).ToList() });
        await _db.SaveChangesAsync(ct);
        return (await RolesAsync(ct)).First(r => r.Id == role.Id);
    }

    public async Task DeleteRoleAsync(Guid id, CancellationToken ct)
    {
        var role = await _db.Roles.FirstOrDefaultAsync(r => r.Id == id, ct) ?? throw new NotFoundException("Роль", id);
        if (role.IsSystem) throw new BusinessException("SYSTEM_ROLE", "Системную роль нельзя удалить");
        if (await _db.UserRoles.AnyAsync(r => r.RoleId == id, ct)) throw new ConflictException(ErrorCodes.HasDependencies, "Роль назначена пользователям");
        _db.Roles.Remove(role);
        _audit.Log("role.delete", nameof(Role), id, role.Name);
        await _db.SaveChangesAsync(ct);
    }
}
