using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Diagnostics.Dns;
using FirstAidAdmin.Diagnostics.Network;
using FirstAidAdmin.Diagnostics.WiFi;
using FirstAidAdmin.Tests.Fakes;
using C = FirstAidAdmin.Core.CheckIds;

namespace FirstAidAdmin.Tests;

public class NetworkAnalyzerTests
{
    private static Task<DiagnosticResult> Run(FakeNetworkProbe net, FakeCommandRunner? cmd = null)
        => new NetworkModule(net, cmd ?? new FakeCommandRunner()).RunAsync(TestContext.Create(), CancellationToken.None);

    [Fact]
    public async Task Healthy_Network_AllKeyChecksOk()
    {
        var r = await Run(FakeNetworkProbe.Healthy());
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetAdapters).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetIPv4).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetGatewayPing).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetInternetIp).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetDnsResolve).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetHttp).Status);
        Assert.DoesNotContain(r.Checks, c => c.IsProblem);
    }

    [Fact]
    public async Task NoAdapter_IsCritical_AndChainSkipped()
    {
        var net = new FakeNetworkProbe();
        net.Adapters.Add(new NetworkAdapterInfo { Name = "Ethernet", IsUp = false, Type = "Ethernet" });
        var r = await Run(net);
        var a = r.Get(C.NetAdapters);
        Assert.Equal(DiagnosticStatus.Error, a.Status);
        Assert.Equal(Severity.Critical, a.Severity);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.NetInternetIp).Status);
        Assert.Contains("Этап отказа: Сетевые адаптеры", r.Summary);
    }

    [Fact]
    public async Task Apipa_IsDetected()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Adapters[0].IPv4.Clear();
        net.Adapters[0].IPv4.Add(new IpAddressInfo("169.254.12.7", 16));
        net.Adapters[0].Gateways.Clear();
        var r = await Run(net);
        var ip = r.Get(C.NetIPv4);
        Assert.Equal(DiagnosticStatus.Error, ip.Status);
        Assert.Equal("True", ip.GetEvidence("apipa"));
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.NetDhcp).Status);
        Assert.Contains(ActionIdsRenew, ip.Remediation);
    }

    private const string ActionIdsRenew = FirstAidAdmin.Core.ActionIds.RenewIp;

    [Fact]
    public async Task GatewayUnreachable_AndInternetDown()
    {
        var net = FakeNetworkProbe.Healthy();
        net.AllPingFail = true;
        net.AllTcpFail = true;
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.NetGatewayPing).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.NetInternetIp).Status);
        Assert.Contains("Этап отказа: Доступность шлюза", r.Summary);
    }

    [Fact]
    public async Task IcmpBlocked_ButTcpWorks_IsWarningNotError()
    {
        var net = FakeNetworkProbe.Healthy();
        net.PingFails.Add("8.8.8.8");
        net.PingFails.Add("1.1.1.1");
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.NetInternetIp).Status);
    }

    [Fact]
    public async Task DnsFailure_WithWorkingIp()
    {
        var net = FakeNetworkProbe.Healthy();
        net.AllDnsFail = true;
        net.Http = new HttpOutcome("x", false, 0, null, 10, "No such host");
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.NetInternetIp).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.NetDnsResolve).Status);
        Assert.Contains("Разрешение имён", r.Summary);
    }

    [Fact]
    public async Task CaptivePortal_RedirectIsWarning()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Http = new HttpOutcome("x", false, 302, "", 10, null);
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.NetHttp).Status);
        Assert.Contains("captive", r.Get(C.NetHttp).Summary);
    }

    [Fact]
    public async Task Proxy_IsReportedAsEvidence()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Proxy = new ProxyInfo { Enabled = true, Server = "proxy.corp:3128" };
        var r = await Run(net);
        Assert.Equal("True", r.Get(C.NetProxy).GetEvidence("enabled"));
        Assert.Contains("proxy.corp", r.Get(C.NetProxy).Summary);
    }

    [Fact]
    public async Task HighRetransmits_IsWarning()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Stats = new TcpStatistics { SegmentsSent = 100_000, SegmentsResent = 12_000 };
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.NetTcp).Status);
    }

    [Fact]
    public void VirtualAdapters_AreIgnored_UnlessTheyHaveGateway()
    {
        var list = new List<NetworkAdapterInfo>
        {
            new() { Name = "vEthernet (WSL)", IsUp = true, IsVirtual = true },
            new() { Name = "Ethernet", IsUp = true },
        };
        Assert.Equal("Ethernet", Assert.Single(NetworkModule.RelevantAdapters(list)).Name);
        var vpnOnly = new List<NetworkAdapterInfo> { new() { Name = "VPN", IsUp = true, IsVirtual = true, Gateways = { "10.8.0.1" } } };
        Assert.Single(NetworkModule.RelevantAdapters(vpnOnly));
    }
}

public class DnsAnalyzerTests
{
    private static Task<DiagnosticResult> Run(FakeNetworkProbe net, SystemSnapshot? sys = null, FakeServiceProbe? svc = null)
        => new DnsModule(net, svc ?? FakeServiceProbe.Healthy(), new FakePowerShell()).RunAsync(TestContext.Create(sys), CancellationToken.None);

