using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Parsers;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Domain;

/// <summary>Domain health: membership, DC discovery, logon server, secure channel, DC ports, time, GPO, Kerberos.</summary>
public sealed class DomainModule : DiagnosticModuleBase
{
    public const string SharedDcName = "domain.dc";
    private readonly ICommandRunner _cmd;
    private readonly INetworkProbe _net;
    private readonly IEventLogProbe _events;

    public DomainModule(ICommandRunner cmd, INetworkProbe net, IEventLogProbe events)
    {
        _cmd = cmd;
        _net = net;
        _events = events;
    }

    public override string Id => ModuleIds.Domain;
    public override string Name => "Домен";
    public override DiagnosticCategory Category => DiagnosticCategory.Domain;

    public static DiagnosticStatus TimeStatus(double offsetSeconds, int warn, int crit)
    {
        var abs = Math.Abs(offsetSeconds);
        return abs >= crit ? DiagnosticStatus.Error : abs >= warn ? DiagnosticStatus.Warning : DiagnosticStatus.Ok;
    }

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var sys = ctx.System;
        if (!sys.IsDomainJoined || string.IsNullOrWhiteSpace(sys.DomainName))
        {
            Check(root, C.DomainMembership, "Членство в домене", DiagnosticStatus.Info, "Компьютер не входит в домен (рабочая группа)");
            root.Summary = "Компьютер не входит в домен — доменные проверки не требуются";
            return;
        }
        var domain = sys.DomainName!;
        Check(root, C.DomainMembership, "Членство в домене", DiagnosticStatus.Ok, $"Домен: {domain}")
            .WithEvidence("domain", domain).WithEvidence("user", sys.QualifiedUser);

        // DC discovery
        var dsget = await _cmd.RunAsync("nltest", $"/dsgetdc:{domain}", ctx.CommandTimeout, ct).ConfigureAwait(false);
        var dc = NltestParser.ParseDsGetDc(dsget.StdOut);
        var dcHost = dc.DcName;
        if (dsget.Success && !string.IsNullOrEmpty(dcHost))
        {
            ctx.Shared[SharedDcName] = dcHost;
            Check(root, C.DomainDcDiscovery, "Контроллер домена", DiagnosticStatus.Ok, $"{dcHost} ({dc.Address}), сайт {dc.SiteName}")
                .WithEvidence("dc", dcHost).WithEvidence("address", dc.Address).WithEvidence("site", dc.SiteName).WithEvidence("forest", dc.Forest);
        }
        else
        {
            Check(root, C.DomainDcDiscovery, "Контроллер домена", dsget.Started ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                    dsget.Started ? $"Контроллер домена не найден: {FirstLine(dsget.StdOut + dsget.StdErr)}" : "nltest недоступен")
                .WithRecommendation("Проверьте DNS (SRV-записи домена) и сетевой доступ к контроллеру.", A.FlushDns, A.RegisterDns);
        }

        // Logon server
        var logon = sys.LogonServer;
        var cachedLogon = logon is not null && logon.Equals(sys.MachineName, StringComparison.OrdinalIgnoreCase);
        Check(root, C.DomainLogonServer, "Logon Server",
                cachedLogon ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                cachedLogon ? $"Вход выполнен по кэшированным учётным данным (LOGONSERVER = {logon}) — контроллер был недоступен при входе"
                            : $"Logon Server: {logon ?? "не определён"}")
            .WithEvidence("logonServer", logon);

        // Secure channel
        var sc = await _cmd.RunAsync("nltest", $"/sc_query:{domain}", ctx.CommandTimeout, ct).ConfigureAwait(false);
        if (sc.Started)
        {
            var (ok, status, trusted) = NltestParser.ParseScQuery(sc.StdOut + sc.StdErr, sc.ExitCode);
            Check(root, C.DomainSecureChannel, "Secure Channel", ok ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                    ok ? $"Безопасный канал установлен ({trusted ?? dcHost})" : $"Безопасный канал не установлен: {status}",
                    ok ? null : Severity.Critical)
                .WithEvidence("status", status).WithEvidence("trustedDc", trusted)
                .WithRecommendation(ok ? "" : "Восстановите доверие: Test-ComputerSecureChannel -Repair -Credential DOMAIN\\Admin (вручную, с учётной записью домена).");
        }
        else
        {
            Skipped(root, C.DomainSecureChannel, "Secure Channel", "nltest недоступен");
        }

