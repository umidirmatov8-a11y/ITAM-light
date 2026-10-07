using System.Net;
using System.Net.Http.Json;
using System.Net.Mail;
using ITAM.Application.Common;

namespace ITAM.Infrastructure.Notifications;

public sealed class EmailChannel : INotificationChannel
{
    private readonly ISettingsService _settings;
    private readonly ISecretProtector _protector;
    private NotificationSettings? _cfg;

    public EmailChannel(ISettingsService settings, ISecretProtector protector) { _settings = settings; _protector = protector; }

    public string Name => "email";
    public bool IsEnabled => (_cfg ??= _settings.GetAsync<NotificationSettings>().GetAwaiter().GetResult()) is { EmailEnabled: true, SmtpHost.Length: > 0 };

    public async Task SendAsync(string recipient, string subject, string body, CancellationToken ct = default)
    {
        var cfg = await _settings.GetAsync<NotificationSettings>(ct);
        using var client = new SmtpClient(cfg.SmtpHost, cfg.SmtpPort) { EnableSsl = cfg.SmtpUseSsl };
        if (!string.IsNullOrEmpty(cfg.SmtpUser))
            client.Credentials = new NetworkCredential(cfg.SmtpUser, _protector.Unprotect(cfg.SmtpPassword));
        using var msg = new MailMessage(cfg.SmtpFrom ?? cfg.SmtpUser ?? "itam@localhost", recipient, subject, body);
        await client.SendMailAsync(msg, ct);
    }
}

public sealed class TelegramChannel : INotificationChannel
{
    private readonly ISettingsService _settings;
    private readonly ISecretProtector _protector;
    private readonly IHttpClientFactory _http;
    private NotificationSettings? _cfg;

    public TelegramChannel(ISettingsService settings, ISecretProtector protector, IHttpClientFactory http)
    {
        _settings = settings; _protector = protector; _http = http;
    }

    public string Name => "telegram";
    public bool IsEnabled => (_cfg ??= _settings.GetAsync<NotificationSettings>().GetAwaiter().GetResult()) is { TelegramEnabled: true, TelegramBotToken.Length: > 0 };

    public async Task SendAsync(string recipient, string subject, string body, CancellationToken ct = default)
    {
        var cfg = await _settings.GetAsync<NotificationSettings>(ct);
        var token = _protector.Unprotect(cfg.TelegramBotToken);
        if (string.IsNullOrEmpty(token)) return;
        var client = _http.CreateClient("telegram");
        var resp = await client.PostAsJsonAsync($"https://api.telegram.org/bot{token}/sendMessage",
            new { chat_id = string.IsNullOrEmpty(recipient) ? cfg.TelegramChatId : recipient, text = $"{subject}\n{body}" }, ct);
        resp.EnsureSuccessStatusCode();
    }
}