    [Fact]
    public async Task Healthy_Workgroup_DomainChecksSkipped()
    {
        var r = await Run(FakeNetworkProbe.Healthy());
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsServersConfigured).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsServerReachable).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsResolveExternal).Status);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.DnsSrvLdap).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsClientService).Status);
    }

    [Fact]
    public async Task ConfiguredServerTimeout_IsError()
    {
        var net = FakeNetworkProbe.Healthy();
        net.ServerFails.Add("192.168.1.1");
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.DnsServerReachable).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsReference).Status);
    }

    [Fact]
    public async Task NoServers_IsError()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Adapters[0].DnsServers.Clear();
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.DnsServersConfigured).Status);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.DnsServerReachable).Status);
    }

    [Fact]
    public async Task DomainPc_WithPublicDns_IsFlagged()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Adapters[0].DnsServers.Clear();
        net.Adapters[0].DnsServers.Add("8.8.8.8");
        net.SrvMissing.Add("*");
        var r = await Run(net, TestContext.Domain());
        var cfg = r.Get(C.DnsServersConfigured);
        Assert.Equal(DiagnosticStatus.Error, cfg.Status);
        Assert.Equal("True", cfg.GetEvidence("publicOnDomain"));
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.DnsSrvLdap).Status);
        Assert.Contains("Google", cfg.Summary);
    }

    [Fact]
    public async Task DomainPc_SrvRecordsFound()
    {
        var net = FakeNetworkProbe.Healthy();
        net.Adapters[0].DnsServers.Clear();
        net.Adapters[0].DnsServers.Add("10.0.0.10");
        var r = await Run(net, TestContext.Domain());
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsSrvLdap).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsSrvKerberos).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsResolveInternal).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.DnsDc).Status);
    }

    [Fact]
    public async Task ExternalResolutionPartial_IsWarning()
    {
        var net = FakeNetworkProbe.Healthy();
        net.ResolveFails.Add("www.google.com");
        var r = await Run(net);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.DnsResolveExternal).Status);
    }

    [Fact]
    public void Reachable_TreatsRcodeAsAnswer()
    {
        Assert.True(DnsModule.Reachable(new DnsOutcome("x", false, Array.Empty<string>(), 1, "NXDOMAIN")));
        Assert.True(DnsModule.Reachable(new DnsOutcome("x", false, Array.Empty<string>(), 1, "REFUSED")));
        Assert.False(DnsModule.Reachable(new DnsOutcome("x", false, Array.Empty<string>(), 1, "timeout")));
    }
}

public class WiFiTests
{
    private static FakeNetworkProbe WifiNet()
    {
        var net = new FakeNetworkProbe();
        net.Adapters.Add(new NetworkAdapterInfo { Name = "Wi-Fi", Description = "Intel(R) Wi-Fi 6 AX201 160MHz", IsUp = true, IsWireless = true, IPv4 = { new IpAddressInfo("10.10.0.20", 24) }, Gateways = { "10.10.0.1" }, DnsServers = { "10.10.0.1" } });
        return net;
    }

    private static FakeCommandRunner Netsh(string state = "connected", int signal = 80)
    {
        var cmd = new FakeCommandRunner();
        cmd.Set("netsh wlan show interfaces", $"""
                Name                   : Wi-Fi
                Description            : Intel(R) Wi-Fi 6 AX201 160MHz
                State                  : {state}
                SSID                   : Corp
                BSSID                  : 11:22:33:44:55:66
                Radio type             : 802.11ax
                Authentication         : WPA2-Personal
                Channel                : 36
                Receive rate (Mbps)    : 866
                Transmit rate (Mbps)   : 866
                Signal                 : {signal}%
            """);
        return cmd;
    }

    [Fact]
    public async Task Connected_StrongSignal_AllStagesOk()
    {
        var r = await new WiFiModule(Netsh(), WifiNet(), FakeServiceProbe.Healthy()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.WifiInterface).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.WifiSignal).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.WifiStage).Status);
        Assert.Equal("Corp", r.Get(C.WifiInterface).GetEvidence("SSID"));
        Assert.Equal("36", r.Get(C.WifiInterface).GetEvidence("Channel"));
    }

    [Fact]
    public async Task Connected_ButGatewayDown_StageIsGateway()
    {
        var net = WifiNet();
        net.PingFails.Add("10.10.0.1");
        var r = await new WiFiModule(Netsh(signal: 30), net, FakeServiceProbe.Healthy()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.WifiSignal).Status);
        var stage = r.Get(C.WifiStage);
        Assert.Equal(DiagnosticStatus.Error, stage.Status);
        Assert.Contains("шлюз", stage.Summary);
    }

    [Fact]
    public async Task Connected_NoIp_StageIsDhcp()
    {
        var net = WifiNet();
        net.Adapters[0].IPv4.Clear();
        net.Adapters[0].IPv4.Add(new IpAddressInfo("169.254.1.1", 16));
        var r = await new WiFiModule(Netsh(), net, FakeServiceProbe.Healthy()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Contains("DHCP", r.Get(C.WifiStage).Summary);
    }

    [Fact]
    public async Task NoWifiAdapter_IsSkipped()
    {
        var svc = FakeServiceProbe.Healthy();
        svc.Services.Remove("WlanSvc");
        var r = await new WiFiModule(new FakeCommandRunner(), FakeNetworkProbe.Healthy(), svc).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Skipped, r.Status);
    }

    [Theory]
    [InlineData(90, DiagnosticStatus.Ok)]
    [InlineData(45, DiagnosticStatus.Warning)]
    [InlineData(10, DiagnosticStatus.Error)]
    public void Signal_Thresholds(int signal, DiagnosticStatus expected) => Assert.Equal(expected, WiFiModule.SignalStatus(signal));
}
