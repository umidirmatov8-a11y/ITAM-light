using System.IO.Compression;
using FirstAidAdmin.Application;
using FirstAidAdmin.Application.Cli;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Cases;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Remediation;
using FirstAidAdmin.Tests.Fakes;
using Microsoft.Extensions.DependencyInjection;
using C = FirstAidAdmin.Core.CheckIds;

namespace FirstAidAdmin.IntegrationTests;

internal sealed class AlwaysYes : IConfirmationService
{
    public List<string> Confirmed { get; } = new();
    public Task<bool> ConfirmAsync(RemediationAction action, string? parameter) { Confirmed.Add(action.Id); return Task.FromResult(true); }
    public Task<UserFeedback> AskFeedbackAsync(RemediationAction action, RemediationOutcome outcome)
        => Task.FromResult(outcome == RemediationOutcome.Resolved ? UserFeedback.Yes : UserFeedback.No);
}

internal sealed class FlakyDnsFixedByFlush : ICommandRunner
{
    private readonly FakeNetworkProbe _net;
    public List<string> Calls { get; } = new();
    public FlakyDnsFixedByFlush(FakeNetworkProbe net) => _net = net;
    public Task<CommandResult> RunAsync(string fileName, string arguments, TimeSpan timeout, CancellationToken cancellationToken, OutputEncoding encoding = OutputEncoding.Oem)
    {
        var cmd = $"{fileName} {arguments}";
        Calls.Add(cmd);
        if (cmd == "ipconfig /flushdns") _net.AllDnsFail = false; // simulated: stale cache was the cause
        return Task.FromResult(cmd.StartsWith("ipconfig")
            ? new CommandResult(cmd, 0, "Successfully flushed the DNS Resolver Cache.", "", TimeSpan.FromMilliseconds(3))
            : CommandResult.NotStarted(cmd, "n/a"));
    }
}

/// <summary>End-to-end workflow with the real DI graph: problem → diagnostics → correlation → remediation → re-test → case → report.</summary>
public class WorkflowTests
{
    [Fact]
    public async Task NoInternet_Workflow_DnsFix_Retest_Resolved_AndDocumented()
    {
        var net = FakeNetworkProbe.Healthy();
        net.AllDnsFail = true;
        var yes = new AlwaysYes();
        var services = new ServiceCollection();
        var cmd = new FlakyDnsFixedByFlush(net);
        var data = Path.Combine(Path.GetTempPath(), "faa-it-" + Guid.NewGuid().ToString("N"));
        try
        {
            var settings = new AppSettings();
            settings.Reports.ReportFolder = Path.Combine(data, "Reports");
            services.AddSingleton<INetworkProbe>(net);
            services.AddSingleton<ICommandRunner>(cmd);
            services.AddSingleton<IPowerShellRunner>(new FakePowerShell());
            services.AddSingleton<IServiceProbe>(FakeServiceProbe.Healthy());
            services.AddSingleton<IEventLogProbe>(new FakeEventLogProbe());
            services.AddSingleton<IRegistryProbe>(new FakeRegistry());
            services.AddSingleton<ISystemProbe>(new FakeSystemProbe());
            services.AddSingleton<IFileSystemProbe>(new FakeFileSystem());
            services.AddSingleton<IProcessLauncher>(new FakeProcessLauncher());
            services.AddSingleton<ICaseStore>(new FileCaseStore(Path.Combine(data, "Cases")));
            services.AddSingleton<IConfirmationService>(yes);
            services.AddFirstAidAdmin(settings, Path.Combine(data, "Logs"));
            await using var sp = services.BuildServiceProvider();
            var session = sp.GetRequiredService<DiagnosticSession>();

            // 1. Case
            var c = session.CreateCase("Нет интернета", ProblemScenario.NoInternet);
            Assert.Matches(@"^\d{8}-\d{4}$", c.Id);

            // 2. Diagnostics + correlation
            await session.RunScenarioAsync(ProblemScenario.NoInternet, null, null, CancellationToken.None);
            var dns = Assert.Single(session.Findings, f => f.Id == "net.dns");
            Assert.Equal(Confidence.High, dns.Confidence);
            Assert.Contains(ActionIds.FlushDns, dns.RemediationIds);

            // 3. Remediation (confirmed) + automatic re-test
            var run = await session.RemediateAsync(ActionIds.FlushDns, null, CancellationToken.None);
            Assert.Contains(ActionIds.FlushDns, yes.Confirmed);
            Assert.Contains("ipconfig /flushdns", cmd.Calls);
            Assert.Equal(RemediationOutcome.Resolved, run.Record.Outcome);
            Assert.Equal(UserFeedback.Yes, run.Record.Feedback);
            Assert.DoesNotContain(session.Findings, f => f.Id == "net.dns"); // findings recomputed from re-test

            // 4. Timeline tells the story in order
            var msgs = session.Timeline.Select(t => t.Message).ToList();
            Assert.Equal("Case created", msgs[0]);
            Assert.Contains(msgs, m => m.Contains("Сеть: диагностика начата"));
            Assert.Contains(msgs, m => m.Contains("Доступность шлюза (ping) OK"));
            Assert.Contains(msgs, m => m.Contains("FAILED"));
            Assert.Contains(msgs, m => m.Contains("Проблема устранена"));
            Assert.True(msgs.FindIndex(m => m.Contains("FAILED")) < msgs.FindIndex(m => m.Contains("Проблема устранена")));

            // 5. Report + package, and the case on disk has everything
            var files = await session.ExportReportAsync();
            var html = await File.ReadAllTextAsync(files.First(f => f.EndsWith(".html")));
            Assert.Contains("История исправлений", html);
            Assert.Contains("Очистить кэш DNS", html);
            var zip = await session.BuildPackageAsync();
            using (var archive = ZipFile.OpenRead(zip))
                Assert.Contains(archive.Entries, e => e.FullName == "commands.log");
            var stored = sp.GetRequiredService<ICaseStore>().Load(c.Id)!;
            Assert.Single(stored.RemediationHistory);
            Assert.Contains(stored.Timeline, t => t.Message.Contains("Case exported"));
        }
        finally { try { Directory.Delete(data, true); } catch { } }
    }

