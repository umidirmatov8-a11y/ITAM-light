using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Diagnostics.Application;
using FirstAidAdmin.Diagnostics.Domain;
using FirstAidAdmin.Diagnostics.EventLog;
using FirstAidAdmin.Diagnostics.NetworkShare;
using FirstAidAdmin.Diagnostics.Performance;
using FirstAidAdmin.Diagnostics.Printer;
using FirstAidAdmin.Diagnostics.Rdp;
using FirstAidAdmin.Diagnostics.Security;
using FirstAidAdmin.Diagnostics.Services;
using FirstAidAdmin.Diagnostics.Storage;
using FirstAidAdmin.Diagnostics.WindowsHealth;
using FirstAidAdmin.Diagnostics.WindowsUpdate;
using FirstAidAdmin.Tests.Fakes;
using C = FirstAidAdmin.Core.CheckIds;
using K = FirstAidAdmin.Core.Abstractions.InputKeys;

namespace FirstAidAdmin.Tests;

public class DiskAnalyzerTests
{
    private static DriveSnapshot Drive(double usedPercent, long totalGb = 200, bool system = true)
    {
        var total = totalGb << 30;
        return new DriveSnapshot("C:\\", "", "NTFS", "Fixed", total, (long)(total * (100 - usedPercent) / 100), system);
    }

    [Theory]
    [InlineData(50, DiagnosticStatus.Ok)]
    [InlineData(86, DiagnosticStatus.Warning)]
    [InlineData(96, DiagnosticStatus.Error)]
    public void Evaluate_ByPercent(double used, DiagnosticStatus expected) => Assert.Equal(expected, StorageModule.Evaluate(Drive(used), 85, 95));

    [Fact]
    public void Evaluate_SmallFreeSpaceOnSystemDrive_IsError_EvenWithLowPercent()
        => Assert.Equal(DiagnosticStatus.Error, StorageModule.Evaluate(Drive(70, totalGb: 12), 85, 95)); // 3.6 GB free

