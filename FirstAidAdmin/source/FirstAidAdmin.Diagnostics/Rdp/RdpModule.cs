using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Rdp;

/// <summary>RDP diagnostics. Read-only: never changes RDP settings.</summary>
public sealed class RdpModule : DiagnosticModuleBase
{
    private const string TsKey = @"SYSTEM\CurrentControlSet\Control\Terminal Server";
    private const string RdpTcpKey = TsKey + @"\WinStations\RDP-Tcp";
    // Language independent resource id of the "Remote Desktop" firewall rule group.
    public const string FirewallGroup = "@FirewallAPI.dll,-28752";

    private readonly IServiceProbe _services;
    private readonly IRegistryProbe _registry;
    private readonly INetworkProbe _net;
    private readonly IPowerShellRunner _ps;

    public RdpModule(IServiceProbe services, IRegistryProbe registry, INetworkProbe net, IPowerShellRunner ps)
    {
        _services = services;
        _registry = registry;
        _net = net;
        _ps = ps;
    }

    public override string Id => ModuleIds.Rdp;
    public override string Name => "Удалённый рабочий стол (RDP)";
    public override DiagnosticCategory Category => DiagnosticCategory.Rdp;
    public override IReadOnlyList<string> InputKeys => new[] { Core.Abstractions.InputKeys.RdpTarget, Core.Abstractions.InputKeys.RdpPort };

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var target = ctx.Input(Core.Abstractions.InputKeys.RdpTarget);
        var port = int.TryParse(ctx.Input(Core.Abstractions.InputKeys.RdpPort), out var p) && p is > 0 and < 65536 ? p : 3389;

        // Remote target check first if requested (the most common "can't connect to X" case).
        if (target is not null)
        {
            var ping = await _net.PingAsync(target, ctx.Settings.Diagnostics.PingTimeoutMs, ct).ConfigureAwait(false);
            Check(root, C.RdpTargetPing, $"Ping {target}", ping.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
                ping.Success ? $"{target} отвечает ({ping.RoundTripMs} мс)" : $"{target} не отвечает на ping ({ping.Status}); ICMP может блокироваться")
                .WithEvidence("target", target);
            var tcp = await _net.TcpConnectAsync(target, port, Math.Max(3000, ctx.Settings.Diagnostics.TcpTimeoutMs), ct).ConfigureAwait(false);
            Check(root, C.RdpTargetTcp, $"TCP {target}:{port}", tcp.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                    tcp.Success ? $"Порт {port} на {target} открыт ({tcp.ElapsedMs} мс)" : $"Порт {port} на {target} недоступен ({tcp.Error})")
                .WithEvidence("target", target).WithEvidence("port", port);
        }

        if (!ctx.System.IsWindows)
        {
            Skipped(root, C.RdpService, "Служба TermService", "Локальные проверки RDP доступны только в Windows");
            return;
        }

        // Local RDP host checks
        var svc = _services.Get("TermService");
        Check(root, C.RdpService, "Служба TermService",
                svc.State == ServiceState.Running ? DiagnosticStatus.Ok : svc.State == ServiceState.NotFound ? DiagnosticStatus.Warning : DiagnosticStatus.Error,
                svc.State == ServiceState.Running ? "Служба удалённых рабочих столов запущена" : $"Служба: {svc.State}, запуск: {svc.StartMode}")
            .WithEvidence("state", svc.State).WithEvidence("startMode", svc.StartMode);

        var deny = ToInt(_registry.GetValue(RegistryHive.LocalMachine, TsKey, "fDenyTSConnections"));
        Check(root, C.RdpEnabled, "Удалённый рабочий стол разрешён",
                deny == 0 ? DiagnosticStatus.Ok : deny == 1 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                deny == 0 ? "Удалённые подключения разрешены" : deny == 1 ? "Удалённые подключения запрещены (fDenyTSConnections = 1)" : "Не удалось прочитать настройку")
            .WithEvidence("fDenyTSConnections", deny)
            .WithRecommendation(deny == 1 ? "Включите RDP вручную, если это разрешено политикой (программа не меняет настройки RDP)." : "", deny == 1 ? new[] { A.OpenRemoteSettings } : Array.Empty<string>());