    [Fact]
    public async Task FullDiagnostics_WithFakes_RunsEveryModule_WithoutExceptions()
    {
        using var host = new TestHost();
        var results = await host.Session.RunScenarioAsync(ProblemScenario.FullDiagnostics, null, null, CancellationToken.None);
        var expected = Core.Scenarios.ScenarioCatalog.Get(ProblemScenario.FullDiagnostics).Modules;
        Assert.Equal(expected.Count, results.Count);
        Assert.DoesNotContain(results, r => r.Summary.Contains("исключением"));
        var report = await host.Session.BuildReportAsync();
        Assert.True(report.Summary.OkCount > 10);
    }

    [Fact]
    public async Task Rdp_Target_EndToEnd()
    {
        var net = FakeNetworkProbe.Healthy();
        net.TcpFails.Add("10.0.0.99:3389");
        using var host = new TestHost { Network = net };
        await host.Session.RunScenarioAsync(ProblemScenario.Rdp, new Dictionary<string, string> { [InputKeys.RdpTarget] = "10.0.0.99" }, null, CancellationToken.None);
        var f = Assert.Single(host.Session.Findings, x => x.Id == "rdp.target");
        Assert.Equal(Confidence.High, f.Confidence); // ping works, port closed
    }

    [Fact]
    public async Task Cancellation_StopsTheRun()
    {
        using var host = new TestHost();
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => host.Session.RunScenarioAsync(ProblemScenario.FullDiagnostics, null, null, cts.Token));
    }

    [Fact]
    public async Task Cli_Report_WritesFiles()
    {
        using var host = new TestHost();
        var outDir = Path.Combine(host.DataFolder, "cli");
        var sw = new StringWriter();
        var code = await new CliRunner(host.Session, sw).RunAsync(new[] { "/report", $"/out:{outDir}" }, CancellationToken.None);
        Assert.True(code is CliRunner.ExitOk or CliRunner.ExitWarnings or CliRunner.ExitProblems, sw.ToString());
        Assert.True(File.Exists(Path.Combine(outDir, "report.html")));
        Assert.True(File.Exists(Path.Combine(outDir, "report.json")));
    }
}