    [Fact]
    public async Task Module_LowDisk_LargeTemp_DiskErrors()
    {
        var sys = new FakeSystemProbe();
        sys.Drives.Clear();
        sys.Drives.Add(Drive(98));
        sys.Drives.Add(new DriveSnapshot("D:\\", "Data", "NTFS", "Fixed", 500L << 30, 20L << 30, false));
        var fs = new FakeFileSystem { TempBytes = 6L << 30 };
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Get-PhysicalDisk"] = """[{"FriendlyName":"Samsung SSD","MediaType":"SSD","HealthStatus":"Warning","OperationalStatus":"Predictive Failure"}]""";
        ps.JsonByScriptFragment["PerfDisk"] = """{"PercentIdleTime":5,"CurrentDiskQueueLength":8,"AvgDisksecPerTransfer":0}""";
        var ev = new FakeEventLogProbe().Add("System", "disk", 7, 2, "bad block").Add("System", "disk", 7, 2, "bad block");

        var r = await new StorageModule(sys, fs, ps, ev).RunAsync(TestContext.Create(), CancellationToken.None);
        var c = r.Get(C.StorageSystem);
        Assert.Equal(DiagnosticStatus.Error, c.Status);
        Assert.Equal("98", c.GetEvidence("usedPercent"));
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.StorageDrives).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.StorageTemp).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.StoragePhysical).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.StoragePerformance).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.StorageEvents).Status);
        Assert.Contains(FirstAidAdmin.Core.ActionIds.ClearUserTemp, c.Remediation);
    }
}

public class DomainAnalyzerTests
{
    private static FakeCommandRunner HealthyDomainCommands()
    {
        var cmd = new FakeCommandRunner();
        cmd.Set("nltest /dsgetdc:corp.local", "           DC: \\\\DC01.corp.local\n      Address: \\\\10.0.0.10\n     Dom Name: corp.local\n Dc Site Name: HQ\nThe command completed successfully");
        cmd.Set("nltest /sc_query:corp.local", "Trusted DC Name \\\\DC01.corp.local\nTrusted DC Connection Status Status = 0 0x0 NERR_Success\nThe command completed successfully");
        cmd.Set("w32tm", "Tracking DC01.corp.local\n19:00:00, +00.0100000s\n19:00:02, +00.0110000s");
        cmd.Set("gpresult", "ok");
        cmd.Set("klist", "Cached Tickets: (3)\n#0> a\n#1> b\n#2> c");
        return cmd;
    }

    private static Task<DiagnosticResult> Run(FakeCommandRunner cmd, FakeNetworkProbe? net = null, SystemSnapshot? sys = null, FakeEventLogProbe? ev = null)
        => new DomainModule(cmd, net ?? FakeNetworkProbe.Healthy(), ev ?? new FakeEventLogProbe()).RunAsync(TestContext.Create(sys ?? TestContext.Domain()), CancellationToken.None);

    [Fact]
    public async Task Workgroup_IsInfoOnly()
    {
        var r = await new DomainModule(new FakeCommandRunner(), FakeNetworkProbe.Healthy(), new FakeEventLogProbe()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Info, r.Get(C.DomainMembership).Status);
        Assert.Single(r.Checks);
    }

    [Fact]
    public async Task HealthyDomain_AllOk()
    {
        var r = await Run(HealthyDomainCommands());
        foreach (var id in new[] { C.DomainMembership, C.DomainDcDiscovery, C.DomainLogonServer, C.DomainSecureChannel, C.DomainDcConnectivity, C.DomainTime, C.DomainGpo, C.DomainKerberos })
            Assert.Equal(DiagnosticStatus.Ok, r.Get(id).Status);
        Assert.Equal("DC01.corp.local", r.Get(C.DomainDcDiscovery).GetEvidence("dc"));
    }

    [Fact]
    public async Task BrokenSecureChannel_IsCritical()
    {
        var cmd = HealthyDomainCommands();
        cmd.Set("nltest /sc_query:corp.local", "Trusted DC Connection Status Status = 1788 0x6fc ERROR_TRUSTED_DOMAIN_FAILURE", 0);
        var r = await Run(cmd);
        var sc = r.Get(C.DomainSecureChannel);
        Assert.Equal(DiagnosticStatus.Error, sc.Status);
        Assert.Equal(Severity.Critical, sc.Severity);
    }

    [Fact]
    public async Task TimeSkew_IsError()
    {
        var cmd = HealthyDomainCommands();
        cmd.Set("w32tm", "19:00:00, +421.0000000s\n19:00:02, +421.5000000s");
        var r = await Run(cmd);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.DomainTime).Status);
        Assert.Contains(FirstAidAdmin.Core.ActionIds.TimeResync, r.Get(C.DomainTime).Remediation);
    }

    [Fact]
    public async Task DcUnreachable_AndCachedLogon()
    {
        var cmd = HealthyDomainCommands();
        var net = FakeNetworkProbe.Healthy();
        net.TcpFails.Add("10.0.0.10");
        var sys = TestContext.Domain();
        sys.LogonServer = "PC-001";
        var r = await Run(cmd, net, sys);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.DomainDcConnectivity).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.DomainLogonServer).Status);
    }

    [Fact]
    public async Task GpoErrors_AreWarning()
    {
        var ev = new FakeEventLogProbe().Add("Microsoft-Windows-GroupPolicy/Operational", "Microsoft-Windows-GroupPolicy", 1058, 2, "Cannot access gpt.ini");
        var r = await Run(HealthyDomainCommands(), ev: ev);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.DomainGpo).Status);
    }

    [Theory]
    [InlineData(0.5, DiagnosticStatus.Ok)]
    [InlineData(-90, DiagnosticStatus.Warning)]
    [InlineData(301, DiagnosticStatus.Error)]
    public void TimeStatus_Thresholds(double offset, DiagnosticStatus expected) => Assert.Equal(expected, DomainModule.TimeStatus(offset, 60, 300));
}

public class RdpAnalyzerTests
{
    private const string Ts = @"SYSTEM\CurrentControlSet\Control\Terminal Server";

    private static FakePowerShell Firewall(bool enabled)
    {
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment[RdpModule.FirewallGroup] = $$"""{"profiles":["Domain","Private"],"rules":[{"DisplayName":"Remote Desktop - User Mode (TCP-In)","Enabled":"{{(enabled ? "True" : "False")}}","Profile":"Any"}]}""";
        return ps;
    }

    [Fact]
    public async Task RemoteTarget_PortClosed_PingOk()
    {
        var net = FakeNetworkProbe.Healthy();
        net.TcpFails.Add("192.168.1.10:3389");
        var reg = new FakeRegistry().Set(RegistryHive.LocalMachine, Ts, "fDenyTSConnections", 0);
        var ctx = TestContext.Create(inputs: new() { [K.RdpTarget] = "192.168.1.10", [K.RdpPort] = "3389" });
        var r = await new RdpModule(FakeServiceProbe.Healthy(), reg, net, Firewall(true)).RunAsync(ctx, CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.RdpTargetPing).Status);
        var tcp = r.Get(C.RdpTargetTcp);
        Assert.Equal(DiagnosticStatus.Error, tcp.Status);
        Assert.Equal("192.168.1.10", tcp.GetEvidence("target"));
    }

    [Fact]
    public async Task LocalRdpDisabled_FirewallClosed_NotListening()
    {
        var reg = new FakeRegistry()
            .Set(RegistryHive.LocalMachine, Ts, "fDenyTSConnections", 1)
            .Set(RegistryHive.LocalMachine, Ts + @"\WinStations\RDP-Tcp", "UserAuthentication", 1)
            .Set(RegistryHive.LocalMachine, Ts + @"\WinStations\RDP-Tcp", "PortNumber", 3389);
        var r = await new RdpModule(FakeServiceProbe.Healthy(), reg, FakeNetworkProbe.Healthy(), Firewall(false)).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.RdpEnabled).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.RdpNla).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.RdpListening).Status); // disabled => not listening is expected
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.RdpFirewall).Status);
        Assert.Equal(DiagnosticStatus.Skipped, r.Checks.FirstOrDefault(c => c.Id == C.RdpTargetTcp)?.Status ?? DiagnosticStatus.Skipped);
    }

    [Fact]
    public async Task EnabledAndListening_IsOk_AndModuleIsReadOnly()
    {
        var reg = new FakeRegistry().Set(RegistryHive.LocalMachine, Ts, "fDenyTSConnections", 0);
        var net = FakeNetworkProbe.Healthy();
        net.Listening.Add(3389);
        var ps = Firewall(true);
        var r = await new RdpModule(FakeServiceProbe.Healthy(), reg, net, ps).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.RdpEnabled).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.RdpListening).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.RdpFirewall).Status);
        Assert.DoesNotContain(ps.Scripts, s => s.Contains("Set-", StringComparison.OrdinalIgnoreCase) || s.Contains("Enable-", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task ServiceStopped_IsError()
    {
        var svc = FakeServiceProbe.Healthy().Add("TermService", ServiceState.Stopped, ServiceStartMode.Disabled);
        var r = await new RdpModule(svc, new FakeRegistry(), FakeNetworkProbe.Healthy(), Firewall(true)).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.RdpService).Status);
    }
}

public class PerformanceAnalyzerTests
{
    private static readonly DiagnosticsSettings S = new();

    [Fact]
    public void Thresholds()
    {
        Assert.Equal(DiagnosticStatus.Ok, PerformanceAnalyzer.Cpu(24, S));
        Assert.Equal(DiagnosticStatus.Warning, PerformanceAnalyzer.Cpu(85, S));
        Assert.Equal(DiagnosticStatus.Error, PerformanceAnalyzer.Cpu(99, S));
        Assert.Equal(DiagnosticStatus.Warning, PerformanceAnalyzer.Ram(82, S));
        Assert.Equal(DiagnosticStatus.Error, PerformanceAnalyzer.Ram(95, S));
        Assert.Equal(DiagnosticStatus.Warning, PerformanceAnalyzer.Uptime(TimeSpan.FromDays(18), S));
        Assert.Equal(DiagnosticStatus.Ok, PerformanceAnalyzer.Uptime(TimeSpan.FromDays(1), S));
        Assert.Equal(DiagnosticStatus.Warning, PerformanceAnalyzer.Startup(25));
        Assert.Equal(DiagnosticStatus.Error, PerformanceAnalyzer.Boot(200));
    }

    [Theory]
    [InlineData("Windows has started up: Boot Duration : 61234ms", 61234)]
    [InlineData("Windows запущена: Длительность загрузки : 45 000мс", 45000)]
    public void BootDuration_IsParsed(string message, double expected) => Assert.Equal(expected, PerformanceAnalyzer.ParseBootMs(message));

    [Fact]
    public async Task Module_ReportsPotentialCauses_WithoutClaimingCausality()
    {
        var sys = new FakeSystemProbe { Memory = new MemorySnapshot(16L << 30, (long)((16L << 30) * 0.18)), Uptime = TimeSpan.FromDays(18), Cpu = 24 };
        sys.Drives[0] = new DriveSnapshot("C:\\", "", "NTFS", "Fixed", 256L << 30, (long)((256L << 30) * 0.04), true);
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Win32_StartupCommand"] = "[" + string.Join(",", Enumerable.Range(0, 5).Select(i => $$"""{"Name":"App{{i}}","Location":"HKCU"}""")) + "]";
        var r = await new PerformanceModule(sys, ps, FakeServiceProbe.Healthy(), new FakeEventLogProbe()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.PerfCpu).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.PerfRam).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.PerfUptime).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.PerfDisk).Status);
        Assert.Equal("18", r.Get(C.PerfUptime).GetEvidence("days"));
        Assert.StartsWith("Потенциальные причины", r.Summary);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.PerfBoot).Status); // not admin
    }
}

public class EventAnalyzerTests
{
    [Fact]
    public void Group_MergesIdenticalEvents_AndOrdersSeriousFirst()
    {
        var now = DateTimeOffset.Now;
        var events = new List<EventRecordInfo>();
        for (var i = 0; i < 4; i++) events.Add(new EventRecordInfo("System", "Microsoft-Windows-Kernel-Power", 41, 1, now.AddHours(-i), "The system has rebooted without cleanly shutting down first."));
        for (var i = 0; i < 30; i++) events.Add(new EventRecordInfo("System", "Microsoft-Windows-DistributedCOM", 10016, 2, now.AddMinutes(-i), "DCOM permission"));
        events.Add(new EventRecordInfo("System", "Service Control Manager", 7000, 2, now, "Service failed to start"));

        var groups = EventAnalyzer.Group(events);
        Assert.Equal(3, groups.Count);
        var kp = groups[0];
        Assert.Equal(41, kp.EventId);
        Assert.Equal(4, kp.Count);
        Assert.True(kp.IsSerious);
        Assert.Equal(now, kp.Last);
        Assert.True(groups.Single(g => g.EventId == 10016).IsNoise);
    }

    [Fact]
    public async Task Module_CreatesGroupChildren_AndSkipsSecurityWithoutAdmin()
    {
        var ev = new FakeEventLogProbe();
        for (var i = 0; i < 4; i++) ev.Add("System", "Microsoft-Windows-Kernel-Power", 41, 1, "rebooted", DateTimeOffset.Now.AddHours(-i));
        ev.Add("Application", "Application Error", 1000, 2, "Faulting application name: app.exe");
        var r = await new EventLogModule(ev).RunAsync(TestContext.Create(), CancellationToken.None);
        var sys = r.Get(C.EventsSystem);
        Assert.Equal(DiagnosticStatus.Error, sys.Status);
        var group = Assert.Single(sys.Checks);
        Assert.Equal("4", group.GetEvidence("count"));
        Assert.Equal("41", group.GetEvidence("eventId"));
        Assert.Contains("kernel-power.41", group.Id);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.EventsSecurity).Status);
        Assert.True(r.Get(C.EventsSecurity).RequiresAdmin);
    }

    [Fact]
    public async Task Module_AccessDenied_IsSkipped()
    {
        var ev = new FakeEventLogProbe();
        ev.Denied.Add("System");
        var r = await new EventLogModule(ev).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.EventsSystem).Status);
    }
}

public class OtherModuleTests
{
    [Fact]
    public async Task Printer_SpoolerStopped_StuckQueue_UnreachablePrinter()
    {
        var svc = FakeServiceProbe.Healthy().Add("Spooler", ServiceState.Stopped, ServiceStartMode.Automatic);
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Win32_Printer"] = """
            {"printers":[{"Name":"HP LaserJet","Default":true,"WorkOffline":false,"PrinterStatus":3,"DetectedErrorState":2,"PortName":"IP_10.0.0.50","Network":false,"DriverName":"HP"},
                         {"Name":"Microsoft Print to PDF","Default":false,"WorkOffline":false,"PrinterStatus":3,"DetectedErrorState":0,"PortName":"PORTPROMPT:","Network":false,"DriverName":"MS"}],
             "ports":[{"Name":"IP_10.0.0.50","HostAddress":"10.0.0.50","PortNumber":9100}],
             "jobs":[{"Name":"HP LaserJet, 12","JobStatus":"Error | Printing","Status":"Degraded"}]}
            """;
        var net = FakeNetworkProbe.Healthy();
        net.TcpFails.Add("10.0.0.50");
        net.PingFails.Add("10.0.0.50");
        var r = await new PrinterModule(svc, ps, net).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.PrinterSpooler).Status);
        Assert.Contains(FirstAidAdmin.Core.ActionIds.RestartSpooler, r.Get(C.PrinterSpooler).Remediation);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.PrinterInstalled).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.PrinterDefault).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.PrinterQueue).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.PrinterNetwork).Status);
    }

    [Fact]
    public async Task WindowsUpdate_FailedInstalls_DisabledService_PendingReboot()
    {
        var now = new DateTimeOffset(2026, 10, 3, 12, 0, 0, TimeSpan.Zero);
        var svc = FakeServiceProbe.Healthy().Add("wuauserv", ServiceState.Stopped, ServiceStartMode.Disabled);
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Microsoft.Update.Session"] = """
            {"history":[{"Date":"2026-10-01T10:00:00Z","Title":"2026-09 Cumulative Update","ResultCode":4,"HResult":"0x80070070"},
                        {"Date":"2026-09-30T10:00:00Z","Title":"2026-09 Cumulative Update","ResultCode":4,"HResult":"0x80070070"},
                        {"Date":"2026-07-01T10:00:00Z","Title":"2026-06 Cumulative Update","ResultCode":2,"HResult":"0x00000000"}],
             "hotfix":[{"Id":"KB5000001","InstalledOn":"2026-07-01T00:00:00"}],"error":null}
            """;
        var reg = new FakeRegistry();
        reg.Keys.Add(@"LocalMachine\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired");
        var r = await new WindowsUpdateModule(svc, ps, new FakeEventLogProbe(), reg, () => now).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.WuService).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.WuBits).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.WuLastUpdate).Status); // > 90 days
        var err = r.Get(C.WuHistoryErrors);
        Assert.Equal(DiagnosticStatus.Warning, err.Status);
        Assert.Equal("0x80070070", err.GetEvidence("codes"));
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.WuPendingReboot).Status);
    }

    [Fact]
    public void WindowsUpdate_LastSuccess_UsesHistoryAndHotfix()
    {
        var h = WindowsUpdateModule.ParseHistory(System.Text.Json.JsonDocument.Parse("""{"history":{"Date":"2026-09-01T00:00:00Z","Title":"x","ResultCode":2,"HResult":"0x0"},"hotfix":[{"Id":"KB1","InstalledOn":"2026-09-20T00:00:00"}]}""").RootElement);
        Assert.Single(h.Entries);
        Assert.Equal(20, h.LastSuccess!.Value.Day);
    }

    [Fact]
    public async Task WindowsHealth_NonAdmin_SkipsDism_ReadsCbs_AndCrashes()
    {
        var fs = new FakeFileSystem();
        fs.Content[Path.Combine("C:\\Windows", "Logs", "CBS", "CBS.log")] = "[SR] Hashes for file member x do not match\n[SR] Verify complete";
        var ev = new FakeEventLogProbe().Add("System", "Microsoft-Windows-Kernel-Power", 41, 1, "rebooted");
        var r = await new WindowsHealthModule(new FakePowerShell(), fs, new FakeRegistry(), ev, new FakeSystemProbe()).RunAsync(TestContext.Create(), CancellationToken.None);
        var dism = r.Get(C.HealthDism);
        Assert.Equal(DiagnosticStatus.Skipped, dism.Status);
        Assert.True(dism.RequiresAdmin);
        Assert.Contains(FirstAidAdmin.Core.ActionIds.DismCheckHealth, dism.Remediation);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.HealthCbs).Status);
        Assert.Equal(DiagnosticStatus.Warning, r.Get(C.HealthCrashes).Status);
    }

    [Fact]
    public async Task WindowsHealth_Admin_DismRepairable()
    {
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["-CheckHealth"] = """{"state":"Repairable"}""";
        var r = await new WindowsHealthModule(ps, new FakeFileSystem(), new FakeRegistry(), new FakeEventLogProbe(), new FakeSystemProbe())
            .RunAsync(TestContext.Create(TestContext.Domain(admin: true)), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.HealthDism).Status);
        Assert.Equal(DiagnosticStatus.Critical, ImageHealth.Map("NonRepairable").Status);
        Assert.Equal(DiagnosticStatus.Ok, ImageHealth.Map("Healthy").Status);
    }

    [Fact]
    public async Task Sfc_NonAdmin_IsSkippedWithElevatedAction()
    {
        var r = await new SfcModule(new FakeCommandRunner(), new FakeFileSystem(), new FakeSystemProbe()).RunAsync(TestContext.Create(), CancellationToken.None);
        var c = r.Get(C.HealthSfc);
        Assert.Equal(DiagnosticStatus.Skipped, c.Status);
        Assert.Contains(FirstAidAdmin.Core.ActionIds.SfcVerify, c.Remediation);
    }

    [Fact]
    public async Task Security_DefenderOff_FirewallOff_UacOff()
    {
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Get-MpComputerStatus"] = """{"defender":{"svc":true,"av":true,"rt":false,"age":20,"tamper":false},"av":[],"fw":[{"Name":"Domain","Enabled":true},{"Name":"Public","Enabled":false}]}""";
        var reg = new FakeRegistry().Set(RegistryHive.LocalMachine, @"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA", 0);
        var r = await new SecurityModule(ps, reg).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.SecDefender).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.SecSignatures).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.SecFirewall).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.SecUac).Status);
    }

    [Fact]
    public async Task Security_ThirdPartyAv_DefenderPassive_IsInfo()
    {
        var ps = new FakePowerShell();
        ps.JsonByScriptFragment["Get-MpComputerStatus"] = """{"defender":{"svc":true,"av":false,"rt":false,"age":1},"av":[{"displayName":"Kaspersky Endpoint Security"},{"displayName":"Windows Defender"}],"fw":[]}""";
        var r = await new SecurityModule(ps, new FakeRegistry()).RunAsync(TestContext.Create(), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Info, r.Get(C.SecDefender).Status);
        Assert.Equal("Kaspersky Endpoint Security", r.Get(C.SecAntivirus).GetEvidence("thirdParty"));
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.SecUac).Status);
    }

    [Fact]
    public async Task Services_CriticalStopped_AndTargetService()
    {
        var svc = FakeServiceProbe.Healthy().Add("Dnscache", ServiceState.Stopped, ServiceStartMode.Automatic).Add("MyAgent", ServiceState.Stopped, ServiceStartMode.Automatic, "My Corp Agent");
        var ctx = TestContext.Create(inputs: new() { [K.ServiceName] = "My Corp Agent" });
        var r = await new ServicesModule(svc).RunAsync(ctx, CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.ServicesCritical).Status);
        Assert.Contains("Dnscache", r.Get(C.ServicesCritical).Summary);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.ServicesTarget).Status);
        Assert.Contains(ServiceAnalyzer.AutoNotRunning(svc.GetAll()), s => s.Name == "MyAgent");
    }

    [Fact]
    public async Task Application_MissingExe_And_Crashes_NoLaunchWithoutPermission()
    {
        var fs = new FakeFileSystem();
        fs.Files.Add(@"C:\Program Files\App\app.exe");
        var ev = new FakeEventLogProbe().Add("Application", "Application Error", 1000, 2, "Faulting application name: app.exe, version 1.0\nFaulting module name: badplugin.dll, version: 2.0")
                                        .Add("Application", "Application Error", 1000, 2, "Faulting application name: app.exe\nFaulting module name: badplugin.dll,");
        var launcher = new FakeProcessLauncher();
        var ctx = TestContext.Create(inputs: new() { [K.AppName] = "App", [K.AppExe] = @"C:\Program Files\App\app.exe" });
        var r = await new ApplicationModule(fs, launcher, ev, FakeNetworkProbe.Healthy(), FakeServiceProbe.Healthy()).RunAsync(ctx, CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.AppFile).Status);
        Assert.Equal(DiagnosticStatus.Skipped, r.Get(C.AppLaunch).Status);
        Assert.Equal(0, launcher.Launches);
        var events = r.Get(C.AppEvents);
        Assert.Equal(DiagnosticStatus.Warning, events.Status);
        Assert.Equal("badplugin.dll", events.GetEvidence("faultingModule"));

        var missing = await new ApplicationModule(new FakeFileSystem(), launcher, ev, FakeNetworkProbe.Healthy(), FakeServiceProbe.Healthy())
            .RunAsync(TestContext.Create(inputs: new() { [K.AppExe] = @"C:\nope\x.exe" }), CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Error, missing.Get(C.AppFile).Status);
    }

    [Fact]
    public async Task Application_LaunchOnlyWhenAllowed()
    {
        var fs = new FakeFileSystem();
        fs.Files.Add(@"C:\App\tool.exe");
        var launcher = new FakeProcessLauncher { LaunchResult = (true, true, -1073741515, null) };
        var ctx = TestContext.Create(inputs: new() { [K.AppExe] = @"C:\App\tool.exe", [K.AppAllowLaunch] = "true" });
        var r = await new ApplicationModule(fs, launcher, new FakeEventLogProbe(), FakeNetworkProbe.Healthy(), FakeServiceProbe.Healthy()).RunAsync(ctx, CancellationToken.None);
        Assert.Equal(1, launcher.Launches);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.AppLaunch).Status);
        Assert.Contains("C0000135", r.Get(C.AppLaunch).Summary);
    }

    [Theory]
    [InlineData("\\\\srv01\\docs", "srv01", "docs")]
    [InlineData("//10.0.0.5/share/sub", "10.0.0.5", "share")]
    [InlineData("\\\\fs", "fs", null)]
    public void Share_ParseUnc(string path, string host, string? share)
    {
        var p = NetworkShareModule.ParseUnc(path);
        Assert.Equal(host, p!.Value.Host);
        Assert.Equal(share, p.Value.Share);
        Assert.Null(NetworkShareModule.ParseUnc("C:\\x"));
    }

    [Fact]
    public async Task Share_SmbClosed()
    {
        var net = FakeNetworkProbe.Healthy();
        net.TcpFails.Add("203.0.113.10:445");
        var ctx = TestContext.Create(inputs: new() { [K.SharePath] = "\\\\fs01\\docs" });
        var r = await new NetworkShareModule(net, new FakeFileSystem(), FakeServiceProbe.Healthy()).RunAsync(ctx, CancellationToken.None);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.ShareDns).Status);
        Assert.Equal(DiagnosticStatus.Ok, r.Get(C.SharePing).Status);
        Assert.Equal(DiagnosticStatus.Error, r.Get(C.ShareSmb).Status);
    }
}
