using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Tests.Fakes;
using C = FirstAidAdmin.Core.CheckIds;
using S = FirstAidAdmin.Core.Models.DiagnosticStatus;

namespace FirstAidAdmin.Tests;

public class CorrelationEngineTests
{
    private static List<Finding> Analyze(params DiagnosticResult[] checks) => new CorrelationEngine().Analyze(new[] { R.Module("m", checks) });

    [Fact]
    public void GatewayOk_InternetFail_DnsFail_IsExternalNetworkProblem()
    {
        var f = Analyze(
            R.Check(C.NetAdapters, S.Ok), R.Check(C.NetIPv4, S.Ok), R.Check(C.NetGatewayConfigured, S.Ok),
            R.Check(C.NetGatewayPing, S.Ok), R.Check(C.NetInternetIp, S.Error), R.Check(C.DnsResolveExternal, S.Error));
        var top = f[0];
        Assert.Equal("net.external", top.Id);
        Assert.Equal("Вероятная проблема с доступом во внешнюю сеть", top.Title);
        Assert.Equal(Confidence.High, top.Confidence);
        Assert.DoesNotContain(f, x => x.Id == "net.dns"); // superseded
        Assert.Contains(top.Basis, b => b.Supports && b.Text == "Шлюз доступен");
        Assert.Contains(top.Basis, b => !b.Supports && b.Text == "Внешние IP-адреса недоступны");
    }

    [Fact]
    public void GatewayOk_InternetOk_DnsFail_IsDnsProblem_HighConfidence()
    {
        var f = Analyze(
            R.Check(C.NetGatewayPing, S.Ok), R.Check(C.NetInternetIp, S.Ok),
            R.Check(C.DnsResolveExternal, S.Error), R.Check(C.DnsReference, S.Ok), R.Check(C.DnsServerReachable, S.Error));
        var dns = Assert.Single(f, x => x.Id == "net.dns");
        Assert.Equal("Проблема DNS", dns.Title);
        Assert.Equal(Confidence.High, dns.Confidence);
        Assert.Equal(Severity.High, dns.Severity);
        Assert.Contains(dns.Basis, b => b.Supports && b.Text == "Интернет по IP работает");
        Assert.Contains(dns.Basis, b => b.Supports && b.Text == "Шлюз доступен");
        Assert.Contains(dns.Basis, b => !b.Supports && b.Text == "DNS-запросы не проходят");
        Assert.Contains(FirstAidAdmin.Core.ActionIds.FlushDns, dns.RemediationIds);
        Assert.Equal("net.dns", dns.KnowledgeBaseId);
    }

    [Fact]
    public void FullDisk_AndWindowsUpdateErrors_AreCorrelated()
    {
        var f = Analyze(
            R.Check(C.StorageSystem, S.Error, "Занято 98%"),
            R.Check(C.WuHistoryErrors, S.Error, "Неудачных установок: 3", ("codes", "0x80070070")),
            R.Check(C.StorageTemp, S.Warning));
        var wu = Assert.Single(f, x => x.Id == "wu.disk-space");
        Assert.Equal(Confidence.High, wu.Confidence);
        Assert.Contains("Windows Update", wu.Title);
        Assert.DoesNotContain(f, x => x.Id == "disk.system-low"); // superseded by the more specific finding
    }

    [Fact]
    public void FullDisk_Alone_IsDiskFinding()
    {
        var f = Analyze(R.Check(C.StorageSystem, S.Warning, "Занято 90%"), R.Check(C.WuHistoryErrors, S.Ok));
        Assert.Contains(f, x => x.Id == "disk.system-low" && x.Severity == Severity.Medium);
        Assert.DoesNotContain(f, x => x.Id == "wu.disk-space");
    }

    [Fact]
    public void NoAdapter_SupersedesEverythingElseInTheChain()
    {
        var f = Analyze(R.Check(C.NetAdapters, S.Error), R.Check(C.NetIPv4, S.Skipped), R.Check(C.NetInternetIp, S.Skipped));
        var top = Assert.Single(f);
        Assert.Equal("net.no-adapter", top.Id);
        Assert.Equal(Severity.Critical, top.Severity);
    }

