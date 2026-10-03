using System.IO.Compression;
using System.Text.Json;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Cases;
using FirstAidAdmin.Core.Engine;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Infrastructure.Windows;
using FirstAidAdmin.Remediation;
using FirstAidAdmin.Reporting;
using FirstAidAdmin.Tests.Fakes;
using A = FirstAidAdmin.Core.ActionIds;
using C = FirstAidAdmin.Core.CheckIds;

namespace FirstAidAdmin.Tests;

public class ReportGeneratorTests
{
    public static DiagnosticReport SampleReport()
    {
        var net = DiagnosticResult.Create("network", "Сеть", DiagnosticCategory.Network, DiagnosticStatus.Error, "Этап отказа: DNS");
        net.Checks.Add(DiagnosticResult.Create(C.NetGatewayPing, "Доступность шлюза", DiagnosticCategory.Network, DiagnosticStatus.Ok, "Шлюз 192.168.1.1 отвечает").WithEvidence("gateway", "192.168.1.1"));
        net.Checks.Add(DiagnosticResult.Create(C.NetDnsResolve, "Разрешение имён <script>", DiagnosticCategory.Network, DiagnosticStatus.Error, "www.microsoft.com не разрешается"));
        var disk = DiagnosticResult.Create("storage", "Диски", DiagnosticCategory.Storage, DiagnosticStatus.Warning, "Мало места");
        var ev = DiagnosticResult.Create("eventlog", "Анализ системных событий", DiagnosticCategory.EventLog, DiagnosticStatus.Error, "Ошибок: 4");
        return new DiagnosticReport
        {
            AppVersion = "2.0.0",
            System = new SystemSnapshot { MachineName = "PC-001", UserName = "ivanov", UserDomain = "CORP", DomainName = "corp.local", IsDomainJoined = true, OsDescription = "Windows 11" },
            Case = new SupportCase { Id = "20261003-0012", Problem = "Нет интернета", Computer = "PC-001", User = "CORP\\ivanov" },
            Results = { ev, disk, net },
            Findings =
            {
                new Finding { Id = "net.dns", Title = "Проблема DNS", Severity = Severity.High, Confidence = Confidence.High, WhatWasFound = "Интернет по IP работает", ProbableCause = "Некорректный DNS", Recommendation = "Проверить DNS", RemediationIds = { A.FlushDns } }
                    .Support("Интернет по IP работает").Against("DNS-запросы не проходят")
            },
            Summary = new ExecutiveSummary { OkCount = 23, WarningCount = 4, ProblemCount = 2, CriticalFindings = { "Ошибка DNS" }, Recommendations = { "Проверить DNS" } },
            RemediationHistory = { new RemediationRecord { ActionId = A.FlushDns, Title = "Очистить кэш DNS", Risk = RiskLevel.Low, Outcome = RemediationOutcome.Persists, StartedAt = DateTimeOffset.Now } },
            Timeline = { new TimelineEntry(DateTimeOffset.Now, "case", "Case created") }
        };
    }

    [Fact]
    public void Html_HasAllSectionsInRequiredOrder_AndExecutiveSummary()
    {
        var html = new HtmlReportGenerator().Generate(SampleReport());
        Assert.StartsWith("<!DOCTYPE html>", html);
        var order = new[] { "Общие сведения", "ИТОГ ДИАГНОСТИКИ", "<h2>Сеть</h2>", "<h2>Хранилище</h2>", "<h2>Журналы событий</h2>", "Находки (Findings)", "<h2>Рекомендации</h2>", "История исправлений" };
        var positions = order.Select(s => html.IndexOf(s, StringComparison.Ordinal)).ToList();
        Assert.All(positions, p => Assert.True(p >= 0));
        Assert.Equal(positions.OrderBy(p => p), positions);
        Assert.Contains("CASE #20261003-0012", html);
        Assert.Contains("PC-001", html);
        Assert.Contains("corp.local", html);
        Assert.Contains("<div class=\"num\">23</div>", html);
        Assert.Contains("Уверенность: <b>высокая</b>", html);
        Assert.Contains("✓ Интернет по IP работает", html);
        Assert.Contains("✗ DNS-запросы не проходят", html);
        Assert.Contains("Risk: LOW", html);
        Assert.Contains("Проблема сохраняется", html);
    }

    [Fact]
    public void Html_EncodesUntrustedText()
    {
        var html = new HtmlReportGenerator().Generate(SampleReport());
        Assert.DoesNotContain("<script>", html);
        Assert.Contains("&lt;script&gt;", html);
    }