/// <summary>Runs the real probes of the current OS (Linux in local CI, Windows in the Windows CI job).</summary>
public class RealSystemTests
{
    private static ServiceProvider Build(string data)
    {
        var services = new ServiceCollection();
        var settings = new AppSettings();
        settings.Reports.ReportFolder = Path.Combine(data, "Reports");
        settings.Diagnostics.PingCount = 1;
        services.AddSingleton<ICaseStore>(new FileCaseStore(Path.Combine(data, "Cases")));
        services.AddSingleton<IConfirmationService>(new NonInteractiveConfirmationService());
        services.AddFirstAidAdmin(settings, Path.Combine(data, "Logs"));
        return services.BuildServiceProvider();
    }

    [Fact]
    public async Task FirstResponse_OnRealSystem_CompletesWithoutModuleCrashes()
    {
        var data = Path.Combine(Path.GetTempPath(), "faa-real-" + Guid.NewGuid().ToString("N"));
        try
        {
            await using var sp = Build(data);
            var session = sp.GetRequiredService<DiagnosticSession>();
            var sys = session.RefreshSystem();
            Assert.False(string.IsNullOrEmpty(sys.MachineName));
            var sw = System.Diagnostics.Stopwatch.StartNew();
            var results = await session.RunScenarioAsync(ProblemScenario.FirstResponse, null, null, CancellationToken.None);
            sw.Stop();
            Assert.NotEmpty(results);
            Assert.DoesNotContain(results, r => r.Summary.Contains("исключением"));
            Assert.True(sw.Elapsed < TimeSpan.FromMinutes(3), $"First response took {sw.Elapsed}");
            var files = await session.ExportReportAsync();
            Assert.All(files, f => Assert.True(new FileInfo(f).Length > 1000));
        }
        finally { try { Directory.Delete(data, true); } catch { } }
    }

    [Fact]
    public async Task EveryScenario_OnRealSystem_DoesNotThrow()
    {
        var data = Path.Combine(Path.GetTempPath(), "faa-real2-" + Guid.NewGuid().ToString("N"));
        try
        {
            await using var sp = Build(data);
            var session = sp.GetRequiredService<DiagnosticSession>();
            var inputs = new Dictionary<string, string>
            {
                [InputKeys.RdpTarget] = "127.0.0.1", [InputKeys.AppName] = "notepad", [InputKeys.SharePath] = @"\\localhost\C$", [InputKeys.ServiceName] = "Spooler"
            };
            foreach (var s in new[] { ProblemScenario.Domain, ProblemScenario.Rdp, ProblemScenario.Printer, ProblemScenario.WindowsUpdate, ProblemScenario.WindowsErrors,
                                      ProblemScenario.WiFi, ProblemScenario.Security, ProblemScenario.ApplicationNotWorking, ProblemScenario.NetworkShare, ProblemScenario.ServiceNotWorking })
            {
                var r = await session.RunScenarioAsync(s, inputs, null, CancellationToken.None);
                Assert.DoesNotContain(r, x => x.Summary.Contains("исключением"));
            }
            Assert.NotNull(await session.BuildReportAsync());
        }
        finally { try { Directory.Delete(data, true); } catch { } }
    }

    [Fact]
    public async Task OperationExecutor_ReadOnlyDnsFlush_OnWindowsOnly()
    {
        if (!OperatingSystem.IsWindows()) return; // ipconfig exists only on Windows
        await using var sp = Build(Path.Combine(Path.GetTempPath(), "faa-real3-" + Guid.NewGuid().ToString("N")));
        var r = await sp.GetRequiredService<IOperationExecutor>().ExecuteAsync(ActionIds.FlushDns, null, CancellationToken.None);
        Assert.True(r.Success, r.Error + r.Output);
    }
}
