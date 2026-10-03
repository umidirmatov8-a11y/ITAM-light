using FirstAidAdmin.Application.Cli;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Analysis;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Plugins;
using FirstAidAdmin.Core.Scenarios;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Remediation;
using FirstAidAdmin.Tests.Fakes;

namespace FirstAidAdmin.Tests;

public class KnowledgeBaseTests
{
    [Fact]
    public void EmbeddedKnowledgeBase_Loads()
    {
        var kb = KnowledgeBaseService.LoadDefault("/nonexistent");
        Assert.Empty(kb.LoadErrors);
        Assert.True(kb.Entries.Count >= 40);
        var dns = kb.Find("net.dns")!;
        Assert.NotEmpty(dns.Symptoms);
        Assert.NotEmpty(dns.PossibleCauses);
        Assert.NotEmpty(dns.Recommendations);
        Assert.Equal(RiskLevel.Low, dns.Risk);
    }

    [Fact]
    public void EveryCorrelationRule_HasKnowledgeBaseEntry()
    {
        var kb = KnowledgeBaseService.LoadDefault("/nonexistent");
        var missing = CorrelationRules.All().Select(r => r.Id).Where(id => kb.Find(id) is null).ToList();
        Assert.Empty(missing);
    }

    [Fact]
    public void KnowledgeBaseRemediation_ReferencesCatalog()
    {
        var kb = KnowledgeBaseService.LoadDefault("/nonexistent");
        var unknown = kb.Entries.SelectMany(e => e.Remediation).Where(id => RemediationCatalog.Find(id) is null).Distinct().ToList();
        Assert.Empty(unknown);
    }