    [Fact]
    public void Json_RoundTrips()
    {
        var json = new JsonReportGenerator().Generate(SampleReport());
        var back = JsonSerializer.Deserialize<DiagnosticReport>(json, JsonDefaults.Indented)!;
        Assert.Equal("20261003-0012", back.Case!.Id);
        Assert.Equal(3, back.Results.Count);
        Assert.Equal(DiagnosticStatus.Error, back.Results[2].Checks[1].Status);
        Assert.Contains("\"status\": \"Error\"", json);
    }

    [Fact]
    public async Task Pdf_IsPlanned()
    {
        var pdf = new PlannedPdfExporter();
        Assert.False(pdf.IsSupported);
        await Assert.ThrowsAsync<NotSupportedException>(() => pdf.ExportAsync(SampleReport(), "x.pdf", CancellationToken.None));
    }

    [Fact]
    public void Redactor_MasksUserHostDomainIpAndSecrets()
    {
        var s = new SecuritySettings { RedactUserNames = true, RedactHostNames = true, RedactDomain = true, RedactIpAddresses = true };
        var r = new Redactor(s, "ivanov", "PC-001", "corp.local", "CORP");
        var text = @"User CORP\ivanov on PC-001.corp.local path C:\Users\ivanov\Desktop ip 192.168.1.50 password=Secret123 token: abc Authorization: Bearer eyJhbGciOi version 10.0.26100.1";
        var x = r.Redact(text);
        Assert.Contains(@"DOMAIN\USER", x);
        Assert.Contains(@"C:\Users\USER\Desktop", x);
        Assert.DoesNotContain("ivanov", x);
        Assert.DoesNotContain("PC-001", x);
        Assert.Contains("HOST", x);
        Assert.Contains("192.168.x.x", x);
        Assert.DoesNotContain("Secret123", x);
        Assert.Contains("password=***", x);
        Assert.DoesNotContain("eyJhbGciOi", x);
        Assert.Contains("10.0.26100.1", x); // version strings are not IPs (26100 > 255)
    }

    [Fact]
    public void Redactor_DefaultSettings_MaskOnlyUserAndSecrets()
    {
        var r = new Redactor(new SecuritySettings(), "ivanov", "PC-001", "corp.local", "CORP");
        var x = r.Redact(@"CORP\ivanov PC-001 10.0.0.1 pwd=1");
        Assert.Equal(@"CORP\USER PC-001 10.0.0.1 pwd=***", x);
    }

    [Fact]
    public void Package_ContainsRequiredFiles_AndIsRedacted()
    {
        var folder = Path.Combine(Path.GetTempPath(), "faa-pkg-" + Guid.NewGuid().ToString("N"));
        try
        {
            var report = SampleReport();
            var redactor = new Redactor(new SecuritySettings { RedactHostNames = true }, "ivanov", "PC-001", "corp.local", "CORP");
            var zip = new DiagnosticPackageBuilder().Build(report, "[x] > ipconfig /all\n    user ivanov", folder, redactor, report.Case!.FileStem);
            Assert.EndsWith("Case-20261003-0012.zip", zip);
            using var archive = ZipFile.OpenRead(zip);
            var names = archive.Entries.Select(e => e.FullName).ToList();
            Assert.Equal(DiagnosticPackageBuilder.PackageFiles.OrderBy(x => x), names.OrderBy(x => x));
            foreach (var e in archive.Entries)
            {
                using var reader = new StreamReader(e.Open());
                var content = reader.ReadToEnd();
                Assert.DoesNotContain("ivanov", content);
                Assert.DoesNotContain("PC-001", content);
            }
            using var meta = new StreamReader(archive.GetEntry("metadata.json")!.Open());
            Assert.Contains("\"redaction\": \"applied\"", meta.ReadToEnd());
        }
        finally { try { Directory.Delete(folder, true); } catch { } }
    }

    [Fact]
    public void TextExports_ContainSections()
    {
        var r = SampleReport();
        Assert.Contains("SYSTEM INFORMATION", TextExports.System(r));
        Assert.Contains("Разрешение имён", TextExports.Network(r));
        Assert.Contains("EVENT LOG ERRORS", TextExports.EventErrors(r));
    }
}

