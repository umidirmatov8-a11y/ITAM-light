using System.Diagnostics;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using FirstAidAdmin.Core.Abstractions;
using TcpStatistics = FirstAidAdmin.Core.Abstractions.TcpStatistics;

namespace FirstAidAdmin.Infrastructure.Network;

/// <summary>Network probe based on standard .NET/Windows APIs (no external tools, language independent).</summary>
public sealed class NetworkProbe : INetworkProbe
{
    private static readonly string[] VirtualMarkers =
        { "virtual", "hyper-v", "vmware", "virtualbox", "vbox", "wsl", "docker", "loopback", "pseudo", "teredo", "isatap", "6to4" };

    private readonly IRegistryProbe _registry;
    private static readonly Random Rng = new();

    public NetworkProbe(IRegistryProbe registry) => _registry = registry;

    public bool IsNetworkAvailable()
    {
        try { return NetworkInterface.GetIsNetworkAvailable(); }
        catch { return false; }
    }

    public IReadOnlyList<NetworkAdapterInfo> GetAdapters()
    {
        var list = new List<NetworkAdapterInfo>();
        NetworkInterface[] nics;
        try { nics = NetworkInterface.GetAllNetworkInterfaces(); }
        catch { return list; }

        foreach (var nic in nics)
        {
            var info = new NetworkAdapterInfo
            {
                Id = nic.Id,
                Name = nic.Name,
                Description = nic.Description,
                Type = nic.NetworkInterfaceType.ToString(),
                IsUp = nic.OperationalStatus == OperationalStatus.Up,
                IsWireless = nic.NetworkInterfaceType == NetworkInterfaceType.Wireless80211,
                IsLoopback = nic.NetworkInterfaceType == NetworkInterfaceType.Loopback,
            };
            var text = (nic.Name + " " + nic.Description).ToLowerInvariant();
            info.IsVirtual = info.IsLoopback || nic.NetworkInterfaceType == NetworkInterfaceType.Tunnel || VirtualMarkers.Any(text.Contains);
            try { info.SpeedBitsPerSecond = nic.Speed; } catch { }
            try { info.MacAddress = FormatMac(nic.GetPhysicalAddress()); } catch { }

            try
            {
                var props = nic.GetIPProperties();
                foreach (var ua in props.UnicastAddresses)
                {
                    if (ua.Address.AddressFamily == AddressFamily.InterNetwork)
                        info.IPv4.Add(new IpAddressInfo(ua.Address.ToString(), SafePrefix(ua)));
                    else if (ua.Address.AddressFamily == AddressFamily.InterNetworkV6)
                        info.IPv6.Add(new IpAddressInfo(ua.Address.ToString(), SafePrefix(ua)));
                }
                info.Gateways = props.GatewayAddresses
                    .Select(g => g.Address)
                    .Where(a => !a.Equals(IPAddress.Any) && !a.Equals(IPAddress.IPv6Any))
                    .Select(a => a.ToString())
                    .ToList();
                info.DnsServers = props.DnsAddresses
                    .Where(a => !(a.IsIPv6SiteLocal && a.ToString().StartsWith("fec0", StringComparison.OrdinalIgnoreCase)))
                    .Select(a => a.ToString()).ToList();
                info.DnsSuffix = props.DnsSuffix ?? "";
                if (OperatingSystem.IsWindows())
                {
                    try { info.DhcpEnabled = props.GetIPv4Properties()?.IsDhcpEnabled; } catch { }
                    try { info.DhcpServers = props.DhcpServerAddresses.Select(a => a.ToString()).ToList(); } catch { }
                }
            }
            catch { /* adapter without IP stack */ }

            list.Add(info);
        }
        return list;
    }

    private static int SafePrefix(UnicastIPAddressInformation ua)
    {
        try { return ua.PrefixLength; } catch { return 0; }
    }

    private static string FormatMac(PhysicalAddress pa)
    {
        var bytes = pa.GetAddressBytes();
        return bytes.Length == 0 ? "" : string.Join("-", bytes.Select(b => b.ToString("X2")));
    }

    public async Task<PingOutcome> PingAsync(string host, int timeoutMs, CancellationToken cancellationToken)
    {
        try
        {
            using var ping = new Ping();
            var reply = await ping.SendPingAsync(host, TimeSpan.FromMilliseconds(timeoutMs), cancellationToken: cancellationToken).ConfigureAwait(false);
            return new PingOutcome(host, reply.Status == IPStatus.Success, reply.RoundtripTime, reply.Status.ToString());
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception ex)
        {
            return new PingOutcome(host, false, -1, ex.InnerException?.Message ?? ex.Message);
        }
    }