    [Fact]
    public void ExternalFolder_OverridesEmbedded_AndReportsErrors()
    {
        var dir = Path.Combine(Path.GetTempPath(), "faa-kb-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            File.WriteAllText(Path.Combine(dir, "custom.json"), """[{"id":"net.dns","problem":"Локальная версия","risk":"Medium"}]""");
            File.WriteAllText(Path.Combine(dir, "broken.json"), "{ nope");
            var kb = KnowledgeBaseService.LoadDefault(dir);
            Assert.Equal("Локальная версия", kb.Find("net.dns")!.Problem);
            Assert.Single(kb.LoadErrors);
            Assert.NotEmpty(kb.Search("DNS"));
        }
        finally { Directory.Delete(dir, true); }
    }
}

public class ScenarioTests
{
    [Fact]
    public void AllScenarioModules_AreRegistered()
    {
        using var host = new TestHost();
        var ids = host.Session.Runner.Modules.Select(m => m.Id).ToHashSet();
        foreach (var s in ScenarioCatalog.All)
            foreach (var m in s.Modules)
                Assert.Contains(m, ids);
        Assert.Equal(Enum.GetValues<ProblemScenario>().Length, ScenarioCatalog.All.Count);
    }

    [Fact]
    public void FullDiagnostics_ExcludesLongRunningModules()
    {
        var full = ScenarioCatalog.Get(ProblemScenario.FullDiagnostics);
        Assert.DoesNotContain(ModuleIds.Sfc, full.Modules);
        Assert.DoesNotContain(ModuleIds.DismScan, full.Modules);
    }

    [Theory]
    [InlineData("/diagnose", ProblemScenario.FullDiagnostics)]
    [InlineData("/network", ProblemScenario.NoInternet)]
    [InlineData("-dns", ProblemScenario.Dns)]
    [InlineData("rdp", ProblemScenario.Rdp)]
    [InlineData("FirstResponse", ProblemScenario.FirstResponse)]
    public void Parse_Tokens(string token, ProblemScenario expected) => Assert.Equal(expected, ScenarioCatalog.Parse(token));

    [Fact]
    public void HelpDeskScenarios_MatchSimpleMode()
    {
        var helpdesk = ScenarioCatalog.All.Where(s => s.HelpDesk).Select(s => s.Scenario).ToList();
        foreach (var s in new[] { ProblemScenario.NoInternet, ProblemScenario.SlowComputer, ProblemScenario.ApplicationNotWorking, ProblemScenario.CannotLogin, ProblemScenario.Printer, ProblemScenario.Rdp, ProblemScenario.FullDiagnostics })
            Assert.Contains(s, helpdesk);
    }
}

public class CliTests
{
    [Fact]
    public void Parse_CommonCommands()
    {
        Assert.Equal(ProblemScenario.FullDiagnostics, CliRunner.Parse(new[] { "/diagnose" }).Scenario);
        Assert.Equal(ProblemScenario.NoInternet, CliRunner.Parse(new[] { "/network" }).Scenario);
        var report = CliRunner.Parse(new[] { "/report" });
        Assert.True(report.Report);
        Assert.Equal(ProblemScenario.FullDiagnostics, report.Scenario);
        var c = CliRunner.Parse(new[] { "/case", "Нет интернета" });
        Assert.True(c.CreateCase);
        Assert.Equal("Нет интернета", c.CaseProblem);
        Assert.Equal(ProblemScenario.FirstResponse, c.Scenario);
        var rdp = CliRunner.Parse(new[] { "/rdp:192.168.1.10", "/port:3390" });
        Assert.Equal("192.168.1.10", rdp.Inputs[InputKeys.RdpTarget]);
        Assert.Equal("3390", rdp.Inputs[InputKeys.RdpPort]);
        var share = CliRunner.Parse(new[] { "/share:\\\\srv\\docs" });
        Assert.Equal(ProblemScenario.NetworkShare, share.Scenario);
        Assert.Single(CliRunner.Parse(new[] { "/bogus" }).Errors);
        Assert.Contains(ModuleIds.Sfc, CliRunner.Parse(new[] { "/sfc" }).ExtraModules);
    }

    [Fact]
    public void IsCliInvocation_DetectsSwitches()
    {
        Assert.True(CliRunner.IsCliInvocation(new[] { "/diagnose" }));
        Assert.True(CliRunner.IsCliInvocation(new[] { "--report" }));
        Assert.False(CliRunner.IsCliInvocation(Array.Empty<string>()));
        Assert.False(CliRunner.IsCliInvocation(new[] { "somefile.txt" }));
    }

    [Fact]
    public async Task Help_And_Usage()
    {
        using var host = new TestHost();
        var sw = new StringWriter();
        Assert.Equal(CliRunner.ExitOk, await new CliRunner(host.Session, sw).RunAsync(new[] { "/help" }, CancellationToken.None));
        Assert.Contains("/diagnose", sw.ToString());
        Assert.Equal(CliRunner.ExitUsage, await new CliRunner(host.Session, new StringWriter()).RunAsync(new[] { "/nope" }, CancellationToken.None));
    }

    [Fact]
    public async Task Network_Healthy_ReturnsNoProblems()
    {
        using var host = new TestHost();
        var sw = new StringWriter();
        var code = await new CliRunner(host.Session, sw).RunAsync(new[] { "/dns" }, CancellationToken.None);
        Assert.True(code is CliRunner.ExitOk or CliRunner.ExitWarnings, sw.ToString());
        Assert.Contains("ИТОГ ДИАГНОСТИКИ", sw.ToString());
    }

    [Fact]
    public async Task Network_DnsBroken_ReturnsProblems_AndPrintsFinding()
    {
        var net = FakeNetworkProbe.Healthy();
        net.AllDnsFail = true;
        using var host = new TestHost { Network = net };
        var sw = new StringWriter();
        var code = await new CliRunner(host.Session, sw).RunAsync(new[] { "/network" }, CancellationToken.None);
        Assert.Equal(CliRunner.ExitProblems, code);
        var text = sw.ToString();
        Assert.True(text.Contains("Проблема DNS"), text);
        Assert.True(text.Contains("✓ Интернет по IP работает"), text);
    }

    [Fact]
    public async Task Case_CreatesReportAndZip()
    {
        using var host = new TestHost();
        var outDir = Path.Combine(host.DataFolder, "out");
        var sw = new StringWriter();
        await new CliRunner(host.Session, sw).RunAsync(new[] { "/case:Нет интернета", "/network", $"/out:{outDir}" }, CancellationToken.None);
        var text = sw.ToString();
        Assert.Contains("CASE #", text);
        Assert.True(File.Exists(Path.Combine(outDir, "report.html")), text);
        Assert.True(File.Exists(Path.Combine(outDir, "report.json")));
        Assert.Single(Directory.GetFiles(outDir, "Case-*.zip"));
        var c = host.Session.CurrentCase!;
        Assert.Contains(c.Timeline, t => t.Message == "Case created");
        Assert.Contains(c.Timeline, t => t.Message.Contains("Case exported"));
    }

    [Fact]
    public async Task Json_IsValid()
    {
        using var host = new TestHost();
        var sw = new StringWriter();
        await new CliRunner(host.Session, sw).RunAsync(new[] { "/dns", "/json" }, CancellationToken.None);
        using var doc = System.Text.Json.JsonDocument.Parse(sw.ToString());
        Assert.True(doc.RootElement.TryGetProperty("results", out _));
    }

    [Fact]
    public async Task Cli_NeverRemediates()
    {
        var c = new NonInteractiveConfirmationService();
        Assert.False(await c.ConfirmAsync(RemediationCatalog.Find(ActionIds.FlushDns)!, null));
    }
}

[DiagnosticPlugin]
public sealed class SamplePluginModule : IDiagnosticModule
{
    public string Id => "sample.plugin";
    public string Name => "Sample plugin";
    public Task<DiagnosticResult> RunAsync(DiagnosticContext context, CancellationToken cancellationToken)
        => Task.FromResult(DiagnosticResult.Create(Id, Name, DiagnosticCategory.System, DiagnosticStatus.Ok, "plugin works"));
}

public class PluginAndAnalysisTests
{
    [Fact]
    public void PluginLoader_FindsOnlyMarkedModules()
    {
        var modules = PluginLoader.CreateModules(typeof(SamplePluginModule).Assembly).ToList();
        Assert.Single(modules, m => m.Id == "sample.plugin");
    }

    [Fact]
    public void PluginLoader_MissingFolder_IsEmpty() => Assert.Empty(new PluginLoader().LoadFrom("/no/such/plugins"));

    [Fact]
    public void PluginLoader_BadDll_IsReportedNotThrown()
    {
        var dir = Path.Combine(Path.GetTempPath(), "faa-plg-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            File.WriteAllText(Path.Combine(dir, "bad.dll"), "not a dll");
            var loader = new PluginLoader();
            Assert.Empty(loader.LoadFrom(dir));
            Assert.NotNull(loader.Reports.Single().Error);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public async Task LocalRuleEngine_IsDefault_OptionalAiIsOffline()
    {
        var report = ReportGeneratorTests.SampleReport();
        var local = new LocalRuleEngine(new CorrelationEngine());
        Assert.True(local.IsAvailable);
        var result = await local.AnalyzeAsync(report);
        Assert.Equal("LocalRuleEngine", result.Provider);
        var ai = new OptionalAIProvider(new AppSettings());
        Assert.False(ai.IsAvailable);
        Assert.Empty((await ai.AnalyzeAsync(report)).Findings);
    }

    [Fact]
    public async Task Runner_IsolatesModuleExceptions()
    {
        var runner = new FirstAidAdmin.Core.Engine.DiagnosticRunner(new IDiagnosticModule[] { new ThrowingModule(), new SamplePluginModule() });
        var results = await runner.RunAsync(new[] { "throws", "sample.plugin", "missing" }, TestContext.Create(), CancellationToken.None);
        Assert.Equal(2, results.Count);
        Assert.Equal(DiagnosticStatus.Warning, results[0].Status);
        Assert.Contains("исключением", results[0].Summary);
        Assert.Equal(DiagnosticStatus.Ok, results[1].Status);
    }

    [Fact]
    public async Task Runner_RespectsCancellation_AndDisabledModules()
    {
        var runner = new FirstAidAdmin.Core.Engine.DiagnosticRunner(new IDiagnosticModule[] { new SamplePluginModule() });
        var settings = new AppSettings();
        settings.Diagnostics.DisabledModules.Add("sample.plugin");
        Assert.Empty(await runner.RunAsync(new[] { "sample.plugin" }, TestContext.Create(settings: settings), CancellationToken.None));
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => runner.RunAsync(new[] { "sample.plugin" }, TestContext.Create(), cts.Token));
    }

    private sealed class ThrowingModule : IDiagnosticModule
    {
        public string Id => "throws";
        public string Name => "Throws";
        public Task<DiagnosticResult> RunAsync(DiagnosticContext context, CancellationToken cancellationToken) => throw new InvalidOperationException("boom");
    }
}

public class CompositionTests
{
    [Fact]
    public void DiCorrelationEngine_HasBuiltInRules()
    {
        using var host = new TestHost();
        Assert.Equal(CorrelationRules.All().Count, host.Get<CorrelationEngine>().Rules.Count);
    }
}
