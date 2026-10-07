using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Numbering;

namespace ITAM.Application.Admin;

public sealed record AllSettingsDto(GeneralSettings General, NumberingSettings Numbering, DocumentSettings Documents,
    NotificationSettings Notifications, BackupSettings Backup, SecuritySettings Security, QrSettings Qr);

/// <summary>Settings administration. Secrets are encrypted at rest and returned masked.</summary>
public sealed class SettingsAdminService
{
    public const string Mask = "********";
    private readonly ISettingsService _settings;
    private readonly ISecretProtector _protector;
    private readonly IAuditService _audit;
    private readonly IAppDbContext _db;
    private readonly IEnumerable<INotificationChannel> _channels;

    public SettingsAdminService(ISettingsService settings, ISecretProtector protector, IAuditService audit, IAppDbContext db, IEnumerable<INotificationChannel> channels)
    {
        _settings = settings; _protector = protector; _audit = audit; _db = db; _channels = channels;
    }

    public async Task<AllSettingsDto> GetAsync(CancellationToken ct)
    {
        var n = Clone(await _settings.GetAsync<NotificationSettings>(ct));
        n.SmtpPassword = string.IsNullOrEmpty(n.SmtpPassword) ? null : Mask;
        n.TelegramBotToken = string.IsNullOrEmpty(n.TelegramBotToken) ? null : Mask;
        return new AllSettingsDto(await _settings.GetAsync<GeneralSettings>(ct), await _settings.GetAsync<NumberingSettings>(ct),
            await _settings.GetAsync<DocumentSettings>(ct), n, await _settings.GetAsync<BackupSettings>(ct),
            await _settings.GetAsync<SecuritySettings>(ct), await _settings.GetAsync<QrSettings>(ct));
    }

    private static T Clone<T>(T v) => JsonSerializer.Deserialize<T>(JsonSerializer.Serialize(v, Json.Options), Json.Options)!;

    public async Task SaveAsync(string group, JsonElement body, CancellationToken ct)
    {
        switch (group.ToLowerInvariant())
        {
            case "general":
            {
                var v = body.Deserialize<GeneralSettings>(Json.Options) ?? throw new ValidationFailedException("Пустые настройки");
                var old = await _settings.GetAsync<GeneralSettings>(ct);
                v.SetupCompleted = old.SetupCompleted;
                TimeZones.Resolve(v.TimeZone);
                await SaveWithAudit(old, v, ct);
                break;
            }
            case "numbering":
            {
                var v = body.Deserialize<NumberingSettings>(Json.Options) ?? throw new ValidationFailedException("Пустые настройки");
                foreach (var (name, pattern) in new[] { ("assetFormat", v.AssetFormat), ("issueFormat", v.IssueFormat), ("returnFormat", v.ReturnFormat),
                             ("transferFormat", v.TransferFormat), ("repairFormat", v.RepairFormat), ("documentFormat", v.DocumentFormat),
                             ("statusChangeFormat", v.StatusChangeFormat), ("inventoryFormat", v.InventoryFormat), ("employeeNumberFormat", v.EmployeeNumberFormat) })
                    if (!NumberFormatter.IsValidPattern(pattern))
                        throw new ValidationFailedException($"Формат {name} должен содержать {{SEQ}} или {{SEQ:n}}");
                await SaveWithAudit(await _settings.GetAsync<NumberingSettings>(ct), v, ct);
                break;
            }
            case "documents":
                await SaveWithAudit(await _settings.GetAsync<DocumentSettings>(ct), body.Deserialize<DocumentSettings>(Json.Options)!, ct);
                break;
            case "notifications":
            {
                var v = body.Deserialize<NotificationSettings>(Json.Options)!;
                var old = await _settings.GetAsync<NotificationSettings>(ct);
                v.SmtpPassword = v.SmtpPassword == Mask ? old.SmtpPassword : string.IsNullOrEmpty(v.SmtpPassword) ? null : _protector.Protect(v.SmtpPassword);
                v.TelegramBotToken = v.TelegramBotToken == Mask ? old.TelegramBotToken : string.IsNullOrEmpty(v.TelegramBotToken) ? null : _protector.Protect(v.TelegramBotToken);
                await SaveWithAudit(old, v, ct);
                break;
            }
            case "backup":
            {
                var v = body.Deserialize<BackupSettings>(Json.Options)!;
                if (v.Schedule is not ("Daily" or "Weekly")) throw new ValidationFailedException("Расписание: Daily или Weekly");
                if (!TimeOnly.TryParse(v.TimeOfDay, out _)) throw new ValidationFailedException("Время в формате ЧЧ:ММ");
                if (v.RetentionDays < 1 || v.MaxBackups < 1) throw new ValidationFailedException("Срок хранения и количество копий должны быть больше 0");
                await SaveWithAudit(await _settings.GetAsync<BackupSettings>(ct), v, ct);
                break;
            }
            case "security":
            {
                var v = body.Deserialize<SecuritySettings>(Json.Options)!;
                if (v.PasswordMinLength < 8) throw new ValidationFailedException("Минимальная длина пароля не может быть меньше 8");
                if (v.SessionIdleMinutes < 5 || v.SessionAbsoluteHours < 1) throw new ValidationFailedException("Слишком короткий тайм-аут сессии");
                await SaveWithAudit(await _settings.GetAsync<SecuritySettings>(ct), v, ct);
                break;
            }
            case "qr":
                await SaveWithAudit(await _settings.GetAsync<QrSettings>(ct), body.Deserialize<QrSettings>(Json.Options)!, ct);
                break;
            default:
                throw new NotFoundException("Группа настроек", group);
        }
    }

    private async Task SaveWithAudit<T>(T old, T value, CancellationToken ct) where T : class, new()
    {
        var oldJson = Json.Serialize(old);
        var newJson = Json.Serialize(value);
        if (oldJson == newJson) return;
        var key = SettingsService.Keys[typeof(T)];
        _audit.Log("settings.update", "Settings", null, key, MaskSecrets(oldJson), MaskSecrets(newJson));
        await _settings.SaveAsync(value, ct);
    }

    private static JsonElement? MaskSecrets(string json)
    {
        var dict = Json.ToDictionary(json);
        if (dict is null) return null;
        var result = dict.ToDictionary(k => k.Key, k => k.Key.Contains("password", StringComparison.OrdinalIgnoreCase) || k.Key.Contains("token", StringComparison.OrdinalIgnoreCase)
            ? (object?)(k.Value.ValueKind == JsonValueKind.Null ? null : Mask) : k.Value);
        return Json.ToElement(Json.Serialize(result));
    }

    public async Task<string> TestChannelAsync(string channel, string recipient, CancellationToken ct)
    {
        var c = _channels.FirstOrDefault(x => x.Name == channel) ?? throw new NotFoundException("Канал", channel);
        await c.SendAsync(recipient, "ITAM: тестовое сообщение", "Канал уведомлений настроен корректно.", ct);
        return "ok";
    }
}
