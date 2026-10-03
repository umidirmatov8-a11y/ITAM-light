using System.ComponentModel.DataAnnotations;
using ITAM.Application.Auth;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using ITAM.Domain.Security;
using Microsoft.EntityFrameworkCore;

namespace ITAM.Application.Setup;

public sealed class SetupRequest
{
    [Required, MaxLength(256)] public string OrganizationName { get; set; } = string.Empty;
    [Required, MaxLength(128), RegularExpression(@"^[A-Za-z0-9._@\-]+$")] public string AdminUserName { get; set; } = "admin";
    [Required, MaxLength(256)] public string AdminPassword { get; set; } = string.Empty;
    [MaxLength(256)] public string? AdminDisplayName { get; set; }
    [EmailAddress, MaxLength(256)] public string? AdminEmail { get; set; }
    [MaxLength(64)] public string TimeZone { get; set; } = "Asia/Tashkent";
    [MaxLength(8)] public string Language { get; set; } = "ru";
    [MaxLength(8)] public string Currency { get; set; } = "UZS";
    [MaxLength(32)] public string DateFormat { get; set; } = "DD.MM.YYYY";
    [MaxLength(64)] public string? AssetNumberFormat { get; set; }
    [MaxLength(256)] public string? PublicBaseUrl { get; set; }
    public bool LoadDemoData { get; set; }
}

public sealed record SetupStatus(bool SetupCompleted, bool DatabaseConnected, string? DatabaseVersion, string? DatabaseName, string? OrganizationName,
    string AppVersion, string? Error);

public interface IDemoDataSeeder
{
    Task SeedAsync(CancellationToken ct);
}

/// <summary>First-run wizard: organization, administrator, timezone, initial settings.</summary>
public sealed class SetupService
{
    private readonly IAppDbContext _db;
    private readonly ISettingsService _settings;
    private readonly IPasswordHasher _hasher;
    private readonly IClock _clock;
    private readonly IAuditService _audit;
    private readonly IDemoDataSeeder _demo;

    public SetupService(IAppDbContext db, ISettingsService settings, IPasswordHasher hasher, IClock clock, IAuditService audit, IDemoDataSeeder demo)
    {
        _db = db; _settings = settings; _hasher = hasher; _clock = clock; _audit = audit; _demo = demo;
    }

    public async Task<bool> IsCompletedAsync(CancellationToken ct)
        => await _db.Users.IgnoreQueryFilters().AnyAsync(ct);

    public async Task<SetupStatus> StatusAsync(CancellationToken ct)
    {
        var version = typeof(SetupService).Assembly.GetName().Version?.ToString(3) ?? "1.0.0";
        try
        {
            var connected = await _db.Database.CanConnectAsync(ct);
            if (!connected) return new SetupStatus(false, false, null, null, null, version, "Нет подключения к базе данных");
            var dbVersion = (await _db.Database.SqlQueryRaw<string>("SELECT version() AS \"Value\"").ToListAsync(ct)).FirstOrDefault();
            var general = await _settings.GetAsync<GeneralSettings>(ct);
            return new SetupStatus(await IsCompletedAsync(ct), true, dbVersion?.Split(',')[0], _db.Database.GetDbConnection().Database, general.OrganizationName, version, null);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            return new SetupStatus(false, false, null, null, null, version, ex.Message);
        }
    }

    public async Task CompleteAsync(SetupRequest req, CancellationToken ct)
    {
        if (await IsCompletedAsync(ct)) throw new ConflictException(ErrorCodes.SetupCompleted, "Первоначальная настройка уже выполнена");
        var security = await _settings.GetAsync<SecuritySettings>(ct);
        PasswordPolicy.Ensure(req.AdminPassword, security);
        TimeZones.Resolve(req.TimeZone);

        var org = await _db.Organizations.FirstOrDefaultAsync(ct);
        if (org is not null) org.Name = req.OrganizationName.Trim();
        var general = await _settings.GetAsync<GeneralSettings>(ct);
        general.OrganizationName = req.OrganizationName.Trim();
        general.TimeZone = req.TimeZone;
        general.DefaultLanguage = req.Language;
        general.Currency = req.Currency;
        general.DateFormat = req.DateFormat;
        general.PublicBaseUrl = req.PublicBaseUrl;
        general.SetupCompleted = true;
        await _settings.SaveAsync(general, ct);
        if (!string.IsNullOrWhiteSpace(req.AssetNumberFormat))
        {
            if (!Domain.Numbering.NumberFormatter.IsValidPattern(req.AssetNumberFormat)) throw new ValidationFailedException("Формат номера должен содержать {SEQ}");
            var numbering = await _settings.GetAsync<NumberingSettings>(ct);
            numbering.AssetFormat = req.AssetNumberFormat;
            await _settings.SaveAsync(numbering, ct);
        }

        var role = await _db.Roles.FirstOrDefaultAsync(r => r.Code == BuiltInRoles.SuperAdmin, ct)
                   ?? throw new BusinessException("SEED_MISSING", "Справочные данные не инициализированы");
        var admin = new User
        {
            UserName = req.AdminUserName.Trim(),
            NormalizedUserName = req.AdminUserName.Trim().ToUpperInvariant(),
            DisplayName = string.IsNullOrWhiteSpace(req.AdminDisplayName) ? "Администратор" : req.AdminDisplayName.Trim(),
            Email = req.AdminEmail,
            PasswordHash = _hasher.Hash(req.AdminPassword),
            PasswordChangedAt = _clock.UtcNow,
            AllRegions = true,
            IsActive = true,
            Language = req.Language,
        };
        _db.Users.Add(admin);
        _db.UserRoles.Add(new UserRole { UserId = admin.Id, RoleId = role.Id });
        _audit.Log("setup.complete", "Setup", admin.Id, admin.UserName, null, new { req.OrganizationName, req.TimeZone, req.LoadDemoData });
        await _db.SaveChangesAsync(ct);
        if (req.LoadDemoData) await _demo.SeedAsync(ct);
    }
}
