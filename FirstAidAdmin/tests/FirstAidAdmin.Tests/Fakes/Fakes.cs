using System.Text.Json;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Infrastructure.Commands;

namespace FirstAidAdmin.Tests.Fakes;

public sealed class FakeNetworkProbe : INetworkProbe
{
    public List<NetworkAdapterInfo> Adapters { get; } = new();
    public HashSet<string> PingFails { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> TcpFails { get; } = new(StringComparer.OrdinalIgnoreCase); // "host:port" or "host"
    public HashSet<string> ResolveFails { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> ServerFails { get; } = new(StringComparer.OrdinalIgnoreCase); // servers timing out
    public HashSet<string> SrvMissing { get; } = new(StringComparer.OrdinalIgnoreCase); // names with no SRV
    public bool AllPingFail { get; set; }
    public bool AllDnsFail { get; set; }
    public bool AllTcpFail { get; set; }
    public HttpOutcome? Http { get; set; }
    public ProxyInfo Proxy { get; set; } = new();
    public TcpStatistics Stats { get; set; } = new() { SegmentsSent = 100_000, SegmentsResent = 100, ActiveConnections = 20, ListeningPorts = 10 };
    public List<int> Listening { get; } = new();

    public static FakeNetworkProbe Healthy()
    {
        var p = new FakeNetworkProbe();
        p.Adapters.Add(new NetworkAdapterInfo
        {
            Id = "eth0", Name = "Ethernet", Description = "Intel(R) Ethernet", Type = "Ethernet", IsUp = true, SpeedBitsPerSecond = 1_000_000_000,
            MacAddress = "00-11-22-33-44-55", IPv4 = { new IpAddressInfo("192.168.1.50", 24) }, Gateways = { "192.168.1.1" },
            DnsServers = { "192.168.1.1" }, DhcpEnabled = true, DhcpServers = { "192.168.1.1" }, DnsSuffix = "home"
        });
        return p;
    }

    public IReadOnlyList<NetworkAdapterInfo> GetAdapters() => Adapters;
    public bool IsNetworkAvailable() => Adapters.Any(a => a.IsUp);

    public Task<PingOutcome> PingAsync(string host, int timeoutMs, CancellationToken cancellationToken)
    {
        var ok = !AllPingFail && !PingFails.Contains(host);
        return Task.FromResult(new PingOutcome(host, ok, ok ? 5 : -1, ok ? "Success" : "TimedOut"));
    }

    public Task<TcpOutcome> TcpConnectAsync(string host, int port, int timeoutMs, CancellationToken cancellationToken)
    {
        var ok = !AllTcpFail && !TcpFails.Contains($"{host}:{port}") && !TcpFails.Contains(host);
        return Task.FromResult(new TcpOutcome(host, port, ok, ok ? 7 : timeoutMs, ok ? null : "timeout"));
    }

    public Task<DnsOutcome> ResolveAsync(string name, int timeoutMs, CancellationToken cancellationToken)
    {
        var ok = !AllDnsFail && !ResolveFails.Contains(name);
        return Task.FromResult(new DnsOutcome(name, ok, ok ? new[] { "203.0.113.10" } : Array.Empty<string>(), 12, ok ? null : "HostNotFound"));
    }

    public Task<DnsOutcome> QueryServerAsync(string server, string name, int timeoutMs, CancellationToken cancellationToken, bool srv = false)
    {
        if (ServerFails.Contains(server) || (AllDnsFail && !server.StartsWith("8.8.") && !server.StartsWith("1.1.")))
            return Task.FromResult(new DnsOutcome(name, false, Array.Empty<string>(), timeoutMs, "timeout", server));
        if (srv)
        {
            var missing = SrvMissing.Contains(name) || SrvMissing.Contains("*");
            return Task.FromResult(new DnsOutcome(name, !missing, missing ? Array.Empty<string>() : new[] { "dc01.corp.local:389" }, 10, missing ? "NXDOMAIN" : null, server));
        }
        return Task.FromResult(new DnsOutcome(name, true, new[] { "203.0.113.10" }, 10, null, server));
    }

    public Task<HttpOutcome> HttpGetAsync(string url, int timeoutMs, CancellationToken cancellationToken)
        => Task.FromResult(Http ?? (AllTcpFail || AllDnsFail
            ? new HttpOutcome(url, false, 0, null, timeoutMs, "No such host")
            : new HttpOutcome(url, true, 200, "Microsoft Connect Test", 30, null)));

    public ProxyInfo GetProxyInfo(string probeUrl) => Proxy;
    public TcpStatistics GetTcpStatistics() => Stats;
    public IReadOnlyList<int> GetListeningTcpPorts() => Listening;
}

public sealed class FakeCommandRunner : ICommandRunner
{
    public Dictionary<string, CommandResult> Responses { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> Calls { get; } = new();

    public void Set(string fileAndArgsPrefix, string stdout, int exit = 0)
        => Responses[fileAndArgsPrefix] = new CommandResult(fileAndArgsPrefix, exit, stdout, "", TimeSpan.FromMilliseconds(5));

    public Task<CommandResult> RunAsync(string fileName, string arguments, TimeSpan timeout, CancellationToken cancellationToken, OutputEncoding encoding = OutputEncoding.Oem)
    {
        var cmd = $"{fileName} {arguments}".Trim();
        Calls.Add(cmd);
        var match = Responses.Where(kv => cmd.StartsWith(kv.Key, StringComparison.OrdinalIgnoreCase)).OrderByDescending(kv => kv.Key.Length).Select(kv => kv.Value).FirstOrDefault();
        return Task.FromResult(match is null ? CommandResult.NotStarted(cmd, "not configured") : match with { Command = cmd });
    }
}

public sealed class FakePowerShell : IPowerShellRunner
{
    public Dictionary<string, string> JsonByScriptFragment { get; } = new(StringComparer.Ordinal);
    public List<string> Scripts { get; } = new();

    public Task<CommandResult> RunAsync(string script, TimeSpan timeout, CancellationToken cancellationToken)
    {
        Scripts.Add(script);
        var json = Find(script);
        return Task.FromResult(json is null
            ? CommandResult.NotStarted("powershell", "not configured")
            : new CommandResult("powershell", 0, json, "", TimeSpan.FromMilliseconds(5)));
    }

    public async Task<JsonElement?> RunJsonAsync(string script, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var r = await RunAsync(script, timeout, cancellationToken);
        return r.Started ? PowerShellRunner.ParseJson(r.StdOut) : null;
    }

    private string? Find(string script) => JsonByScriptFragment.Where(kv => script.Contains(kv.Key, StringComparison.Ordinal)).Select(kv => kv.Value).FirstOrDefault();
}

public sealed class FakeServiceProbe : IServiceProbe
{
    public Dictionary<string, ServiceInfo> Services { get; } = new(StringComparer.OrdinalIgnoreCase);

    public static FakeServiceProbe Healthy()
    {
        var f = new FakeServiceProbe();
        foreach (var n in new[] { "RpcSs", "EventLog", "Winmgmt", "Dhcp", "Dnscache", "NlaSvc", "LanmanWorkstation", "BFE", "mpssvc", "CryptSvc", "Schedule", "ProfSvc", "Power", "PlugPlay", "Spooler", "TermService", "WlanSvc" })
            f.Add(n, ServiceState.Running, ServiceStartMode.Automatic);
        f.Add("wuauserv", ServiceState.Stopped, ServiceStartMode.Manual);
        f.Add("BITS", ServiceState.Stopped, ServiceStartMode.Manual);
        f.Add("TrustedInstaller", ServiceState.Stopped, ServiceStartMode.Manual);
        f.Add("msiserver", ServiceState.Stopped, ServiceStartMode.Manual);
        return f;
    }

    public FakeServiceProbe Add(string name, ServiceState state, ServiceStartMode mode, string? display = null)
    {
        Services[name] = new ServiceInfo(name, display ?? name, state, mode);
        return this;
    }

    public ServiceInfo Get(string name) => Services.TryGetValue(name, out var s) ? s : new ServiceInfo(name, name, ServiceState.NotFound, ServiceStartMode.Unknown);
    public IReadOnlyList<ServiceInfo> GetAll() => Services.Values.ToList();
}

public sealed class FakeEventLogProbe : IEventLogProbe
{
    public Dictionary<string, List<EventRecordInfo>> Logs { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> Denied { get; } = new(StringComparer.OrdinalIgnoreCase);

    public FakeEventLogProbe Add(string log, string provider, int id, int level, string message, DateTimeOffset? time = null)
    {
        if (!Logs.TryGetValue(log, out var list)) Logs[log] = list = new List<EventRecordInfo>();
        list.Add(new EventRecordInfo(log, provider, id, level, time ?? DateTimeOffset.Now.AddHours(-1), message));
        return this;
    }

    public Task<EventQueryResult> QueryAsync(string logName, TimeSpan window, int maxEvents, bool includeWarnings, CancellationToken cancellationToken, IReadOnlyCollection<int>? eventIds = null)
    {
        if (Denied.Contains(logName)) return Task.FromResult(new EventQueryResult { Log = logName, AccessDenied = true });
        var list = Logs.TryGetValue(logName, out var l) ? l : new List<EventRecordInfo>();
        var since = DateTimeOffset.Now - window;
        var filtered = list.Where(e => e.TimeCreated >= since)
            .Where(e => eventIds is { Count: > 0 } ? eventIds.Contains(e.EventId) : e.Level is 1 or 2 || (includeWarnings && e.Level == 3))
            .OrderByDescending(e => e.TimeCreated).Take(maxEvents).ToList();
        return Task.FromResult(new EventQueryResult { Log = logName, Events = filtered });
    }
}

public sealed class FakeRegistry : IRegistryProbe
{
    public Dictionary<string, object> Values { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> Keys { get; } = new(StringComparer.OrdinalIgnoreCase);

    public FakeRegistry Set(RegistryHive hive, string path, string name, object value) { Values[$"{hive}\\{path}\\{name}"] = value; Keys.Add($"{hive}\\{path}"); return this; }
    public object? GetValue(RegistryHive hive, string path, string name) => Values.TryGetValue($"{hive}\\{path}\\{name}", out var v) ? v : null;
    public bool KeyExists(RegistryHive hive, string path) => Keys.Contains($"{hive}\\{path}");
    public IReadOnlyList<string> GetSubKeyNames(RegistryHive hive, string path) => Array.Empty<string>();
}

public sealed class FakeSystemProbe : ISystemProbe
{
    public SystemSnapshot Snapshot { get; set; } = new()
    {
        MachineName = "PC-001", UserName = "ivanov", UserDomain = "CORP", OsDescription = "Windows 11 Pro 24H2", IsWindows = true,
        Architecture = "X64", ProcessorCount = 8, Uptime = TimeSpan.FromDays(2), NetworkAvailable = true, PrimaryIPv4 = "192.168.1.50"
    };
    public List<DriveSnapshot> Drives { get; } = new() { new DriveSnapshot("C:\\", "System", "NTFS", "Fixed", 256L << 30, 120L << 30, true) };
    public MemorySnapshot Memory { get; set; } = new(16L << 30, 8L << 30);
    public TimeSpan Uptime { get; set; } = TimeSpan.FromDays(2);
    public double? Cpu { get; set; } = 20;
    public List<ProcessSnapshot> Processes { get; } = new() { new ProcessSnapshot(100, "chrome", 5, 800L << 20), new ProcessSnapshot(200, "outlook", 1, 400L << 20) };
    public Dictionary<string, string> Env { get; } = new(StringComparer.OrdinalIgnoreCase) { ["TEMP"] = Path.GetTempPath(), ["windir"] = "C:\\Windows" };

    public SystemSnapshot GetSnapshot() => Snapshot;
    public IReadOnlyList<DriveSnapshot> GetDrives() => Drives;
    public MemorySnapshot GetMemory() => Memory;
    public TimeSpan GetUptime() => Uptime;
    public Task<IReadOnlyList<ProcessSnapshot>> GetTopProcessesAsync(TimeSpan sampleInterval, int top, CancellationToken cancellationToken) => Task.FromResult<IReadOnlyList<ProcessSnapshot>>(Processes);
    public Task<double?> GetCpuUsageAsync(TimeSpan sampleInterval, CancellationToken cancellationToken) => Task.FromResult(Cpu);
    public string? GetEnvironmentVariable(string name) => Env.TryGetValue(name, out var v) ? v : null;
}

public sealed class FakeFileSystem : IFileSystemProbe
{
    public HashSet<string> Files { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> Dirs { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> Content { get; } = new(StringComparer.OrdinalIgnoreCase);
    public long TempBytes { get; set; } = 100L << 20;

    public bool FileExists(string path) => Files.Contains(path);
    public bool DirectoryExists(string path) => Dirs.Contains(path);
    public (long Bytes, int Files, bool Truncated) GetDirectorySize(string path, int maxFiles) => (TempBytes, 120, false);
    public string? TryOpenRead(string path) => Files.Contains(path) ? null : "Access denied";
    public string? ReadTail(string path, int maxBytes) => Content.TryGetValue(path, out var c) ? c : null;
    public Task<bool> DirectoryExistsWithTimeoutAsync(string path, int timeoutMs, CancellationToken cancellationToken) => Task.FromResult(Dirs.Contains(path));
    public IReadOnlyList<string> FindExecutable(string nameOrPath) => Files.Where(f => f.EndsWith(Path.GetFileName(nameOrPath), StringComparison.OrdinalIgnoreCase) || f.EndsWith(nameOrPath + ".exe", StringComparison.OrdinalIgnoreCase)).ToList();
}

public sealed class FakeProcessLauncher : IProcessLauncher
{
    public List<int> Running { get; } = new();
    public (bool, bool, int?, string?) LaunchResult { get; set; } = (true, false, null, null);
    public int Launches { get; private set; }
    public Task<(bool Started, bool ExitedEarly, int? ExitCode, string? Error)> LaunchAndObserveAsync(string path, TimeSpan observe, CancellationToken cancellationToken) { Launches++; return Task.FromResult(LaunchResult); }
    public IReadOnlyList<int> FindRunningProcesses(string processName) => Running;
}

public static class TestContext
{
    public static DiagnosticContext Create(SystemSnapshot? system = null, Dictionary<string, string>? inputs = null, AppSettings? settings = null)
        => new() { System = system ?? new FakeSystemProbe().Snapshot, Inputs = inputs ?? new Dictionary<string, string>(), Settings = settings ?? new AppSettings() };

    public static SystemSnapshot Domain(bool admin = false) => new()
    {
        MachineName = "PC-001", UserName = "ivanov", UserDomain = "CORP", IsDomainJoined = true, DomainName = "corp.local", LogonServer = "DC01",
        IsWindows = true, IsAdmin = admin, OsDescription = "Windows 11 Pro"
    };
}

public static class R
{
    public static DiagnosticResult Check(string id, DiagnosticStatus status, string summary = "", params (string Key, string Value)[] evidence)
    {
        var c = DiagnosticResult.Create(id, id, DiagnosticCategory.System, status, summary == "" ? id + " " + status : summary);
        foreach (var (k, v) in evidence) c.WithEvidence(k, v);
        return c;
    }

    public static DiagnosticResult Module(string id, params DiagnosticResult[] checks)
    {
        var m = DiagnosticResult.Create(id, id, DiagnosticCategory.System, DiagnosticStatus.Info, id);
        m.Checks.AddRange(checks);
        return m;
    }

    public static DiagnosticResult Get(this DiagnosticResult root, string id) => root.Flatten().First(c => c.Id == id);
}