    [Fact]
    public void GatewayIcmpBlocked_ButInternetOk_IsNotAFinding()
    {
        var f = Analyze(R.Check(C.NetGatewayPing, S.Error), R.Check(C.NetInternetIp, S.Ok), R.Check(C.DnsResolveExternal, S.Ok));
        Assert.DoesNotContain(f, x => x.Id == "net.gateway-unreachable");
        // The failed ping is explained by the rule, so no generic finding either.
        Assert.DoesNotContain(f, x => x.Id == "check:" + C.NetGatewayPing);
    }

    [Fact]
    public void GatewayUnreachable_ConfidenceDependsOnArp()
    {
        var withArp = Analyze(R.Check(C.NetGatewayPing, S.Error), R.Check(C.NetGatewayArp, S.Ok), R.Check(C.NetInternetIp, S.Error));
        var noArp = Analyze(R.Check(C.NetGatewayPing, S.Error), R.Check(C.NetGatewayArp, S.Info), R.Check(C.NetInternetIp, S.Error));
        Assert.Equal(Confidence.Medium, withArp.Single(x => x.Id == "net.gateway-unreachable").Confidence);
        Assert.Equal(Confidence.High, noArp.Single(x => x.Id == "net.gateway-unreachable").Confidence);
    }

    [Fact]
    public void DomainPc_WithPublicDns_IsHighSeverity()
    {
        var f = Analyze(R.Check(C.DnsServersConfigured, S.Error, "8.8.8.8", ("publicOnDomain", "True")), R.Check(C.DnsSrvLdap, S.Error), R.Check(C.DnsResolveExternal, S.Ok));
        Assert.Equal("domain.public-dns", f[0].Id);
        Assert.DoesNotContain(f, x => x.Id == "dns.internal-only");
    }

    [Fact]
    public void SecureChannel_WithReachableDc_IsHighConfidence()
    {
        var f = Analyze(R.Check(C.DomainSecureChannel, S.Error), R.Check(C.DomainDcConnectivity, S.Ok));
        var sc = f.Single(x => x.Id == "domain.secure-channel");
        Assert.Equal(Confidence.High, sc.Confidence);
        Assert.Equal(Severity.Critical, sc.Severity);
    }

    [Fact]
    public void PerformanceSummary_ListsCauses_WithModestConfidence()
    {
        var f = Analyze(R.Check(C.PerfCpu, S.Ok), R.Check(C.PerfRam, S.Warning), R.Check(C.PerfDisk, S.Error), R.Check(C.PerfUptime, S.Warning));
        var p = f.Single(x => x.Id == "perf.summary");
        Assert.Contains("1. Высокая загрузка RAM", p.WhatWasFound);
        Assert.Contains("Недостаточно свободного места", p.WhatWasFound);
        Assert.Contains("Очень длительное время", p.WhatWasFound);
        Assert.NotEqual(Confidence.High, p.Confidence);
        Assert.Contains("не доказана", p.ProbableCause);
    }

    [Fact]
    public void ComponentStore_AndUpdateErrors()
    {
        var f = Analyze(R.Check(C.HealthDism, S.Error), R.Check(C.WuHistoryErrors, S.Warning, "", ("codes", "0x80073712")));
        var c = f.Single(x => x.Id == "wu.component-store");
        Assert.Equal(Confidence.High, c.Confidence);
        Assert.True(c.MayRequireReboot);
        Assert.DoesNotContain(f, x => x.Id == "health.dism-repairable");
    }

    [Fact]
    public void UncoveredFailedCheck_BecomesSimpleFinding()
    {
        var c = R.Check("custom.check", S.Error, "Что-то сломалось");
        c.Recommendation = "Сделайте X";
        var f = Analyze(c);
        var g = Assert.Single(f);
        Assert.False(g.IsCorrelated);
        Assert.Equal("Сделайте X", g.Recommendation);
    }

    [Fact]
    public void NoProblems_NoFindings_AndEmptyInputIsSafe()
    {
        Assert.Empty(Analyze(R.Check(C.NetInternetIp, S.Ok), R.Check(C.DnsResolveExternal, S.Ok)));
        Assert.Empty(new CorrelationEngine().Analyze(Array.Empty<DiagnosticResult>()));
    }

