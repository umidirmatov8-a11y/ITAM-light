using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Parsers;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.WiFi;

public sealed class WiFiModule : DiagnosticModuleBase
{
    private readonly ICommandRunner _cmd;
    private readonly INetworkProbe _net;
    private readonly IServiceProbe _services;

    public WiFiModule(ICommandRunner cmd, INetworkProbe net, IServiceProbe services)
    {
        _cmd = cmd;
        _net = net;
        _services = services;
    }

    public override string Id => ModuleIds.WiFi;
    public override string Name => "Wi-Fi";
    public override DiagnosticCategory Category => DiagnosticCategory.WiFi;

    public static DiagnosticStatus SignalStatus(int? signal) => signal switch
    {
        null => DiagnosticStatus.Info,
        < 25 => DiagnosticStatus.Error,
        < 50 => DiagnosticStatus.Warning,
        _ => DiagnosticStatus.Ok
    };

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var wireless = _net.GetAdapters().Where(a => a.IsWireless).ToList();
        var svc = _services.Get("WlanSvc");
        if (wireless.Count == 0 && svc.State is ServiceState.NotFound or ServiceState.Stopped)
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Wi-Fi адаптер не обнаружен";
            Skipped(root, C.WifiInterface, "Wi-Fi интерфейс", "Wi-Fi адаптер не обнаружен");
            return;
        }

        Check(root, C.WifiService, "Служба WLAN AutoConfig", svc.State == ServiceState.Running ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                svc.State == ServiceState.Running ? "Служба WlanSvc запущена" : $"Служба WlanSvc: {svc.State}")
            .WithRecommendation(svc.State == ServiceState.Running ? "" : "Запустите службу WLAN AutoConfig (WlanSvc).", svc.State == ServiceState.Running ? Array.Empty<string>() : new[] { A.OpenServices });

        var r = await _cmd.RunAsync("netsh", "wlan show interfaces", TimeSpan.FromSeconds(15), ct).ConfigureAwait(false);
        var interfaces = r.Started ? NetshWlanParser.Parse(r.StdOut) : new List<WifiInterfaceInfo>();
        var wifi = interfaces.FirstOrDefault(i => i.Connected) ?? interfaces.FirstOrDefault();
        if (wifi is null)
        {
            Check(root, C.WifiInterface, "Wi-Fi интерфейс", DiagnosticStatus.Warning, "Wi-Fi интерфейсы не найдены через netsh");
            return;
        }

        var ethernetActive = _net.GetAdapters().Any(a => a.IsUp && !a.IsWireless && !a.IsVirtual && !a.IsLoopback && a.Gateways.Count > 0);
        var ifc = Check(root, C.WifiInterface, "Wi-Fi подключение",
            wifi.Connected ? DiagnosticStatus.Ok : ethernetActive ? DiagnosticStatus.Info : DiagnosticStatus.Error,
            wifi.Connected ? $"Подключено к «{wifi.Ssid}» ({wifi.RadioType}, канал {wifi.Channel})"
                           : ethernetActive ? "Wi-Fi не подключён (используется проводное подключение)" : $"Wi-Fi не подключён (состояние: {wifi.State})");
        ifc.WithEvidence("Interface", wifi.Name).WithEvidence("Description", wifi.Description).WithEvidence("SSID", wifi.Ssid)
            .WithEvidence("BSSID", wifi.Bssid).WithEvidence("Radio type", wifi.RadioType).WithEvidence("Authentication", wifi.Authentication)
            .WithEvidence("Cipher", wifi.Cipher).WithEvidence("Channel", wifi.Channel).WithEvidence("Band", wifi.Band)
            .WithEvidence("Receive rate (Mbps)", wifi.ReceiveRateMbps).WithEvidence("Transmit rate (Mbps)", wifi.TransmitRateMbps)
            .WithEvidence("Signal", wifi.SignalPercent is null ? "" : wifi.SignalPercent + "%");
        if (!wifi.Connected && !ethernetActive) ifc.WithRecommendation("Подключитесь к сети Wi-Fi или проверьте, не включён ли режим «в самолёте».", A.OpenWifiSettings);
        if (!wifi.Connected) return;

        Check(root, C.WifiSignal, "Уровень сигнала", SignalStatus(wifi.SignalPercent),
                $"Сигнал {wifi.SignalPercent}%, приём {wifi.ReceiveRateMbps} Мбит/с, передача {wifi.TransmitRateMbps} Мбит/с")
            .WithEvidence("signal", wifi.SignalPercent);

        var adapter = _net.GetAdapters().FirstOrDefault(a => a.IsWireless && a.IsUp && (a.Name == wifi.Name || a.Description == wifi.Description))
                      ?? _net.GetAdapters().FirstOrDefault(a => a.IsWireless && a.IsUp);
        var ip = adapter?.IPv4.FirstOrDefault(i => !IpClassifier.IsApipa(i.Address));
        Check(root, C.WifiIp, "IP-адрес Wi-Fi", ip is not null ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            ip is not null ? $"{ip.Address}/{ip.PrefixLength}" : "IP-адрес не получен (DHCP точки доступа не ответил)");

        var gw = adapter?.Gateways.FirstOrDefault(g => !g.Contains(':'));
        PingOutcome? gwPing = null;
        if (gw is not null)
        {
            gwPing = await _net.PingAsync(gw, ctx.Settings.Diagnostics.PingTimeoutMs, ct).ConfigureAwait(false);
            Check(root, C.WifiGateway, "Шлюз Wi-Fi", gwPing.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                gwPing.Success ? $"{gw} отвечает ({gwPing.RoundTripMs} мс)" : $"{gw} не отвечает ({gwPing.Status})");
        }
        else
        {
            Check(root, C.WifiGateway, "Шлюз Wi-Fi", DiagnosticStatus.Error, "Шлюз не получен");
        }

        // Stage of failure
        var internetOk = true;
        if (ctx.PreviousResults.TryGetValue(ModuleIds.Network, out var netResult))
            internetOk = netResult.Flatten().FirstOrDefault(c => c.Id == C.NetInternetIp)?.Status is not (DiagnosticStatus.Error or DiagnosticStatus.Critical);
        else
            internetOk = (await _net.TcpConnectAsync(ctx.Settings.Diagnostics.InternetProbeIps.FirstOrDefault() ?? "8.8.8.8", 53, ctx.Settings.Diagnostics.TcpTimeoutMs, ct).ConfigureAwait(false)).Success;

        var (stageStatus, stage, details, rec) = (ip, gwPing) switch
        {
            (null, _) => (DiagnosticStatus.Error, "Этап отказа: получение IP-адреса (DHCP)", "Wi-Fi подключён, но адрес не получен: DHCP точки доступа/маршрутизатора не отвечает или исчерпан пул.", "Переподключитесь к сети или обновите IP; проверьте DHCP на маршрутизаторе."),
            (_, null) or (_, { Success: false }) => (DiagnosticStatus.Error, "Этап отказа: шлюз (маршрутизатор)", "Адрес есть, но маршрутизатор не отвечает: изоляция клиентов, слабый сигнал или проблема маршрутизатора.", "Переподключитесь к Wi-Fi, проверьте маршрутизатор."),
            _ when !internetOk => (DiagnosticStatus.Error, "Этап отказа: Интернет за маршрутизатором", "Локальная часть Wi-Fi работает, но выхода в Интернет нет: проблема канала провайдера или маршрутизатора.", "Проверьте подключение маршрутизатора к провайдеру."),
            _ => (DiagnosticStatus.Ok, "Wi-Fi → IP → шлюз → Интернет: все этапы пройдены", (string?)null, (string?)null)
        };
        var stageCheck = Check(root, C.WifiStage, "Этап отказа Wi-Fi", stageStatus, stage).WithDetails(details);
        if (rec is not null) stageCheck.WithRecommendation(rec, A.RenewIp, A.OpenWifiSettings);
    }
}
