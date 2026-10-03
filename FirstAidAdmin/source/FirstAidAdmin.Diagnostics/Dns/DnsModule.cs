using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Network;
using FirstAidAdmin.Diagnostics.Parsers;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Dns;

public sealed class DnsModule : DiagnosticModuleBase
{
    private static readonly string[] RCodes = { "NOERROR", "FORMERR", "SERVFAIL", "NXDOMAIN", "NOTIMP", "REFUSED", "RCODE" };
    private readonly INetworkProbe _net;
    private readonly IServiceProbe _services;
    private readonly IPowerShellRunner _ps;

    public DnsModule(INetworkProbe net, IServiceProbe services, IPowerShellRunner ps)
    {
        _net = net;
        _services = services;
        _ps = ps;
    }

    public override string Id => ModuleIds.Dns;
    public override string Name => "DNS";
    public override DiagnosticCategory Category => DiagnosticCategory.Dns;

    public static bool Reachable(DnsOutcome o) => o.Success || (o.Error is not null && RCodes.Any(r => o.Error.StartsWith(r, StringComparison.Ordinal)));

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var s = ctx.Settings.Diagnostics;
        var timeout = Math.Max(2000, s.PingTimeoutMs * 2);

        // DNS Client service
        var svc = _services.Get("Dnscache");
        if (svc.State == ServiceState.NotFound)
            Skipped(root, C.DnsClientService, "Служба DNS-клиента", "Служба Dnscache недоступна на этой системе");
        else
            Check(root, C.DnsClientService, "Служба DNS-клиента (Dnscache)",
                    svc.State == ServiceState.Running ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                    svc.State == ServiceState.Running ? "Служба запущена" : $"Служба в состоянии {svc.State}, тип запуска {svc.StartMode}")
                .WithEvidence("state", svc.State).WithEvidence("startMode", svc.StartMode);

        // Configured servers
        var primary = ctx.Shared.TryGetValue(NetworkModule.SharedPrimaryAdapter, out var p) ? p as NetworkAdapterInfo : null;
        primary ??= NetworkModule.PickPrimary(NetworkModule.RelevantAdapters(_net.GetAdapters()));
        var servers = primary?.DnsServers ?? new List<string>();
        var v4Servers = servers.Where(x => !x.Contains(':')).ToList();
        var domainJoined = ctx.System.IsDomainJoined && !string.IsNullOrWhiteSpace(ctx.System.DomainName);
        var publicOnDomain = domainJoined && v4Servers.Count > 0 && v4Servers.All(x => !IpClassifier.IsPrivateOrLocal(x));
        var cfg = Check(root, C.DnsServersConfigured, "Настроенные DNS-серверы",
                servers.Count == 0 ? DiagnosticStatus.Error : publicOnDomain ? DiagnosticStatus.Error : DiagnosticStatus.Ok,
                servers.Count == 0 ? "DNS-серверы не заданы"
                : publicOnDomain ? $"Доменный компьютер использует только внешние DNS: {string.Join(", ", v4Servers.Select(Describe))}"
                : $"{primary?.Name}: {string.Join(", ", servers.Select(Describe))}")
            .WithEvidence("servers", string.Join(", ", servers))
            .WithEvidence("publicOnDomain", publicOnDomain);
        if (publicOnDomain) cfg.WithRecommendation("Укажите DNS-серверы контроллеров домена в настройках адаптера.", A.OpenNetworkConnections);

        var externalNames = s.ExternalTestNames.Count > 0 ? s.ExternalTestNames : new List<string> { "www.microsoft.com" };

        // Each configured server directly (bypasses cache)
        if (v4Servers.Count > 0)
        {
            var outcomes = await Task.WhenAll(v4Servers.Select(srv => _net.QueryServerAsync(srv, externalNames[0], timeout, ct))).ConfigureAwait(false);
            var reachable = outcomes.Count(Reachable);
            var r = Check(root, C.DnsServerReachable, "Доступность DNS-серверов",
                reachable == outcomes.Length ? DiagnosticStatus.Ok : reachable == 0 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                reachable == outcomes.Length ? $"Все DNS-серверы отвечают ({string.Join(", ", outcomes.Select(o => $"{o.Server} {o.ElapsedMs} мс"))})"
                : reachable == 0 ? $"DNS-серверы не отвечают: {string.Join(", ", outcomes.Select(o => $"{o.Server} ({o.Error})"))}"
                : $"Отвечают {reachable} из {outcomes.Length}: не отвечают {string.Join(", ", outcomes.Where(o => !Reachable(o)).Select(o => o.Server))}");
            foreach (var o in outcomes) r.WithEvidence(o.Server ?? "?", o.Success ? $"{o.ElapsedMs} ms {string.Join(",", o.Addresses.Take(2))}" : o.Error);
            if (reachable < outcomes.Length) r.WithRecommendation("Проверьте адреса DNS-серверов и доступность UDP 53.", A.OpenNetworkConnections);
        }
        else
        {
            Skipped(root, C.DnsServerReachable, "Доступность DNS-серверов", "Нет IPv4 DNS-серверов");
        }

