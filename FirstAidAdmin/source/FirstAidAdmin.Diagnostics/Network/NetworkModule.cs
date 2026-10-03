using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Parsers;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Network;

/// <summary>
/// Network diagnostics: adapters → IP → DHCP → gateway → Internet by IP → DNS → HTTP → proxy → routes → TCP/UDP.
/// </summary>
public sealed class NetworkModule : DiagnosticModuleBase
{
    public const string SharedPrimaryAdapter = "network.primaryAdapter";
    private readonly INetworkProbe _net;
    private readonly ICommandRunner _cmd;

    public NetworkModule(INetworkProbe net, ICommandRunner cmd)
    {
        _net = net;
        _cmd = cmd;
    }

    public override string Id => ModuleIds.Network;
    public override string Name => "Сеть";
    public override DiagnosticCategory Category => DiagnosticCategory.Network;

    public static IReadOnlyList<NetworkAdapterInfo> RelevantAdapters(IEnumerable<NetworkAdapterInfo> all)
    {
        var up = all.Where(a => a.IsUp && !a.IsLoopback).ToList();
        var physical = up.Where(a => !a.IsVirtual).ToList();
        // VPN / virtual adapters count only when they carry a default gateway.
        return physical.Count > 0 ? physical : up.Where(a => a.Gateways.Count > 0).ToList();
    }

    public static NetworkAdapterInfo? PickPrimary(IReadOnlyList<NetworkAdapterInfo> relevant)
        => relevant.FirstOrDefault(a => a.Gateways.Any(g => !g.Contains(':')) && a.IPv4.Any(ip => !IpClassifier.IsApipa(ip.Address)))
           ?? relevant.FirstOrDefault(a => a.Gateways.Count > 0)
           ?? relevant.FirstOrDefault(a => a.IPv4.Count > 0)
           ?? relevant.FirstOrDefault();

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var s = ctx.Settings.Diagnostics;
        var all = _net.GetAdapters();
        var relevant = RelevantAdapters(all);

        // 1. Adapters
        var adapters = Check(root, C.NetAdapters, "Сетевые адаптеры",
            relevant.Count > 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            relevant.Count > 0
                ? $"Активных адаптеров: {relevant.Count} ({string.Join(", ", relevant.Select(a => $"{a.Name}{(a.SpeedBitsPerSecond > 0 ? $" {a.SpeedBitsPerSecond / 1_000_000} Мбит/с" : "")}"))})"
                : "Нет активных сетевых адаптеров (кабель отключён / Wi-Fi выключен / адаптер отключён)",
            relevant.Count > 0 ? null : Severity.Critical);
        foreach (var a in all.Where(a => !a.IsLoopback))
            adapters.WithEvidence(a.Name, $"{(a.IsUp ? "Up" : "Down")}; {a.Type}; {a.Description}; MAC {a.MacAddress}{(a.IsVirtual ? "; virtual" : "")}");
        if (relevant.Count == 0)
        {
            adapters.WithRecommendation("Проверьте кабель, включите Wi-Fi или адаптер в «Сетевых подключениях».", A.OpenNetworkConnections);
            foreach (var (id, name) in new[] { (C.NetIPv4, "IPv4"), (C.NetGatewayConfigured, "Шлюз по умолчанию"), (C.NetInternetIp, "Интернет по IP"), (C.NetDnsResolve, "Разрешение имён") })
                Skipped(root, id, name, "Нет активного адаптера");
            root.Summary = BuildSummary(root);
            return;
        }

        var primary = PickPrimary(relevant)!;
        ctx.Shared[SharedPrimaryAdapter] = primary;

