using FirstAidAdmin.Diagnostics.Parsers;
using FirstAidAdmin.Infrastructure.Commands;
using FirstAidAdmin.Infrastructure.Network;
using FirstAidAdmin.Infrastructure.Windows;

namespace FirstAidAdmin.Tests;

public class ParserTests
{
    private const string NetshEn = """

        There is 1 interface on the system:

            Name                   : Wi-Fi
            Description            : Intel(R) Wi-Fi 6 AX201 160MHz
            GUID                   : 1234
            Physical address       : aa:bb:cc:dd:ee:ff
            Interface type         : Primary
            State                  : connected
            SSID                   : CorpWiFi
            AP BSSID               : 11:22:33:44:55:66
            Band                   : 5 GHz
            Channel                : 44
            Network type           : Infrastructure
            Radio type             : 802.11ax
            Authentication         : WPA2-Enterprise
            Cipher                 : CCMP
            Connection mode        : Auto Connect
            Receive rate (Mbps)    : 1201
            Transmit rate (Mbps)   : 960.5
            Signal                 : 87%
            Profile                : CorpWiFi
        """;

    private const string NetshRu = """
            Имя                    : Беспроводная сеть
            Описание               : Realtek 8822CE
            Состояние              : подключено
            SSID                   : Office
            BSSID                  : 66:55:44:33:22:11
            Тип радио              : 802.11ac
            Проверка подлинности   : WPA2-Personal
            Канал                  : 6
            Скорость приема (Мбит/с)  : 144,4
            Скорость передачи (Мбит/с) : 72
            Сигнал                 : 34%
        """;

    [Fact]
    public void Netsh_English_IsParsed()
    {
        var w = Assert.Single(NetshWlanParser.Parse(NetshEn));
        Assert.True(w.Connected);
        Assert.Equal("CorpWiFi", w.Ssid);
        Assert.Equal("11:22:33:44:55:66", w.Bssid);
        Assert.Equal("44", w.Channel);
        Assert.Equal("802.11ax", w.RadioType);
        Assert.Equal("WPA2-Enterprise", w.Authentication);
        Assert.Equal(1201, w.ReceiveRateMbps);
        Assert.Equal(960.5, w.TransmitRateMbps);
        Assert.Equal(87, w.SignalPercent);
    }

    [Fact]
    public void Netsh_Russian_IsParsed()
    {
        var w = Assert.Single(NetshWlanParser.Parse(NetshRu));
        Assert.True(w.Connected);
        Assert.Equal("Office", w.Ssid);
        Assert.Equal(144.4, w.ReceiveRateMbps);
        Assert.Equal(34, w.SignalPercent);
        Assert.Equal("6", w.Channel);
    }

    [Fact]
    public void Nltest_DsGetDc_IsParsed()
    {
        var text = """
                   DC: \\DC01.corp.local
              Address: \\10.0.0.10
             Dom Guid: 00000000-0000-0000-0000-000000000000
             Dom Name: corp.local
          Forest Name: corp.local
         Dc Site Name: Default-First-Site-Name
        Our Site Name: Default-First-Site-Name
                Flags: PDC GC DS LDAP KDC TIMESERV
        The command completed successfully
        """;
        var dc = NltestParser.ParseDsGetDc(text);
        Assert.Equal("DC01.corp.local", dc.DcName);
        Assert.Equal("10.0.0.10", dc.Address);
        Assert.Equal("corp.local", dc.DomainName);
        Assert.Equal("Default-First-Site-Name", dc.SiteName);
    }

    [Fact]
    public void Nltest_ScQuery_SuccessAndFailure()
    {
        var ok = NltestParser.ParseScQuery("""
            Flags: 30 HAS_IP  HAS_TIMESERV
            Trusted DC Name \\DC01.corp.local
            Trusted DC Connection Status Status = 0 0x0 NERR_Success
            The command completed successfully
            """, 0);
        Assert.True(ok.Success);
        Assert.Equal("DC01.corp.local", ok.TrustedDc);

        var bad = NltestParser.ParseScQuery("""
            Flags: 0
            Trusted DC Name
            Trusted DC Connection Status Status = 1788 0x6fc ERROR_TRUSTED_DOMAIN_FAILURE
            The command completed successfully
            """, 0);
        Assert.False(bad.Success);
        Assert.Contains("ERROR_TRUSTED_DOMAIN_FAILURE", bad.Status);

        var err = NltestParser.ParseScQuery("I_NetLogonControl failed: Status = 1355 0x54b ERROR_NO_SUCH_DOMAIN", 1);
        Assert.False(err.Success);
    }