    public async Task<TcpOutcome> TcpConnectAsync(string host, int port, int timeoutMs, CancellationToken cancellationToken)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            using var client = new TcpClient();
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(timeoutMs);
            await client.ConnectAsync(host, port, cts.Token).ConfigureAwait(false);
            return new TcpOutcome(host, port, client.Connected, sw.ElapsedMilliseconds, null);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (OperationCanceledException)
        {
            return new TcpOutcome(host, port, false, sw.ElapsedMilliseconds, "timeout");
        }
        catch (Exception ex)
        {
            return new TcpOutcome(host, port, false, sw.ElapsedMilliseconds, (ex as SocketException)?.SocketErrorCode.ToString() ?? ex.Message);
        }
    }

    public async Task<DnsOutcome> ResolveAsync(string name, int timeoutMs, CancellationToken cancellationToken)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(timeoutMs);
            var addrs = await Dns.GetHostAddressesAsync(name, cts.Token).ConfigureAwait(false);
            return new DnsOutcome(name, addrs.Length > 0, addrs.Select(a => a.ToString()).ToList(), sw.ElapsedMilliseconds, addrs.Length == 0 ? "no addresses" : null);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (OperationCanceledException)
        {
            return new DnsOutcome(name, false, Array.Empty<string>(), sw.ElapsedMilliseconds, "timeout");
        }
        catch (Exception ex)
        {
            return new DnsOutcome(name, false, Array.Empty<string>(), sw.ElapsedMilliseconds,
                (ex as SocketException)?.SocketErrorCode.ToString() ?? ex.Message);
        }
    }

    public async Task<DnsOutcome> QueryServerAsync(string server, string name, int timeoutMs, CancellationToken cancellationToken, bool srv = false)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            if (!IPAddress.TryParse(server, out var ip))
                return new DnsOutcome(name, false, Array.Empty<string>(), 0, "invalid server address", server);
            ushort id;
            lock (Rng) id = (ushort)Rng.Next(1, ushort.MaxValue);
            var query = DnsWire.BuildQuery(id, name, srv ? DnsWire.TypeSrv : DnsWire.TypeA);
            using var udp = new UdpClient(ip.AddressFamily);
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(timeoutMs);
            await udp.SendAsync(query, new IPEndPoint(ip, 53), cts.Token).ConfigureAwait(false);
            while (true)
            {
                var res = await udp.ReceiveAsync(cts.Token).ConfigureAwait(false);
                var parsed = DnsWire.Parse(res.Buffer);
                if (parsed.Id != id) continue;
                var values = srv ? parsed.SrvTargets : parsed.Addresses;
                var ok = parsed.RCode == 0 && values.Count > 0;
                return new DnsOutcome(name, ok, values, sw.ElapsedMilliseconds, ok ? null : DnsWire.RCodeText(parsed.RCode) + (parsed.RCode == 0 ? " (нет записей)" : ""), server);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (OperationCanceledException)
        {
            return new DnsOutcome(name, false, Array.Empty<string>(), sw.ElapsedMilliseconds, "timeout", server);
        }
        catch (Exception ex)
        {
            return new DnsOutcome(name, false, Array.Empty<string>(), sw.ElapsedMilliseconds, ex.Message, server);
        }
    }

    public async Task<HttpOutcome> HttpGetAsync(string url, int timeoutMs, CancellationToken cancellationToken)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            using var handler = new HttpClientHandler { UseProxy = true, AllowAutoRedirect = false };
            using var http = new HttpClient(handler) { Timeout = TimeSpan.FromMilliseconds(timeoutMs) };
            http.DefaultRequestHeaders.UserAgent.ParseAdd("FirstAidAdmin/2.0");
            using var resp = await http.GetAsync(url, cancellationToken).ConfigureAwait(false);
            var body = await resp.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
            if (body.Length > 200) body = body[..200];
            return new HttpOutcome(url, resp.IsSuccessStatusCode, (int)resp.StatusCode, body, sw.ElapsedMilliseconds, null);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (Exception ex)
        {
            return new HttpOutcome(url, false, 0, null, sw.ElapsedMilliseconds, ex is TaskCanceledException ? "timeout" : ex.InnerException?.Message ?? ex.Message);
        }
    }

    public ProxyInfo GetProxyInfo(string probeUrl)
    {
        const string key = @"Software\Microsoft\Windows\CurrentVersion\Internet Settings";
        var info = new ProxyInfo();
        try
        {
            info.Enabled = Convert.ToInt32(_registry.GetValue(RegistryHive.CurrentUser, key, "ProxyEnable") ?? 0) == 1;
            info.Server = _registry.GetValue(RegistryHive.CurrentUser, key, "ProxyServer") as string;
            info.AutoConfigUrl = _registry.GetValue(RegistryHive.CurrentUser, key, "AutoConfigURL") as string;
            info.Bypass = _registry.GetValue(RegistryHive.CurrentUser, key, "ProxyOverride") as string;
        }
        catch { /* not Windows */ }
        try
        {
            var uri = new Uri(probeUrl);
            var proxy = WebRequest.GetSystemWebProxy().GetProxy(uri);
            if (proxy is not null && proxy != uri) info.EffectiveProxyForProbe = proxy.ToString();
        }
        catch { }
        return info;
    }

    public TcpStatistics GetTcpStatistics()
    {
        var s = new TcpStatistics();
        try
        {
            var props = IPGlobalProperties.GetIPGlobalProperties();
            var tcp = props.GetTcpIPv4Statistics();
            s.ConnectionsEstablished = tcp.CurrentConnections;
            s.SegmentsSent = tcp.SegmentsSent;
            s.SegmentsResent = tcp.SegmentsResent;
            s.FailedConnectionAttempts = tcp.FailedConnectionAttempts;
            s.ResetConnections = tcp.ResetConnections;
            s.ActiveConnections = props.GetActiveTcpConnections().Length;
            s.ListeningPorts = props.GetActiveTcpListeners().Length;
            s.UdpListeners = props.GetActiveUdpListeners().Length;
            var udp = props.GetUdpIPv4Statistics();
            s.UdpDatagramsReceived = udp.DatagramsReceived;
            s.UdpIncomingErrors = udp.IncomingDatagramsWithErrors;
        }
        catch { }
        return s;
    }

    public IReadOnlyList<int> GetListeningTcpPorts()
    {
        try
        {
            return IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Select(e => e.Port).Distinct().ToList();
        }
        catch { return Array.Empty<int>(); }
    }
}