        // DC connectivity (DNS 53, Kerberos 88, LDAP 389, SMB 445)
        var target = dc.Address ?? dcHost ?? logon;
        if (!string.IsNullOrEmpty(target))
        {
            var ports = new[] { 53, 88, 389, 445 };
            var outcomes = await Task.WhenAll(ports.Select(p => _net.TcpConnectAsync(target, p, ctx.Settings.Diagnostics.TcpTimeoutMs, ct))).ConfigureAwait(false);
            var open = outcomes.Count(o => o.Success);
            var conn = Check(root, C.DomainDcConnectivity, "Доступность контроллера домена",
                open == ports.Length ? DiagnosticStatus.Ok : open == 0 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                open == ports.Length ? $"{target}: порты 53/88/389/445 доступны"
                : open == 0 ? $"{target}: контроллер недоступен (порты 53/88/389/445 закрыты)"
                : $"{target}: недоступны порты {string.Join(", ", outcomes.Where(o => !o.Success).Select(o => o.Port))}");
            foreach (var o in outcomes) conn.WithEvidence($"tcp {o.Port}", o.Success ? $"{o.ElapsedMs} ms" : o.Error);
        }
        else
        {
            Check(root, C.DomainDcConnectivity, "Доступность контроллера домена", DiagnosticStatus.Error, "Контроллер домена не определён");
        }

        // Time sync
        var timeSource = dcHost ?? domain;
        var w32 = await _cmd.RunAsync("w32tm", $"/stripchart /computer:{timeSource} /samples:3 /dataonly", TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
        var offset = W32tmParser.ParseStripchartOffset(w32.StdOut);
        if (offset is { } off)
        {
            var st = TimeStatus(off, ctx.Settings.Diagnostics.TimeSkewWarningSeconds, ctx.Settings.Diagnostics.TimeSkewCriticalSeconds);
            Check(root, C.DomainTime, "Синхронизация времени", st,
                    st == DiagnosticStatus.Ok ? $"Расхождение с {timeSource}: {off:+0.000;-0.000} с" : $"Расхождение с {timeSource}: {off:+0.0;-0.0} с (Kerberos допускает до 300 с)")
                .WithEvidence("offsetSeconds", off.ToString("F3", System.Globalization.CultureInfo.InvariantCulture))
                .WithRecommendation(st == DiagnosticStatus.Ok ? "" : "Выполните синхронизацию времени.", st == DiagnosticStatus.Ok ? Array.Empty<string>() : new[] { A.TimeResync });
        }
        else
        {
            Check(root, C.DomainTime, "Синхронизация времени", DiagnosticStatus.Warning, $"Не удалось измерить расхождение времени с {timeSource}")
                .WithDetails(FirstLine(w32.StdOut + w32.StdErr));
        }

        // Group Policy: gpresult exit code + GroupPolicy operational errors
        var gp = await _cmd.RunAsync("gpresult", "/r /scope:computer", TimeSpan.FromSeconds(60), ct).ConfigureAwait(false);
        var gpEvents = await _events.QueryAsync("Microsoft-Windows-GroupPolicy/Operational", TimeSpan.FromHours(24), 200, false, ct).ConfigureAwait(false);
        var gpErrors = gpEvents.Events.Count;
        var gpStatus = !gp.Started ? DiagnosticStatus.Skipped
            : gpErrors > 0 ? DiagnosticStatus.Warning
            : gp.ExitCode == 0 ? DiagnosticStatus.Ok
            : DiagnosticStatus.Info; // computer scope often needs admin rights
        var gpCheck = Check(root, C.DomainGpo, "Group Policy", gpStatus,
            gpErrors > 0 ? $"Ошибок применения политик за 24 ч: {gpErrors} (последняя: {gpEvents.Events[0].Message.Split('\n')[0]})"
            : gp.ExitCode == 0 ? "Групповые политики применяются без ошибок"
            : "Результат политик компьютера недоступен (нужны права администратора)");
        gpCheck.WithEvidence("gpresultExit", gp.ExitCode).WithEvidence("errors24h", gpErrors);
        if (gpErrors > 0) gpCheck.WithRecommendation("Выполните gpupdate /force и проверьте доступ к SYSVOL.", A.GpUpdate);

        // Kerberos tickets
        var klist = await _cmd.RunAsync("klist", "", TimeSpan.FromSeconds(15), ct).ConfigureAwait(false);
        if (klist.Started)
        {
            var tickets = KlistParser.CountTickets(klist.StdOut);
            Check(root, C.DomainKerberos, "Kerberos", tickets > 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
                    tickets > 0 ? $"Билетов Kerberos в кэше: {tickets}" : "Билеты Kerberos отсутствуют (вход по NTLM/кэшу или недоступен KDC)")
                .WithEvidence("tickets", tickets);
        }

        root.Summary = DefaultSummary(root);
    }

    private static string FirstLine(string s) => s.Split('\n').Select(l => l.Trim()).FirstOrDefault(l => l.Length > 0) ?? "";
}