public sealed class ScriptedConfirmation : IConfirmationService
{
    public bool Answer { get; set; } = true;
    public UserFeedback Feedback { get; set; } = UserFeedback.Yes;
    public List<string> Asked { get; } = new();
    public Task<bool> ConfirmAsync(RemediationAction action, string? parameter) { Asked.Add(action.Id); return Task.FromResult(Answer); }
    public Task<UserFeedback> AskFeedbackAsync(RemediationAction action, RemediationOutcome outcome) => Task.FromResult(Feedback);
}

public sealed class FakeElevation : IElevationService
{
    public bool IsElevated { get; set; }
    public bool IsHelperAvailable => true;
    public List<string> Requests { get; } = new();
    public OperationResult Result { get; set; } = OperationResult.Ok("done");
    public Task<OperationResult> RunElevatedAsync(string operationId, string? parameter, CancellationToken cancellationToken) { Requests.Add(operationId); return Task.FromResult(Result); }
}

public sealed class RecordingShell : IShellLauncher
{
    public List<string> Opened { get; } = new();
    public OperationResult Open(string target) { Opened.Add(target); return OperationResult.Ok("opened"); }
}

public class RemediationTests
{
    [Fact]
    public void Catalog_RiskLevels_FollowPolicy()
    {
        Assert.Equal(RiskLevel.Low, RemediationCatalog.Find(A.FlushDns)!.Risk);
        Assert.Equal(RiskLevel.Medium, RemediationCatalog.Find(A.RestartSpooler)!.Risk);
        Assert.Equal(RiskLevel.Medium, RemediationCatalog.Find(A.RenewIp)!.Risk);
        Assert.Equal(RiskLevel.Medium, RemediationCatalog.Find(A.ClearUserTemp)!.Risk);
        foreach (var high in new[] { A.ChkdskFix, A.ChkdskRepair, A.DismRestoreHealth, A.SfcScanNow, A.ResetWindowsUpdateCache, A.WinsockReset })
            Assert.Equal(RiskLevel.High, RemediationCatalog.Find(high)!.Risk);
        Assert.All(RemediationCatalog.All.Where(a => a.Kind == RemediationKind.OpenTool), a => Assert.Equal(RiskLevel.Low, a.Risk));
    }

    [Fact]
    public void Catalog_CoversEveryActionId_AndHasNoDuplicates()
    {
        var ids = typeof(ActionIds).GetFields().Select(f => (string)f.GetValue(null)!).ToList();
        foreach (var id in ids) Assert.NotNull(RemediationCatalog.Find(id));
        Assert.Equal(RemediationCatalog.All.Count, RemediationCatalog.All.Select(a => a.Id).Distinct().Count());
        Assert.All(RemediationCatalog.All, a => Assert.False(string.IsNullOrWhiteSpace(a.WhatChanges)));
    }

    [Fact]
    public void ValidateParameter_EnforcesAllowList()
    {
        var restart = RemediationCatalog.Find(A.RestartService)!;
        Assert.Null(OperationExecutor.ValidateParameter(restart, "Spooler"));
        Assert.NotNull(OperationExecutor.ValidateParameter(restart, "WinDefend"));
        Assert.NotNull(OperationExecutor.ValidateParameter(restart, null));
        var chk = RemediationCatalog.Find(A.ChkdskScan)!;
        Assert.Null(OperationExecutor.ValidateParameter(chk, "D:"));
        Assert.NotNull(OperationExecutor.ValidateParameter(chk, "C:\\ & del"));
    }

    [Fact]
    public async Task Executor_RejectsUnknownOperation_AndRunsKnownCommand()
    {
        var cmd = new FakeCommandRunner();
        cmd.Set("ipconfig /flushdns", "Successfully flushed the DNS Resolver Cache.");
        var ex = new OperationExecutor(cmd, new FakePowerShell(), new RecordingShell());
        Assert.False((await ex.ExecuteAsync("format-c", null, CancellationToken.None)).Success);
        var ok = await ex.ExecuteAsync(A.FlushDns, null, CancellationToken.None);
        Assert.True(ok.Success);
        Assert.Contains("ipconfig /flushdns", cmd.Calls);
        var svc = await ex.ExecuteAsync(A.RestartService, "Spooler'; Remove-Item C:\\ -Recurse; '", CancellationToken.None);
        Assert.False(svc.Success); // not in allow-list => never reaches PowerShell
    }

