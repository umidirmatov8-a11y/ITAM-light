using ITAM.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;

namespace ITAM.Application.Common;

public sealed class GeneralSettings
{
    public string OrganizationName { get; set; } = "Организация";
    public Guid? LogoFileId { get; set; }
    public string TimeZone { get; set; } = "Asia/Tashkent";
    public string DateFormat { get; set; } = "DD.MM.YYYY";
    public string Currency { get; set; } = "UZS";
    public string DefaultLanguage { get; set; } = "ru";
    /// <summary>Public base URL used in QR codes, e.g. http://192.168.1.10:8080.</summary>
    public string? PublicBaseUrl { get; set; }
    public bool SetupCompleted { get; set; }
}

public sealed class NumberingSettings
{
    public string AssetFormat { get; set; } = "{PREFIX}-{SEQ:6}";
    public string IssueFormat { get; set; } = "ISS-{SEQ:6}";
    public string ReturnFormat { get; set; } = "RET-{SEQ:6}";
    public string TransferFormat { get; set; } = "TRF-{SEQ:6}";
    public string StatusChangeFormat { get; set; } = "STC-{SEQ:6}";
    public string RepairFormat { get; set; } = "REP-{SEQ:6}";
    public string DocumentFormat { get; set; } = "DOC-{YYYY}-{SEQ:6}";
    public string InventoryFormat { get; set; } = "INV-{YYYY}-{SEQ:4}";
    public string EmployeeNumberFormat { get; set; } = "EMP-{SEQ:5}";
}

public sealed class DocumentSettings
{
    public bool GeneratePdf { get; set; } = true;
    /// <summary>auto | libreoffice | builtin</summary>
    public string PdfEngine { get; set; } = "auto";
    public string? LibreOfficePath { get; set; }
    public bool RequireSignatures { get; set; } = true;
}

public sealed class NotificationSettings
{
    public int LicenseExpiryDays { get; set; } = 30;
    public int WarrantyExpiryDays { get; set; } = 14;
    public int ContractExpiryDays { get; set; } = 30;
    public int RepairOverdueDays { get; set; } = 0;
    public bool NotifyUnreturnedEquipment { get; set; } = true;
    public bool NotifyNoResponsible { get; set; } = true;
    public bool EmailEnabled { get; set; }
    public string? SmtpHost { get; set; }
    public int SmtpPort { get; set; } = 587;
    public bool SmtpUseSsl { get; set; } = true;
    public string? SmtpUser { get; set; }
    /// <summary>Stored encrypted; returned masked.</summary>
    public string? SmtpPassword { get; set; }
    public string? SmtpFrom { get; set; }
    public string? EmailRecipients { get; set; }
    public bool TelegramEnabled { get; set; }
    public string? TelegramBotToken { get; set; }
    public string? TelegramChatId { get; set; }
}

public sealed class BackupSettings
{
    public bool AutoEnabled { get; set; } = true;
    /// <summary>Daily | Weekly</summary>
    public string Schedule { get; set; } = "Daily";
    public string TimeOfDay { get; set; } = "02:00";
    public DayOfWeek DayOfWeek { get; set; } = DayOfWeek.Sunday;
    /// <summary>Null = {DataRoot}/backups.</summary>
    public string? Location { get; set; }
    public int RetentionDays { get; set; } = 30;
    public int MaxBackups { get; set; } = 30;
    public bool IncludeFiles { get; set; } = true;
}

public sealed class SecuritySettings
{
    public int PasswordMinLength { get; set; } = 10;
    public bool RequireUppercase { get; set; } = true;
    public bool RequireLowercase { get; set; } = true;
    public bool RequireDigit { get; set; } = true;
    public bool RequireSpecial { get; set; }
    public int LockoutThreshold { get; set; } = 5;
    public int LockoutMinutes { get; set; } = 15;
    public int SessionIdleMinutes { get; set; } = 60;
    public int SessionAbsoluteHours { get; set; } = 12;
    /// <summary>Operations older than this are "backdated" and require assets.backdate.</summary>
    public int BackdateToleranceHours { get; set; } = 24;
    public int PasswordMaxAgeDays { get; set; }
}

public sealed class QrSettings
{
    public bool PublicViewEnabled { get; set; } = true;
    public bool ShowStatus { get; set; } = true;
    public bool ShowModel { get; set; } = true;
    public bool ShowLocation { get; set; }
}

public interface ISettingsService
{
    Task<T> GetAsync<T>(CancellationToken ct = default) where T : class, new();
    Task SaveAsync<T>(T value, CancellationToken ct = default) where T : class, new();
    void Invalidate();
}

public sealed class SettingsService : ISettingsService
{
    public static readonly Dictionary<Type, string> Keys = new()
    {
        [typeof(GeneralSettings)] = "general",
        [typeof(NumberingSettings)] = "numbering",
        [typeof(DocumentSettings)] = "documents",
        [typeof(NotificationSettings)] = "notifications",
        [typeof(BackupSettings)] = "backup",
        [typeof(SecuritySettings)] = "security",
        [typeof(QrSettings)] = "qr",
        [typeof(Agents.AgentSettings)] = "agent",
    };

    private readonly IAppDbContext _db;
    private readonly IMemoryCache _cache;
    private readonly ITenantContext _tenant;
    private readonly IClock _clock;
    private readonly ICurrentUser _user;

    public SettingsService(IAppDbContext db, IMemoryCache cache, ITenantContext tenant, IClock clock, ICurrentUser user)
    {
        _db = db; _cache = cache; _tenant = tenant; _clock = clock; _user = user;
    }

    private string CacheKey(string key) => $"settings:{_tenant.OrganizationId}:{key}";

    public async Task<T> GetAsync<T>(CancellationToken ct = default) where T : class, new()
    {
        var key = Keys[typeof(T)];
        if (_cache.TryGetValue(CacheKey(key), out T? cached) && cached is not null) return cached;
        var row = await _db.Settings.AsNoTracking().FirstOrDefaultAsync(s => s.OrganizationId == _tenant.OrganizationId && s.Key == key, ct);
        var value = Json.Deserialize<T>(row?.Value) ?? new T();
        _cache.Set(CacheKey(key), value, TimeSpan.FromMinutes(5));
        return value;
    }

    public async Task SaveAsync<T>(T value, CancellationToken ct = default) where T : class, new()
    {
        var key = Keys[typeof(T)];
        var row = await _db.Settings.FirstOrDefaultAsync(s => s.OrganizationId == _tenant.OrganizationId && s.Key == key, ct);
        if (row is null)
        {
            row = new Setting { OrganizationId = _tenant.OrganizationId, Key = key };
            _db.Settings.Add(row);
        }
        row.Value = Json.Serialize(value);
        row.UpdatedAt = _clock.UtcNow;
        row.UpdatedById = _user.UserId;
        await _db.SaveChangesAsync(ct);
        _cache.Remove(CacheKey(key));
    }

    public void Invalidate()
    {
        foreach (var key in Keys.Values) _cache.Remove(CacheKey(key));
    }
}
