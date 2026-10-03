using System.Net;
using System.Text.Json;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Abstractions;

// All OS access goes through these interfaces so analyzers are unit-testable with fakes.

public sealed record CommandResult(
    string Command,
    int ExitCode,
    string StdOut,
    string StdErr,
    TimeSpan Duration,
    bool TimedOut = false,
    bool Started = true,
    string? Error = null)
{
    public bool Success => Started && !TimedOut && ExitCode == 0;
    public static CommandResult NotStarted(string command, string error) => new(command, -1, "", "", TimeSpan.Zero, false, false, error);
}

public enum OutputEncoding { Oem, Utf8, Unicode }

public interface ICommandRunner
{
    Task<CommandResult> RunAsync(string fileName, string arguments, TimeSpan timeout,
        CancellationToken cancellationToken, OutputEncoding encoding = OutputEncoding.Oem);
}

public interface IPowerShellRunner
{
    Task<CommandResult> RunAsync(string script, TimeSpan timeout, CancellationToken cancellationToken);
    /// <summary>Runs a script that ends with ConvertTo-Json and parses the result. Null on failure.</summary>
    Task<JsonElement?> RunJsonAsync(string script, TimeSpan timeout, CancellationToken cancellationToken);
}

public sealed record IpAddressInfo(string Address, int PrefixLength);

public sealed class NetworkAdapterInfo
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public string Type { get; set; } = "";
    public bool IsUp { get; set; }
    public bool IsWireless { get; set; }
    public bool IsVirtual { get; set; }
    public bool IsLoopback { get; set; }
    public long SpeedBitsPerSecond { get; set; }
    public string MacAddress { get; set; } = "";
    public List<IpAddressInfo> IPv4 { get; set; } = new();
    public List<IpAddressInfo> IPv6 { get; set; } = new();
    public List<string> Gateways { get; set; } = new();
    public List<string> DnsServers { get; set; } = new();
    public bool? DhcpEnabled { get; set; }
    public List<string> DhcpServers { get; set; } = new();
    public string DnsSuffix { get; set; } = "";
}

public sealed record PingOutcome(string Host, bool Success, long RoundTripMs, string Status);
public sealed record TcpOutcome(string Host, int Port, bool Success, long ElapsedMs, string? Error);
public sealed record DnsOutcome(string Name, bool Success, IReadOnlyList<string> Addresses, long ElapsedMs, string? Error, string? Server = null);
public sealed record HttpOutcome(string Url, bool Success, int StatusCode, string? BodyStart, long ElapsedMs, string? Error);

public sealed class ProxyInfo
{
    public bool Enabled { get; set; }
    public string? Server { get; set; }
    public string? AutoConfigUrl { get; set; }
    public bool AutoDetect { get; set; }
    public string? Bypass { get; set; }
    public string? EffectiveProxyForProbe { get; set; }
}

public sealed class TcpStatistics
{
    public long ConnectionsEstablished { get; set; }
    public long SegmentsSent { get; set; }
    public long SegmentsResent { get; set; }
    public long FailedConnectionAttempts { get; set; }
    public long ResetConnections { get; set; }
    public int ActiveConnections { get; set; }
    public int ListeningPorts { get; set; }
    public int UdpListeners { get; set; }
    public long UdpDatagramsReceived { get; set; }
    public long UdpIncomingErrors { get; set; }
}

public interface INetworkProbe
{
    IReadOnlyList<NetworkAdapterInfo> GetAdapters();
    bool IsNetworkAvailable();
    Task<PingOutcome> PingAsync(string host, int timeoutMs, CancellationToken cancellationToken);
    Task<TcpOutcome> TcpConnectAsync(string host, int port, int timeoutMs, CancellationToken cancellationToken);
    /// <summary>Resolves through the OS resolver (cache, hosts, configured servers).</summary>
    Task<DnsOutcome> ResolveAsync(string name, int timeoutMs, CancellationToken cancellationToken);
    /// <summary>Sends a raw DNS query (A or SRV) to a specific server, bypassing the OS cache.
    /// For SRV queries Addresses contains "target:port".</summary>
    Task<DnsOutcome> QueryServerAsync(string server, string name, int timeoutMs, CancellationToken cancellationToken, bool srv = false);
    Task<HttpOutcome> HttpGetAsync(string url, int timeoutMs, CancellationToken cancellationToken);
    ProxyInfo GetProxyInfo(string probeUrl);
    TcpStatistics GetTcpStatistics();
    IReadOnlyList<int> GetListeningTcpPorts();
}