        // 2. IPv4
        var validV4 = primary.IPv4.Where(ip => !IpClassifier.IsApipa(ip.Address)).ToList();
        var apipa = primary.IPv4.Any(ip => IpClassifier.IsApipa(ip.Address)) && validV4.Count == 0;
        var ipv4 = Check(root, C.NetIPv4, "IPv4-адрес",
            validV4.Count > 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            validV4.Count > 0
                ? $"{primary.Name}: {string.Join(", ", validV4.Select(i => $"{i.Address}/{i.PrefixLength}"))}"
                : apipa ? $"{primary.Name}: получен адрес APIPA {primary.IPv4.First().Address} — DHCP не ответил"
                        : $"{primary.Name}: IPv4-адрес отсутствует")
            .WithEvidence("adapter", primary.Name)
            .WithEvidence("apipa", apipa);
        if (validV4.Count == 0) ipv4.WithRecommendation("Обновите IP-адрес (ipconfig /renew) и проверьте DHCP-сервер.", A.RenewIp);

        // 3. IPv6
        var v6 = primary.IPv6.Where(i => !i.Address.StartsWith("fe80", StringComparison.OrdinalIgnoreCase)).ToList();
        Check(root, C.NetIPv6, "IPv6", DiagnosticStatus.Info,
            v6.Count > 0 ? $"Глобальные IPv6: {string.Join(", ", v6.Select(i => i.Address))}"
                         : primary.IPv6.Count > 0 ? "Только link-local IPv6 (fe80::)" : "IPv6 не используется");

        // 4. DHCP
        var dhcp = Check(root, C.NetDhcp, "DHCP",
            primary.DhcpEnabled == true && apipa ? DiagnosticStatus.Warning : DiagnosticStatus.Info,
            primary.DhcpEnabled switch
            {
                true => primary.DhcpServers.Count > 0 ? $"DHCP включён, сервер {string.Join(", ", primary.DhcpServers)}" : "DHCP включён, сервер DHCP не получен",
                false => "Статическая настройка IP",
                _ => "Режим DHCP неизвестен"
            });
        dhcp.WithEvidence("enabled", primary.DhcpEnabled);

        // 5. Gateway configured
        var gw = primary.Gateways.FirstOrDefault(g => !g.Contains(':')) ?? primary.Gateways.FirstOrDefault();
        Check(root, C.NetGatewayConfigured, "Шлюз по умолчанию",
                gw is not null ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                gw is not null ? $"Шлюз: {gw}" : "Шлюз по умолчанию не задан")
            .WithEvidence("gateway", gw);

        // Run reachability probes in parallel.
        var timeout = s.PingTimeoutMs;
        var gwPings = gw is null ? Task.FromResult(Array.Empty<PingOutcome>())
            : Task.WhenAll(Enumerable.Range(0, Math.Max(1, s.PingCount)).Select(_ => _net.PingAsync(gw, timeout, ct)));
        var inetPings = Task.WhenAll(s.InternetProbeIps.Select(ip => _net.PingAsync(ip, timeout, ct)));
        var inetTcp = Task.WhenAll(
            _net.TcpConnectAsync(s.InternetProbeIps.LastOrDefault() ?? "1.1.1.1", 443, s.TcpTimeoutMs, ct),
            _net.TcpConnectAsync(s.InternetProbeIps.FirstOrDefault() ?? "8.8.8.8", 53, s.TcpTimeoutMs, ct));
        var dnsName = s.ExternalTestNames.FirstOrDefault() ?? "www.microsoft.com";
        var dnsTask = _net.ResolveAsync(dnsName, Math.Max(3000, timeout * 2), ct);
        var httpTask = _net.HttpGetAsync(s.HttpProbeUrl, 7000, ct);
        var arpTask = gw is null ? Task.FromResult<CommandResult?>(null) : RunOptional("arp", "-a", ctx, ct);
        var routeTask = RunOptional("route", "print -4", ctx, ct);

        await Task.WhenAll(gwPings, inetPings, inetTcp, dnsTask, httpTask, arpTask, routeTask).ConfigureAwait(false);