    [Fact]
    public void TempCleaner_DeletesOnlyOldFiles()
    {
        var dir = Path.Combine(Path.GetTempPath(), "faa-temp-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            var oldF = Path.Combine(dir, "old.tmp");
            var newF = Path.Combine(dir, "new.tmp");
            File.WriteAllText(oldF, "x");
            File.WriteAllText(newF, "y");
            File.SetLastWriteTimeUtc(oldF, DateTime.UtcNow.AddDays(-30));
            var r = TempCleaner.Clean(dir, TimeSpan.FromDays(7), DateTimeOffset.UtcNow);
            Assert.True(r.Success);
            Assert.False(File.Exists(oldF));
            Assert.True(File.Exists(newF));
        }
        finally { Directory.Delete(dir, true); }
    }

    private static (RemediationEngine Engine, FakeCommandRunner Cmd, FakeNetworkProbe Net, ScriptedConfirmation Confirm, FakeElevation Elev) Build(bool elevated = false)
    {
        var cmd = new FakeCommandRunner();
        cmd.Set("ipconfig /flushdns", "ok");
        var net = FakeNetworkProbe.Healthy();
        var runner = new DiagnosticRunner(new IDiagnosticModule[]
        {
            new FirstAidAdmin.Diagnostics.Dns.DnsModule(net, FakeServiceProbe.Healthy(), new FakePowerShell()),
            new FirstAidAdmin.Diagnostics.Network.NetworkModule(net, cmd)
        });
        var confirm = new ScriptedConfirmation();
        var elev = new FakeElevation { IsElevated = elevated };
        var engine = new RemediationEngine(new OperationExecutor(cmd, new FakePowerShell(), new RecordingShell()), elev, confirm, runner);
        return (engine, cmd, net, confirm, elev);
    }

    [Fact]
    public async Task Engine_NeverExecutesWithoutConfirmation()
    {
        var (engine, cmd, _, confirm, _) = Build();
        confirm.Answer = false;
        var run = await engine.ExecuteAsync(A.FlushDns, null, TestContext.Create(), CancellationToken.None);
        Assert.Equal(RemediationOutcome.Cancelled, run.Record.Outcome);
        Assert.False(run.Record.Confirmed);
        Assert.DoesNotContain(cmd.Calls, c => c.StartsWith("ipconfig"));
    }

    [Fact]
    public async Task Engine_ConfirmedFix_IsRetested_Resolved()
    {
        var (engine, cmd, _, confirm, _) = Build();
        var run = await engine.ExecuteAsync(A.FlushDns, null, TestContext.Create(), CancellationToken.None);
        Assert.Contains(A.FlushDns, confirm.Asked);
        Assert.Contains("ipconfig /flushdns", cmd.Calls);
        Assert.Equal(RemediationOutcome.Resolved, run.Record.Outcome);
        Assert.NotEmpty(run.RetestResults);
        Assert.NotEmpty(run.Record.RetestSummary);
        Assert.Equal(UserFeedback.Yes, run.Record.Feedback);
    }

    [Fact]
    public async Task Engine_ConfirmedFix_ProblemPersists()
    {
        var (engine, _, net, _, _) = Build();
        net.AllDnsFail = true;
        var run = await engine.ExecuteAsync(A.FlushDns, null, TestContext.Create(), CancellationToken.None);
        Assert.Equal(RemediationOutcome.Persists, run.Record.Outcome);
    }

    [Fact]
    public async Task Engine_AdminAction_GoesThroughUac_WhenNotElevated()
    {
        var (engine, cmd, _, _, elev) = Build(elevated: false);
        var run = await engine.ExecuteAsync(A.RestartSpooler, null, TestContext.Create(), CancellationToken.None);
        Assert.Contains(A.RestartSpooler, elev.Requests);
        Assert.True(run.Record.Elevated);
        Assert.Empty(cmd.Calls.Where(c => c.Contains("Spooler")));
    }

    [Fact]
    public async Task Engine_UacCancelled_IsFailed()
    {
        var (engine, _, _, _, elev) = Build();
        elev.Result = OperationResult.Fail("Отменено пользователем в окне UAC");
        var run = await engine.ExecuteAsync(A.RenewIp, null, TestContext.Create(), CancellationToken.None);
        Assert.Equal(RemediationOutcome.Failed, run.Record.Outcome);
        Assert.Contains("UAC", run.Record.Error);
    }