    [Fact]
    public void FaultyRule_DoesNotBreakAnalysis()
    {
        var engine = new CorrelationEngine(new ICorrelationRule[]
        {
            new DelegateRule("boom", _ => throw new InvalidOperationException()),
            new DelegateRule("ok", _ => new Finding { Title = "ok" })
        });
        Assert.Single(engine.Analyze(new[] { R.Module("m") }), f => f.Id == "ok");
    }

    [Fact]
    public void Findings_AreOrderedBySeverity()
    {
        var f = Analyze(R.Check(C.WifiSignal, S.Warning), R.Check(C.NetAdapters, S.Error));
        Assert.Equal(Severity.Critical, f[0].Severity);
    }

    [Fact]
    public void FindingWording_NeverClaimsCertainty()
    {
        var all = new List<Finding>();
        foreach (var id in new[] { C.NetAdapters, C.NetIPv4, C.DomainSecureChannel, C.PrinterSpooler, C.RdpEnabled, C.SecFirewall, C.StorageSystem })
            all.AddRange(Analyze(R.Check(id, S.Error)));
        Assert.DoesNotContain(all, f => System.Text.RegularExpressions.Regex.IsMatch(f.Title + " " + f.ProbableCause, @"(?i)(?<!\p{L})(точно|наверняка|гарантированно)(?!\p{L})"));
    }
}

public class SeverityEngineTests
{
    [Fact]
    public void Worst_PicksMostSevere()
    {
        Assert.Equal(S.Critical, SeverityEngine.Worst(new[] { S.Ok, S.Critical, S.Warning }));
        Assert.Equal(S.Ok, SeverityEngine.Worst(new[] { S.Ok, S.Info, S.Skipped }));
        Assert.Equal(S.Info, SeverityEngine.Worst(Array.Empty<S>()));
    }

    [Fact]
    public void Normalize_PropagatesWorstChildStatus_AndFixesSeverity()
    {
        var m = R.Module("m", R.Check("a", S.Ok), R.Check("b", S.Error));
        SeverityEngine.Normalize(m);
        Assert.Equal(S.Error, m.Status);
        Assert.Equal(Severity.High, m.Severity);
        var ok = R.Module("m2", R.Check("a", S.Ok));
        SeverityEngine.Normalize(ok);
        Assert.Equal(Severity.Low, ok.Severity);
    }

    [Fact]
    public void Summarize_CountsLeavesAndRecommendations()
    {
        var results = new[]
        {
            R.Module("m", R.Check("a", S.Ok), R.Check("b", S.Ok), R.Check("c", S.Warning), R.Check("d", S.Error), R.Check("e", S.Skipped))
        };
        var findings = new List<Finding>
        {
            new() { Title = "Недостаточно места", Severity = Severity.High, Recommendation = "Освободить место" },
            new() { Title = "Мелочь", Severity = Severity.Low, Recommendation = "Проверить" }
        };
        var s = SeverityEngine.Summarize(results, findings);
        Assert.Equal(2, s.OkCount);
        Assert.Equal(1, s.WarningCount);
        Assert.Equal(1, s.ProblemCount);
        Assert.Equal(1, s.SkippedCount);
        Assert.Equal(new[] { "Недостаточно места" }, s.CriticalFindings);
        Assert.Equal("Освободить место", s.Recommendations[0]);
        Assert.Equal(S.Error, s.OverallStatus);
    }

    [Fact]
    public void Summarize_CountsEventLogParentNotGroups()
    {
        var log = R.Check("events.system", S.Error);
        log.Checks.Add(R.Check("events.group.system.x.1", S.Error));
        log.Checks.Add(R.Check("events.group.system.y.2", S.Info));
        var s = SeverityEngine.Summarize(new[] { R.Module("eventlog", log) }, Array.Empty<Finding>());
        Assert.Equal(1, s.ProblemCount);
        Assert.Equal(0, s.InfoCount);
    }

    [Fact]
    public void Russian_Labels()
    {
        Assert.Equal("высокая", SeverityEngine.Russian(Confidence.High));
        Assert.Equal("ВЫСОКИЙ", SeverityEngine.Russian(RiskLevel.High));
        Assert.Equal("🟢", SeverityEngine.Icon(S.Ok));
        Assert.Equal("🔴", SeverityEngine.Icon(S.Error));
    }
}
