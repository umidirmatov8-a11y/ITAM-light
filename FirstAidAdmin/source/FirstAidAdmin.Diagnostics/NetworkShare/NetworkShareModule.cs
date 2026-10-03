using System.Net;
using System.Text.RegularExpressions;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.NetworkShare;

/// <summary>"Не работает сетевой ресурс": UNC parse → name → ping → SMB 445 → folder access.</summary>
public sealed class NetworkShareModule : DiagnosticModuleBase
{
    private readonly INetworkProbe _net;
    private readonly IFileSystemProbe _fs;
    private readonly IServiceProbe _services;

    public NetworkShareModule(INetworkProbe net, IFileSystemProbe fs, IServiceProbe services)
    {
        _net = net;
        _fs = fs;
        _services = services;
    }

    public override string Id => ModuleIds.NetworkShare;
    public override string Name => "Сетевой ресурс";
    public override DiagnosticCategory Category => DiagnosticCategory.NetworkShare;
    public override IReadOnlyList<string> InputKeys => new[] { Core.Abstractions.InputKeys.SharePath };

    public static (string Host, string? Share)? ParseUnc(string path)
    {
        var m = Regex.Match(path.Trim(), @"^(?:\\\\|//)([^\\/]+)(?:[\\/]([^\\/]+))?");
        return m.Success ? (m.Groups[1].Value, m.Groups[2].Success ? m.Groups[2].Value : null) : null;
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var path = ctx.Input(Core.Abstractions.InputKeys.SharePath);
        var parsed = path is null ? null : ParseUnc(path);
        if (parsed is null)
        {
            Check(root, C.SharePath, "Путь к ресурсу", DiagnosticStatus.Error, path is null ? "Путь не указан (например \\\\server\\share)" : $"Некорректный UNC-путь: {path}");
            return;
        }
        var (host, share) = parsed.Value;
        Check(root, C.SharePath, "Путь к ресурсу", DiagnosticStatus.Ok, $"Сервер: {host}, ресурс: {share ?? "(корень)"}");

        var ws = _services.Get("LanmanWorkstation");
        if (ws.State != ServiceState.NotFound)
            Check(root, C.ShareWorkstation, "Служба «Рабочая станция»", ws.State == ServiceState.Running ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                    ws.State == ServiceState.Running ? "LanmanWorkstation запущена" : $"LanmanWorkstation: {ws.State} — SMB-клиент не работает")
                .WithRecommendation(ws.State == ServiceState.Running ? "" : "Запустите службу «Рабочая станция».", ws.State == ServiceState.Running ? Array.Empty<string>() : new[] { A.StartService });

        var timeout = ctx.Settings.Diagnostics.PingTimeoutMs;
        var address = host;
        if (!IPAddress.TryParse(host, out _))
        {
            var dns = await _net.ResolveAsync(host, Math.Max(3000, timeout * 2), ct).ConfigureAwait(false);
            Check(root, C.ShareDns, $"Разрешение имени {host}", dns.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                dns.Success ? $"{host} → {string.Join(", ", dns.Addresses.Take(3))}" : $"{host} не разрешается ({dns.Error})");
            if (!dns.Success) return;
            address = dns.Addresses.FirstOrDefault(a => !a.Contains(':')) ?? dns.Addresses[0];
        }

        var ping = await _net.PingAsync(address, timeout, ct).ConfigureAwait(false);
        Check(root, C.SharePing, $"Ping {host}", ping.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
            ping.Success ? $"Отвечает ({ping.RoundTripMs} мс)" : $"Не отвечает на ping ({ping.Status}); ICMP может блокироваться");

        var smb = await _net.TcpConnectAsync(address, 445, Math.Max(3000, ctx.Settings.Diagnostics.TcpTimeoutMs), ct).ConfigureAwait(false);
        Check(root, C.ShareSmb, "SMB (TCP 445)", smb.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            smb.Success ? $"Порт 445 открыт ({smb.ElapsedMs} мс)" : $"Порт 445 недоступен ({smb.Error})");
        if (!smb.Success || !ctx.System.IsWindows) return;

        var ok = await _fs.DirectoryExistsWithTimeoutAsync(path!, 10_000, ct).ConfigureAwait(false);
        Check(root, C.ShareAccess, "Доступ к папке", ok ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            ok ? $"{path} открывается" : $"{path} не открывается: нет прав, неверное имя ресурса или требуются другие учётные данные");
    }
}