    [Fact]
    public void W32tm_Offset_IsParsed()
    {
        var text = """
            Tracking dc01 [10.0.0.10:123].
            Collecting 3 samples.
            The current time is 03.10.2026 19:31:00.
            19:31:00, +00.0123456s
            19:31:02, +00.0110000s
            19:31:04, -00.0200000s
            """;
        var off = W32tmParser.ParseStripchartOffset(text);
        Assert.NotNull(off);
        Assert.InRange(off!.Value, 0.010, 0.013);
        Assert.Equal(-421.5, W32tmParser.ParseStripchartOffset("19:31:00, -421,5000000s"));
        Assert.Null(W32tmParser.ParseStripchartOffset("error 0x800705B4"));
    }

    [Fact]
    public void Route_DefaultRoutes_AreParsed()
    {
        var text = """
            IPv4 Route Table
            ===========================================================================
            Active Routes:
            Network Destination        Netmask          Gateway       Interface  Metric
                      0.0.0.0          0.0.0.0      192.168.1.1    192.168.1.50     25
                    127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
                  192.168.1.0    255.255.255.0         On-link      192.168.1.50    281
            """;
        var defaults = RouteParser.DefaultRoutes(text);
        var d = Assert.Single(defaults);
        Assert.Equal("192.168.1.1", d.Gateway);
        Assert.Equal(25, d.Metric);
        Assert.Equal(3, RouteParser.ParseIPv4(text).Count);
    }

    [Fact]
    public void Arp_IsParsed_EnglishAndRussian()
    {
        var text = """
            Interface: 192.168.1.50 --- 0x5
              Internet Address      Physical Address      Type
              192.168.1.1           a0-b1-c2-d3-e4-f5     dynamic
            Интерфейс: 10.0.0.5 --- 0x7
              адрес в Интернете      Физический адрес      Тип
              10.0.0.1              00-11-22-33-44-55     динамический
            """;
        var t = ArpParser.Parse(text);
        Assert.Equal("A0-B1-C2-D3-E4-F5", t["192.168.1.1"]);
        Assert.True(t.ContainsKey("10.0.0.1"));
    }

    [Fact]
    public void Klist_CountsTickets() => Assert.Equal(2, KlistParser.CountTickets("Cached Tickets: (2)\n\n#0>\tClient: a\n\n#1>\tClient: b\n"));

    [Fact]
    public void Cbs_Analyze_FindsViolations()
    {
        var log = """
            2026-10-03 10:00:00, Info  CSI    00000001 [SR] Verifying 100 components
            2026-10-03 10:01:00, Info  CSI    00000002 [SR] Hashes for file member \SystemRoot\x.dll do not match actual file
            2026-10-03 10:02:00, Info  CSI    00000003 [SR] Cannot repair member file [l:10]"x.dll"
            2026-10-03 10:03:00, Info  CSI    00000004 [SR] Verify complete
            """;
        var (v, _, completed) = CbsLogParser.Analyze(log);
        Assert.Equal(2, v);
        Assert.True(completed);
        Assert.Equal(0, CbsLogParser.Analyze("[SR] Verify complete").Violations);
    }

    [Theory]
    [InlineData("10.1.2.3", true)]
    [InlineData("172.16.0.1", true)]
    [InlineData("172.32.0.1", false)]
    [InlineData("192.168.0.1", true)]
    [InlineData("8.8.8.8", false)]
    [InlineData("169.254.10.1", true)]
    [InlineData("fe80::1", true)]
    public void IpClassifier_PrivateDetection(string ip, bool expected) => Assert.Equal(expected, IpClassifier.IsPrivateOrLocal(ip));

    [Fact]
    public void WindowsUpdateErrors_AreDescribed()
    {
        Assert.Contains("места", WindowsUpdateErrors.Describe("0x80070070"));
        Assert.Equal("0x80073712", WindowsUpdateErrors.ToHex(unchecked((int)0x80073712)));
        Assert.Equal("Неизвестная ошибка", WindowsUpdateErrors.Describe("0x12345678"));
    }