    [Fact]
    public async Task Engine_OpenTool_NeedsNoConfirmation()
    {
        var cmd = new FakeCommandRunner();
        var shell = new RecordingShell();
        var confirm = new ScriptedConfirmation { Answer = false };
        var engine = new RemediationEngine(new OperationExecutor(cmd, new FakePowerShell(), shell), new FakeElevation(), confirm, new DiagnosticRunner(Array.Empty<IDiagnosticModule>()));
        var run = await engine.ExecuteAsync(A.OpenServices, null, TestContext.Create(), CancellationToken.None);
        Assert.Empty(confirm.Asked);
        Assert.Equal("services.msc", Assert.Single(shell.Opened));
        Assert.Equal(RemediationOutcome.Unknown, run.Record.Outcome);
    }

    [Fact]
    public async Task Engine_InvalidParameter_FailsBeforeConfirmation()
    {
        var (engine, _, _, confirm, _) = Build();
        var run = await engine.ExecuteAsync(A.RestartService, "NotAllowed", TestContext.Create(), CancellationToken.None);
        Assert.Equal(RemediationOutcome.Failed, run.Record.Outcome);
        Assert.Empty(confirm.Asked);
    }
}

public class AdminDetectionTests
{
    [Fact]
    public void AdminDetector_ReturnsProcessPrivilege()
    {
        var elevated = AdminDetector.IsElevated();
        if (!OperatingSystem.IsWindows()) Assert.Equal(Environment.IsPrivilegedProcess, elevated);
    }

    [Fact]
    public async Task UacService_RefusesUnknownOperations_AndReportsMissingHelper()
    {
        var executor = new OperationExecutor(new FakeCommandRunner(), new FakePowerShell(), new RecordingShell());
        var svc = new UacElevationService(executor, "/nonexistent/FirstAidAdmin.Helper.exe");
        Assert.False(svc.IsHelperAvailable);
        var r = await svc.RunElevatedAsync("rm-rf", null, CancellationToken.None);
        Assert.False(r.Success);
        Assert.Contains("не входит", r.Error);
    }

    [Fact]
    public void SystemSnapshot_IsFast_AndPopulated()
    {
        var sw = System.Diagnostics.Stopwatch.StartNew();
        var s = new SystemProbe().GetSnapshot();
        sw.Stop();
        Assert.False(string.IsNullOrEmpty(s.MachineName));
        Assert.False(string.IsNullOrEmpty(s.UserName));
        Assert.True(sw.Elapsed < TimeSpan.FromSeconds(5), $"Startup snapshot took {sw.Elapsed}");
    }
}

public class CaseTests
{
    [Fact]
    public void CaseIds_AreDateBased_AndSequential()
    {
        var dir = Path.Combine(Path.GetTempPath(), "faa-cases-" + Guid.NewGuid().ToString("N"));
        try
        {
            var store = new FileCaseStore(dir, () => new DateTimeOffset(2026, 10, 3, 19, 31, 0, TimeSpan.FromHours(3)));
            var a = store.Create("Нет интернета", ProblemScenario.NoInternet, "PC-001", "CORP\\User");
            var b = store.Create("Принтер", ProblemScenario.Printer, "PC-001", "CORP\\User");
            Assert.Equal("20261003-0001", a.Id);
            Assert.Equal("20261003-0002", b.Id);
            Assert.Equal("CASE #20261003-0001", a.DisplayId);
            Assert.Equal("Case-20261003-0001", a.FileStem);
            Assert.Equal("Case created", a.Timeline.Single().Message);

            a.Timeline.Add(new TimelineEntry(DateTimeOffset.Now, "check", "Gateway OK"));
            store.Save(a);
            var loaded = store.Load(a.Id)!;
            Assert.Equal(2, loaded.Timeline.Count);
            Assert.Equal("Нет интернета", loaded.Problem);
            Assert.Equal(2, store.List().Count);
            Assert.Null(store.Load("19990101-0001"));
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    [Fact]
    public void Settings_RoundTrip_TelemetryAlwaysOff()
    {
        var path = Path.Combine(Path.GetTempPath(), "faa-settings-" + Guid.NewGuid().ToString("N") + ".json");
        try
        {
            var store = new JsonSettingsStore(path);
            var s = store.Load();
            Assert.False(s.Telemetry);
            Assert.False(s.Ai.Enabled);
            s.Diagnostics.PingCount = 7;
            s.General.Theme = AppTheme.Dark;
            s.Telemetry = true;
            store.Save(s);
            var back = store.Load();
            Assert.Equal(7, back.Diagnostics.PingCount);
            Assert.Equal(AppTheme.Dark, back.General.Theme);
            Assert.False(back.Telemetry);
            File.WriteAllText(path, "{ corrupt");
            Assert.NotNull(store.Load());
        }
        finally { File.Delete(path); }
    }
}
