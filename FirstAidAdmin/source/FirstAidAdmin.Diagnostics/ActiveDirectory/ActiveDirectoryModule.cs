using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Domain;
using C = FirstAidAdmin.Core.CheckIds;

namespace FirstAidAdmin.Diagnostics.ActiveDirectory;

/// <summary>Active Directory context: user, extended DC ports, SYSVOL, failed logons (Security log, admin only).</summary>
public sealed class ActiveDirectoryModule : DiagnosticModuleBase
{
    private readonly ICommandRunner _cmd;
    private readonly INetworkProbe _net;
    private readonly IFileSystemProbe _fs;
    private readonly IEventLogProbe _events;

    public ActiveDirectoryModule(ICommandRunner cmd, INetworkProbe net, IFileSystemProbe fs, IEventLogProbe events)
    {
        _cmd = cmd;
        _net = net;
        _fs = fs;
        _events = events;
    }

    public override string Id => ModuleIds.ActiveDirectory;
    public override string Name => "Active Directory";
    public override DiagnosticCategory Category => DiagnosticCategory.ActiveDirectory;

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var sys = ctx.System;
        if (!sys.IsDomainJoined || string.IsNullOrWhiteSpace(sys.DomainName))
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Компьютер не входит в домен";
            return;
        }
        var domain = sys.DomainName!;

        // User context (whoami prints fixed-format values for /upn and /fqdn)
        var upn = await _cmd.RunAsync("whoami", "/upn", TimeSpan.FromSeconds(10), ct).ConfigureAwait(false);
        var groups = await _cmd.RunAsync("whoami", "/groups /fo csv /nh", TimeSpan.FromSeconds(10), ct).ConfigureAwait(false);
        var groupCount = groups.Success ? groups.StdOut.Split('\n').Count(l => l.Trim().Length > 0) : 0;
        Check(root, C.AdUserContext, "Пользователь домена", DiagnosticStatus.Info,
                $"{sys.QualifiedUser}{(upn.Success ? " (" + upn.StdOut.Trim() + ")" : "")}, групп в токене: {groupCount}")
            .WithEvidence("user", sys.QualifiedUser).WithEvidence("groups", groupCount).WithEvidence("isAdmin", sys.IsAdmin);

        // Extended DC ports: GC 3268, RPC 135, kpasswd 464, LDAPS 636
        var dc = ctx.Shared.TryGetValue(DomainModule.SharedDcName, out var d) ? d as string : null;
        dc ??= sys.LogonServer is { Length: > 0 } ls && !ls.Equals(sys.MachineName, StringComparison.OrdinalIgnoreCase) ? ls : domain;
        var ports = new (int Port, string Name)[] { (135, "RPC"), (389, "LDAP"), (464, "kpasswd"), (636, "LDAPS"), (3268, "Global Catalog") };
        var outcomes = await Task.WhenAll(ports.Select(p => _net.TcpConnectAsync(dc, p.Port, ctx.Settings.Diagnostics.TcpTimeoutMs, ct))).ConfigureAwait(false);
        var essential = outcomes.Where(o => o.Port is 135 or 389).ToList();
        var portsCheck = Check(root, C.AdDcPorts, "Службы контроллера домена",
            essential.All(o => o.Success) ? (outcomes.All(o => o.Success) ? DiagnosticStatus.Ok : DiagnosticStatus.Info)
            : essential.Any(o => o.Success) ? DiagnosticStatus.Warning : DiagnosticStatus.Error,
            $"{dc}: " + string.Join(", ", ports.Zip(outcomes).Select(x => $"{x.First.Name} {(x.Second.Success ? "✓" : "✗")}")));
        foreach (var (p, o) in ports.Zip(outcomes)) portsCheck.WithEvidence($"{p.Name} ({p.Port})", o.Success ? "open" : o.Error);

        // SYSVOL
        var sysvol = $@"\\{domain}\SYSVOL";
        if (ctx.System.IsWindows)
        {
            var ok = await _fs.DirectoryExistsWithTimeoutAsync(sysvol, 8000, ct).ConfigureAwait(false);
            Check(root, C.AdSysvol, "Доступ к SYSVOL", ok ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                ok ? $"{sysvol} доступен" : $"{sysvol} недоступен — групповые политики и сценарии входа не применяются");
        }

        // Failed logons (Security log requires admin)
        if (!sys.IsAdmin)
        {
            Skipped(root, C.AdLogonFailures, "Неудачные попытки входа", "Журнал Security доступен только администратору", requiresAdmin: true);
        }
        else
        {
            var sec = await _events.QueryAsync("Security", TimeSpan.FromHours(24), 500, false, ct, new[] { 4625, 4771, 4740 }).ConfigureAwait(false);
            if (sec.AccessDenied || !sec.Available)
                Skipped(root, C.AdLogonFailures, "Неудачные попытки входа", sec.Error ?? "Журнал Security недоступен", true);
            else
            {
                var failed = sec.Events.Count(e => e.EventId is 4625 or 4771);
                var lockouts = sec.Events.Count(e => e.EventId == 4740);
                Check(root, C.AdLogonFailures, "Неудачные попытки входа",
                        lockouts > 0 ? DiagnosticStatus.Error : failed >= 5 ? DiagnosticStatus.Warning : DiagnosticStatus.Ok,
                        $"За 24 ч: неудачных входов {failed}, блокировок {lockouts}")
                    .WithEvidence("failed", failed).WithEvidence("lockouts", lockouts);
            }
        }
    }
}