    [Fact]
    public void DnsWire_QueryAndResponse_RoundTrip()
    {
        var q = DnsWire.BuildQuery(0x1234, "www.example.com");
        Assert.Equal(0x12, q[0]);
        Assert.Equal(0x34, q[1]);

        // Build a response: header + question + one A answer (compressed name pointer to 0x0c).
        var resp = new List<byte>(q);
        resp[2] = 0x81; resp[3] = 0x80; // response, RD, RA, rcode 0
        resp[7] = 1; // ANCOUNT = 1
        resp.AddRange(new byte[] { 0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 60, 0, 4, 93, 184, 216, 34 });
        var parsed = DnsWire.Parse(resp.ToArray());
        Assert.Equal(0x1234, parsed.Id);
        Assert.Equal(0, parsed.RCode);
        Assert.Equal("93.184.216.34", Assert.Single(parsed.Addresses));

        var nx = new List<byte>(q) { };
        nx[2] = 0x81; nx[3] = 0x83; // NXDOMAIN
        Assert.Equal(3, DnsWire.Parse(nx.ToArray()).RCode);
        Assert.Equal("NXDOMAIN", DnsWire.RCodeText(3));
    }

    [Fact]
    public void DnsWire_Srv_IsParsed()
    {
        var q = DnsWire.BuildQuery(7, "_ldap._tcp.dc._msdcs.corp.local", DnsWire.TypeSrv);
        var resp = new List<byte>(q);
        resp[2] = 0x81; resp[3] = 0x80; resp[7] = 1;
        var target = new List<byte> { 4, (byte)'d', (byte)'c', (byte)'0', (byte)'1', 4, (byte)'c', (byte)'o', (byte)'r', (byte)'p', 5, (byte)'l', (byte)'o', (byte)'c', (byte)'a', (byte)'l', 0 };
        var rdata = new List<byte> { 0, 0, 0, 100, 1, 0x85 }; // priority 0, weight 100, port 389
        rdata.AddRange(target);
        resp.AddRange(new byte[] { 0xC0, 0x0C, 0, 33, 0, 1, 0, 0, 2, 88, 0, (byte)rdata.Count });
        resp.AddRange(rdata);
        var parsed = DnsWire.Parse(resp.ToArray());
        Assert.Equal("dc01.corp.local:389", Assert.Single(parsed.SrvTargets));
    }

    [Fact]
    public void PowerShell_ParseJson_HandlesNoiseAndBom()
    {
        Assert.Null(PowerShellRunner.ParseJson(""));
        Assert.Null(PowerShellRunner.ParseJson("not json"));
        var j = PowerShellRunner.ParseJson("\uFEFFWARNING: x\r\n{\"a\":1}");
        Assert.Equal(1, j!.Value.GetProperty("a").GetInt32());
        Assert.Equal(2, PowerShellRunner.ParseJson("[1,2]")!.Value.GetArrayLength());
    }

    [Fact]
    public void PowerShell_Arguments_AreEncodedAndDisplayDecoded()
    {
        var args = PowerShellRunner.BuildArguments("Get-Date");
        Assert.Contains("-EncodedCommand", args);
        Assert.Contains("-NoProfile", args);
        var display = ProcessCommandRunner.DisplayCommand("powershell.exe", args);
        Assert.StartsWith("powershell:", display);
        Assert.Contains("Get-Date", display);
        Assert.Equal("ipconfig /all", ProcessCommandRunner.DisplayCommand("ipconfig", "/all"));
    }

    [Fact]
    public void HelperProtocol_RoundTrip()
    {
        var args = HelperProtocol.BuildArguments("restart-service", "Spooler", @"C:\Temp\faa-0123.json");
        var split = System.Text.RegularExpressions.Regex.Matches(args, "\"([^\"]*)\"|(\\S+)").Select(m => m.Groups[1].Success ? m.Groups[1].Value : m.Groups[2].Value).ToList();
        var (op, output, param) = HelperProtocol.Parse(split);
        Assert.Equal("restart-service", op);
        Assert.Equal(@"C:\Temp\faa-0123.json", output);
        Assert.Equal("Spooler", param);
    }

    [Fact]
    public void EventLog_XPath_IsBuilt()
    {
        var x = EventLogProbe.BuildXPath(TimeSpan.FromHours(24), false, null);
        Assert.Contains("Level=1 or Level=2", x);
        Assert.Contains("86400000", x);
        var ids = EventLogProbe.BuildXPath(TimeSpan.FromHours(1), false, new[] { 4625, 4740 });
        Assert.Contains("EventID=4625 or EventID=4740", ids);
        Assert.DoesNotContain("Level=", ids);
    }
}