        // 6. Gateway ping
        var internetReachable = inetPings.Result.Any(p => p.Success) || inetTcp.Result.Any(t => t.Success);
        if (gw is not null)
        {
            var pings = gwPings.Result;
            var okCount = pings.Count(p => p.Success);
            var avg = okCount > 0 ? pings.Where(p => p.Success).Average(p => p.RoundTripMs) : -1;
            // A gateway that ignores ICMP while the Internet works is not a failure.
            var st = okCount == 0 ? (internetReachable ? DiagnosticStatus.Warning : DiagnosticStatus.Error)
                : okCount < pings.Length ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
            Check(root, C.NetGatewayPing, "Доступность шлюза (ping)", st,
                    okCount == 0 ? (internetReachable ? $"Шлюз {gw} не отвечает на ping, но Интернет доступен (ICMP блокируется)" : $"Шлюз {gw} не отвечает ({pings.FirstOrDefault()?.Status})")
                                 : $"Шлюз {gw} отвечает: {okCount}/{pings.Length}, среднее {avg:F0} мс")
                .WithEvidence("gateway", gw).WithEvidence("received", okCount).WithEvidence("sent", pings.Length).WithEvidence("avgMs", avg);

            // 7. ARP
            var arpText = arpTask.Result;
            if (arpText is { Started: true })
            {
                var table = ArpParser.Parse(arpText.StdOut);
                var found = table.TryGetValue(gw, out var mac);
                Check(root, C.NetGatewayArp, "ARP-запись шлюза", found ? DiagnosticStatus.Ok : DiagnosticStatus.Info,
                        found ? $"MAC шлюза: {mac}" : "ARP-запись шлюза отсутствует")
                    .WithEvidence("entries", table.Count);
            }
        }
        else
        {
            Skipped(root, C.NetGatewayPing, "Доступность шлюза (ping)", "Шлюз не задан");
        }

        // 8. Internet by IP
        var ip = inetPings.Result;
        var tcp = inetTcp.Result;
        var pingOk = ip.Any(p => p.Success);
        var tcpOk = tcp.Any(t => t.Success);
        var inet = Check(root, C.NetInternetIp, "Интернет по IP",
            pingOk ? DiagnosticStatus.Ok : tcpOk ? DiagnosticStatus.Warning : DiagnosticStatus.Error,
            pingOk ? $"Внешние адреса отвечают: {string.Join(", ", ip.Where(p => p.Success).Select(p => $"{p.Host} {p.RoundTripMs} мс"))}"
                   : tcpOk ? "ICMP блокируется, но TCP-подключения к внешним адресам работают"
                           : $"Внешние IP недоступны ({string.Join(", ", s.InternetProbeIps)}): ни ping, ни TCP");
        foreach (var p in ip) inet.WithEvidence("ping " + p.Host, p.Success ? $"{p.RoundTripMs} ms" : p.Status);
        foreach (var t in tcp) inet.WithEvidence($"tcp {t.Host}:{t.Port}", t.Success ? $"{t.ElapsedMs} ms" : t.Error);

        // 9. DNS via OS resolver
        var dns = dnsTask.Result;
        Check(root, C.NetDnsResolve, "Разрешение имён (системный DNS)",
                dns.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                dns.Success ? $"{dnsName} → {string.Join(", ", dns.Addresses.Take(3))} ({dns.ElapsedMs} мс)" : $"{dnsName}: не разрешается ({dns.Error})")
            .WithEvidence("name", dnsName).WithEvidence("dnsServers", string.Join(", ", primary.DnsServers))
            .WithRecommendation(dns.Success ? "" : "Проверьте DNS-серверы адаптера и очистите кэш DNS.", dns.Success ? Array.Empty<string>() : new[] { A.FlushDns });

        // 10. HTTP
        var http = httpTask.Result;
        var expectedOk = http.Success && (http.BodyStart ?? "").Contains(s.HttpProbeExpected, StringComparison.OrdinalIgnoreCase);
        var httpStatus = expectedOk ? DiagnosticStatus.Ok
            : http.StatusCode is >= 300 and < 400 ? DiagnosticStatus.Warning
            : http.Success ? DiagnosticStatus.Warning
            : DiagnosticStatus.Error;
        Check(root, C.NetHttp, "HTTP-проверка подключения", httpStatus,
                expectedOk ? $"Ответ получен за {http.ElapsedMs} мс"
                : http.StatusCode is >= 300 and < 400 ? $"Перенаправление HTTP {http.StatusCode}: возможно, требуется вход на портал (captive portal)"
                : http.Success ? "Получен неожиданный ответ (прокси/фильтр подменяет содержимое)"
                : $"Нет ответа: {http.Error}")
            .WithEvidence("url", s.HttpProbeUrl).WithEvidence("status", http.StatusCode);