        var nla = ToInt(_registry.GetValue(RegistryHive.LocalMachine, RdpTcpKey, "UserAuthentication"));
        Check(root, C.RdpNla, "Network Level Authentication", nla == 1 ? DiagnosticStatus.Ok : DiagnosticStatus.Info,
                nla == 1 ? "NLA включена (клиент должен поддерживать CredSSP)" : nla == 0 ? "NLA выключена (менее безопасно)" : "Не удалось прочитать настройку NLA")
            .WithEvidence("UserAuthentication", nla);

        var cfgPort = ToInt(_registry.GetValue(RegistryHive.LocalMachine, RdpTcpKey, "PortNumber")) ?? 3389;
        Check(root, C.RdpPort, "Порт RDP", cfgPort == 3389 ? DiagnosticStatus.Ok : DiagnosticStatus.Info,
            cfgPort == 3389 ? "Стандартный порт 3389" : $"Нестандартный порт {cfgPort} — подключайтесь как host:{cfgPort}").WithEvidence("port", cfgPort);

        var listening = _net.GetListeningTcpPorts().Contains(cfgPort);
        Check(root, C.RdpListening, "Прослушивание порта",
            listening ? DiagnosticStatus.Ok : deny == 1 || svc.State != ServiceState.Running ? DiagnosticStatus.Warning : DiagnosticStatus.Error,
            listening ? $"Порт {cfgPort} прослушивается" : $"Порт {cfgPort} не прослушивается");

        // Firewall rules of the Remote Desktop group (read-only)
        var json = await _ps.RunJsonAsync(
            $"$p=Get-NetFirewallProfile -ErrorAction SilentlyContinue | ? Enabled | Select -Expand Name; " +
            $"$r=Get-NetFirewallRule -Group '{FirewallGroup}' -Direction Inbound -ErrorAction SilentlyContinue | Select DisplayName,@{{n='Enabled';e={{[string]$_.Enabled}}}},@{{n='Profile';e={{[string]$_.Profile}}}}; " +
            "@{profiles=@($p); rules=@($r)} | ConvertTo-Json -Depth 3 -Compress", TimeSpan.FromSeconds(30), ct).ConfigureAwait(false);
        if (json is { } j)
        {
            var profiles = j.TryGetProperty("profiles", out var pr) && pr.ValueKind == JsonValueKind.Array ? pr.EnumerateArray().Select(x => x.GetString() ?? "").ToList() : new List<string>();
            var rules = j.TryGetProperty("rules", out var rr) && rr.ValueKind == JsonValueKind.Array ? rr.EnumerateArray().ToList() : new List<JsonElement>();
            var enabled = rules.Count(r => r.TryGetProperty("Enabled", out var e) && string.Equals(e.GetString(), "True", StringComparison.OrdinalIgnoreCase));
            var fwOn = profiles.Count > 0;
            var st = !fwOn || enabled > 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error;
            var fw = Check(root, C.RdpFirewall, "Брандмауэр Windows (RDP)", st,
                !fwOn ? "Брандмауэр выключен для всех профилей — не блокирует RDP"
                : enabled > 0 ? $"Правила «Удалённый рабочий стол» включены: {enabled} из {rules.Count} (активные профили: {string.Join(", ", profiles)})"
                : $"Правила «Удалённый рабочий стол» выключены при включённом брандмауэре ({string.Join(", ", profiles)})");
            foreach (var r in rules)
                fw.WithEvidence(r.TryGetProperty("DisplayName", out var dn) ? dn.GetString() ?? "" : "rule",
                    $"{(r.TryGetProperty("Enabled", out var e) ? e.GetString() : "")}; {(r.TryGetProperty("Profile", out var pf) ? pf.GetString() : "")}");
            if (st != DiagnosticStatus.Ok) fw.WithRecommendation("Включите правила группы «Удалённый рабочий стол» в брандмауэре.", A.OpenFirewall);
        }
        else
        {
            Check(root, C.RdpFirewall, "Брандмауэр Windows (RDP)", DiagnosticStatus.Info, "Не удалось получить правила брандмауэра");
        }
    }

    private static int? ToInt(object? v) => v switch
    {
        int i => i,
        long l => (int)l,
        string s when int.TryParse(s, out var x) => x,
        _ => null
    };
}