public enum ServiceState { Unknown, Stopped, StartPending, StopPending, Running, ContinuePending, PausePending, Paused, NotFound }
public enum ServiceStartMode { Unknown, Boot, System, Automatic, Manual, Disabled }

public sealed record ServiceInfo(string Name, string DisplayName, ServiceState State, ServiceStartMode StartMode);

public interface IServiceProbe
{
    ServiceInfo Get(string name);
    IReadOnlyList<ServiceInfo> GetAll();
}

public sealed record EventRecordInfo(string Log, string Provider, int EventId, int Level, DateTimeOffset TimeCreated, string Message);

public sealed class EventQueryResult
{
    public string Log { get; init; } = "";
    public bool Available { get; init; } = true;
    public bool AccessDenied { get; init; }
    public string? Error { get; init; }
    public IReadOnlyList<EventRecordInfo> Events { get; init; } = Array.Empty<EventRecordInfo>();
}

public interface IEventLogProbe
{
    /// <summary>Errors/critical (and optionally warnings) from a log for the given window.</summary>
    Task<EventQueryResult> QueryAsync(string logName, TimeSpan window, int maxEvents, bool includeWarnings,
        CancellationToken cancellationToken, IReadOnlyCollection<int>? eventIds = null);
}

public enum RegistryHive { LocalMachine, CurrentUser }

public interface IRegistryProbe
{
    object? GetValue(RegistryHive hive, string path, string name);
    bool KeyExists(RegistryHive hive, string path);
    IReadOnlyList<string> GetSubKeyNames(RegistryHive hive, string path);
}

public sealed record DriveSnapshot(string Name, string Label, string Format, string DriveType, long TotalBytes, long FreeBytes, bool IsSystem)
{
    public double UsedPercent => TotalBytes <= 0 ? 0 : Math.Round(100.0 * (TotalBytes - FreeBytes) / TotalBytes, 1);
    public double FreeGb => Math.Round(FreeBytes / 1024d / 1024 / 1024, 1);
    public double TotalGb => Math.Round(TotalBytes / 1024d / 1024 / 1024, 1);
}

public sealed record MemorySnapshot(long TotalBytes, long AvailableBytes)
{
    public double UsedPercent => TotalBytes <= 0 ? 0 : Math.Round(100.0 * (TotalBytes - AvailableBytes) / TotalBytes, 1);
}

public sealed record ProcessSnapshot(int Pid, string Name, double CpuPercent, long WorkingSetBytes);

public interface ISystemProbe
{
    SystemSnapshot GetSnapshot();
    IReadOnlyList<DriveSnapshot> GetDrives();
    MemorySnapshot GetMemory();
    TimeSpan GetUptime();
    /// <summary>Samples processes over the interval to compute CPU usage.</summary>
    Task<IReadOnlyList<ProcessSnapshot>> GetTopProcessesAsync(TimeSpan sampleInterval, int top, CancellationToken cancellationToken);
    /// <summary>Total CPU usage (0-100) sampled over the interval, or null if unavailable.</summary>
    Task<double?> GetCpuUsageAsync(TimeSpan sampleInterval, CancellationToken cancellationToken);
    string? GetEnvironmentVariable(string name);
}

public interface IFileSystemProbe
{
    bool FileExists(string path);
    bool DirectoryExists(string path);
    /// <summary>Directory size with an upper bound on enumerated files to keep it fast.</summary>
    (long Bytes, int Files, bool Truncated) GetDirectorySize(string path, int maxFiles);
    /// <summary>Returns null when readable, otherwise the error message.</summary>
    string? TryOpenRead(string path);
    string? ReadTail(string path, int maxBytes);
    Task<bool> DirectoryExistsWithTimeoutAsync(string path, int timeoutMs, CancellationToken cancellationToken);
    IReadOnlyList<string> FindExecutable(string nameOrPath);
}

public interface IProcessLauncher
{
    /// <summary>Starts a program the admin explicitly allowed and observes it for a short time.</summary>
    Task<(bool Started, bool ExitedEarly, int? ExitCode, string? Error)> LaunchAndObserveAsync(string path, TimeSpan observe, CancellationToken cancellationToken);
    IReadOnlyList<int> FindRunningProcesses(string processName);
}