        // 11. Proxy
        var proxy = _net.GetProxyInfo(s.HttpProbeUrl);
        var proxyConfigured = proxy.Enabled || !string.IsNullOrEmpty(proxy.AutoConfigUrl);
        Check(root, C.NetProxy, "Прокси-сервер", DiagnosticStatus.Info,
                proxyConfigured
                    ? $"Прокси включён: {proxy.Server ?? "-"}{(string.IsNullOrEmpty(proxy.AutoConfigUrl) ? "" : $"; PAC: {proxy.AutoConfigUrl}")}"
                    : "Прокси не используется")
            .WithEvidence("enabled", proxyConfigured)
            .WithEvidence("server", proxy.Server)
            .WithEvidence("pac", proxy.AutoConfigUrl)
            .WithEvidence("effectiveForProbe", proxy.EffectiveProxyForProbe);

        // 12. Routes
        var routeText = routeTask.Result;
        if (routeText is { Started: true, ExitCode: 0 })
        {
            var defaults = RouteParser.DefaultRoutes(routeText.StdOut);
            var gateways = defaults.Select(d => d.Gateway).Distinct().ToList();
            var routes = Check(root, C.NetRoutes, "Маршрутизация",
                defaults.Count == 0 ? DiagnosticStatus.Error : gateways.Count > 1 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                defaults.Count == 0 ? "Маршрут по умолчанию (0.0.0.0/0) отсутствует"
                : gateways.Count > 1 ? $"Несколько маршрутов по умолчанию: {string.Join(", ", defaults.Select(d => $"{d.Gateway} (метрика {d.Metric})"))} — возможен конфликт VPN/адаптеров"
                : $"Маршрут по умолчанию через {defaults[0].Gateway} (метрика {defaults[0].Metric})");
            foreach (var d in defaults) routes.WithEvidence("default", $"{d.Gateway} via {d.Interface} metric {d.Metric}");
        }
        else
        {
            Skipped(root, C.NetRoutes, "Маршрутизация", "Таблица маршрутов недоступна");
        }

        // 13. TCP / UDP
        var stats = _net.GetTcpStatistics();
        var retrans = stats.SegmentsSent > 0 ? 100.0 * stats.SegmentsResent / stats.SegmentsSent : 0;
        Check(root, C.NetTcp, "TCP", retrans > 5 && stats.SegmentsSent > 10_000 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                $"Соединений: {stats.ActiveConnections}, прослушиваемых портов: {stats.ListeningPorts}, повторных передач: {retrans:F1}%")
            .WithEvidence("retransmitPercent", retrans.ToString("F2", System.Globalization.CultureInfo.InvariantCulture))
            .WithEvidence("failedConnectionAttempts", stats.FailedConnectionAttempts)
            .WithEvidence("resets", stats.ResetConnections);
        Check(root, C.NetUdp, "UDP", DiagnosticStatus.Info,
            $"UDP-слушателей: {stats.UdpListeners}, датаграмм с ошибками: {stats.UdpIncomingErrors}");

        root.Summary = BuildSummary(root);
    }

    private async Task<CommandResult?> RunOptional(string exe, string args, DiagnosticContext ctx, CancellationToken ct)
    {
        if (!ctx.System.IsWindows) return null;
        return await _cmd.RunAsync(exe, args, TimeSpan.FromSeconds(15), ct).ConfigureAwait(false);
    }

    private static string BuildSummary(DiagnosticResult root)
    {
        // Stage of failure, in the order the admin thinks about it.
        var order = new[] { C.NetAdapters, C.NetIPv4, C.NetGatewayConfigured, C.NetGatewayPing, C.NetInternetIp, C.NetDnsResolve, C.NetHttp };
        foreach (var id in order)
        {
            var c = root.Checks.FirstOrDefault(x => x.Id == id);
            if (c is { IsProblem: true }) return $"Этап отказа: {c.Name} — {c.Summary}";
        }
        return DefaultSummary(root);
    }
}