        // External names via OS resolver (several queries)
        var ext = await Task.WhenAll(externalNames.Select(n => _net.ResolveAsync(n, timeout, ct))).ConfigureAwait(false);
        var extOk = ext.Count(e => e.Success);
        var extCheck = Check(root, C.DnsResolveExternal, "Разрешение внешних имён",
            extOk == ext.Length ? DiagnosticStatus.Ok : extOk == 0 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
            extOk == ext.Length ? $"Внешние имена разрешаются ({string.Join(", ", ext.Select(e => $"{e.Name} {e.ElapsedMs} мс"))})"
            : extOk == 0 ? "Внешние имена не разрешаются"
            : $"Разрешаются {extOk} из {ext.Length}");
        foreach (var e in ext) extCheck.WithEvidence(e.Name, e.Success ? string.Join(", ", e.Addresses.Take(3)) : e.Error);
        if (extOk < ext.Length) extCheck.WithRecommendation("Очистите кэш DNS и проверьте DNS-серверы.", A.FlushDns);

        // Reference server comparison
        var refServer = s.ReferenceDnsServers.FirstOrDefault();
        if (refServer is not null)
        {
            var r = await _net.QueryServerAsync(refServer, externalNames[0], timeout, ct).ConfigureAwait(false);
            Check(root, C.DnsReference, $"Эталонный DNS ({refServer})", r.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Info,
                r.Success ? $"Эталонный DNS отвечает ({r.ElapsedMs} мс)" : $"Эталонный DNS недоступен ({r.Error}) — внешний DNS может блокироваться политикой сети");
        }

        // Suffix
        Check(root, C.DnsSuffix, "DNS-суффикс", DiagnosticStatus.Info,
            string.IsNullOrWhiteSpace(primary?.DnsSuffix) ? "DNS-суффикс подключения не задан" : $"Суффикс: {primary!.DnsSuffix}")
            .WithEvidence("domain", ctx.System.DomainName);

        // Cache
        if (ctx.System.IsWindows)
        {
            var json = await _ps.RunJsonAsync("@{count=@(Get-DnsClientCache -ErrorAction SilentlyContinue).Count} | ConvertTo-Json -Compress", TimeSpan.FromSeconds(20), ct).ConfigureAwait(false);
            var count = json is { } j && j.TryGetProperty("count", out var c) && c.TryGetInt32(out var n) ? n : -1;
            Check(root, C.DnsCache, "Кэш DNS", DiagnosticStatus.Info, count >= 0 ? $"Записей в кэше: {count}" : "Не удалось прочитать кэш DNS")
                .WithRecommendation("При устаревших записях очистите кэш DNS (ipconfig /flushdns).", A.FlushDns);
        }

        // Domain-specific checks
        if (!domainJoined)
        {
            foreach (var (id, name) in new[] { (C.DnsResolveInternal, "Разрешение внутренних имён"), (C.DnsSrvLdap, "SRV _ldap._tcp"), (C.DnsSrvKerberos, "SRV _kerberos._tcp"), (C.DnsDc, "DNS контроллера домена") })
                Skipped(root, id, name, "Компьютер не входит в домен");
            return;
        }

        var domain = ctx.System.DomainName!;
        var internalName = await _net.ResolveAsync(domain, timeout, ct).ConfigureAwait(false);
        Check(root, C.DnsResolveInternal, "Разрешение внутренних имён",
                internalName.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                internalName.Success ? $"{domain} → {string.Join(", ", internalName.Addresses.Take(4))}" : $"{domain} не разрешается ({internalName.Error})")
            .WithRecommendation(internalName.Success ? "" : "Проверьте, что используются доменные DNS-серверы.", internalName.Success ? Array.Empty<string>() : new[] { A.FlushDns, A.RegisterDns });

        var srvServer = v4Servers.FirstOrDefault();
        string? firstDc = null;
        if (srvServer is not null)
        {
            var ldap = await _net.QueryServerAsync(srvServer, $"_ldap._tcp.dc._msdcs.{domain}", timeout, ct, srv: true).ConfigureAwait(false);
            firstDc = ldap.Addresses.FirstOrDefault()?.Split(':')[0];
            Check(root, C.DnsSrvLdap, "SRV _ldap._tcp.dc._msdcs", ldap.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                ldap.Success ? $"Найдено контроллеров: {ldap.Addresses.Count} ({string.Join(", ", ldap.Addresses.Take(5))})" : $"SRV-записи не найдены на {srvServer} ({ldap.Error})");
            var krb = await _net.QueryServerAsync(srvServer, $"_kerberos._tcp.{domain}", timeout, ct, srv: true).ConfigureAwait(false);
            Check(root, C.DnsSrvKerberos, "SRV _kerberos._tcp", krb.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                krb.Success ? $"Найдено записей: {krb.Addresses.Count}" : $"SRV-записи Kerberos не найдены ({krb.Error})");
        }
        else
        {
            Skipped(root, C.DnsSrvLdap, "SRV _ldap._tcp", "Нет DNS-сервера для запроса");
            Skipped(root, C.DnsSrvKerberos, "SRV _kerberos._tcp", "Нет DNS-сервера для запроса");
        }

        var dcName = ctx.System.LogonServer is { Length: > 0 } ls && !ls.Equals(ctx.System.MachineName, StringComparison.OrdinalIgnoreCase)
            ? $"{ls}.{domain}" : firstDc;
        if (dcName is not null)
        {
            var dc = await _net.ResolveAsync(dcName, timeout, ct).ConfigureAwait(false);
            Check(root, C.DnsDc, "DNS контроллера домена", dc.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                dc.Success ? $"{dcName} → {string.Join(", ", dc.Addresses.Take(2))}" : $"{dcName} не разрешается ({dc.Error})");
        }
        else
        {
            Skipped(root, C.DnsDc, "DNS контроллера домена", "Контроллер домена не определён");
        }
    }

    private static string Describe(string ip)
        => IpClassifier.WellKnownPublicDns.TryGetValue(ip, out var n) ? $"{ip} ({n})" : ip;
}
