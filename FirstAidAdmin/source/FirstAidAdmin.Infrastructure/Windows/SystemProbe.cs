using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Infrastructure.Windows;

/// <summary>Detects whether the current process runs with administrator rights (no elevation attempted).</summary>
public static class AdminDetector
{
    public static bool IsElevated()
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                using var id = System.Security.Principal.WindowsIdentity.GetCurrent();
                return new System.Security.Principal.WindowsPrincipal(id).IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);
            }
            return Environment.IsPrivilegedProcess;
        }
        catch { return false; }
    }
}

internal static class NativeMethods
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    internal sealed class MEMORYSTATUSEX
    {
        public uint dwLength = (uint)Marshal.SizeOf<MEMORYSTATUSEX>();
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX lpBuffer);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetSystemTimes(out long idleTime, out long kernelTime, out long userTime);

    internal enum NetSetupJoinStatus { Unknown = 0, Unjoined, Workgroup, Domain }

    [DllImport("netapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern int NetGetJoinInformation(string? server, out IntPtr domain, out NetSetupJoinStatus status);

    [DllImport("netapi32.dll")]
    internal static extern int NetApiBufferFree(IntPtr buffer);
}

public sealed class SystemProbe : ISystemProbe
{
    private readonly INetworkProbe? _network;

    public SystemProbe(INetworkProbe? network = null) => _network = network;

    /// <summary>Fast snapshot used at startup: no heavy diagnostics.</summary>
    public SystemSnapshot GetSnapshot()
    {
        var s = new SystemSnapshot
        {
            MachineName = Environment.MachineName,
            UserName = Environment.UserName,
            UserDomain = SafeEnv(() => Environment.UserDomainName) ?? "",
            OsDescription = RuntimeInformation.OSDescription,
            OsVersion = Environment.OSVersion.VersionString,
            Architecture = RuntimeInformation.OSArchitecture.ToString(),
            IsWindows = OperatingSystem.IsWindows(),
            IsAdmin = AdminDetector.IsElevated(),
            Uptime = GetUptime(),
            ProcessorCount = Environment.ProcessorCount,
            LogonServer = Environment.GetEnvironmentVariable("LOGONSERVER")?.TrimStart('\\'),
        };
        if (OperatingSystem.IsWindows())
        {
            var (joined, name) = GetJoinInformation();
            s.IsDomainJoined = joined;
            if (joined) s.DomainName = name;
            s.OsDescription = WindowsProductName() ?? s.OsDescription;
        }
        try
        {
            var dnsDomain = IPGlobalProperties.GetIPGlobalProperties().DomainName;
            if (s.IsDomainJoined && !string.IsNullOrWhiteSpace(dnsDomain)) s.DomainName = dnsDomain;
        }
        catch { }

        try
        {
            s.NetworkAvailable = _network?.IsNetworkAvailable() ?? NetworkInterface.GetIsNetworkAvailable();
            s.PrimaryIPv4 = NetworkInterface.GetAllNetworkInterfaces()
                .Where(n => n.OperationalStatus == OperationalStatus.Up && n.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                .Where(n => n.GetIPProperties().GatewayAddresses.Count > 0)
                .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                .Where(a => a.Address.AddressFamily == AddressFamily.InterNetwork)
                .Select(a => a.Address.ToString())
                .FirstOrDefault();
        }
        catch { }
        return s;
    }

    private static string? WindowsProductName()
    {
        if (!OperatingSystem.IsWindows()) return null;
        try
        {
            using var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion");
            var name = key?.GetValue("ProductName") as string;
            var display = key?.GetValue("DisplayVersion") as string;
            var build = key?.GetValue("CurrentBuildNumber") as string;
            if (name is null) return null;
            // Windows 11 still reports "Windows 10" in ProductName; correct by build number.
            if (int.TryParse(build, out var b) && b >= 22000) name = name.Replace("Windows 10", "Windows 11");
            return $"{name} {display} (build {build})".Trim();
        }
        catch { return null; }
    }

    public static (bool Joined, string? Name) GetJoinInformation()
    {
        if (!OperatingSystem.IsWindows()) return (false, null);
        try
        {
            var rc = NativeMethods.NetGetJoinInformation(null, out var buffer, out var status);
            if (rc != 0) return (false, null);
            try
            {
                var name = Marshal.PtrToStringUni(buffer);
                return (status == NativeMethods.NetSetupJoinStatus.Domain, name);
            }
            finally { NativeMethods.NetApiBufferFree(buffer); }
        }
        catch { return (false, null); }
    }

    public IReadOnlyList<DriveSnapshot> GetDrives()
    {
        var systemRoot = Path.GetPathRoot(Environment.GetFolderPath(Environment.SpecialFolder.Windows)) ?? "/";
        if (string.IsNullOrEmpty(systemRoot)) systemRoot = "/";
        var list = new List<DriveSnapshot>();
        foreach (var d in DriveInfo.GetDrives())
        {
            try
            {
                if (!d.IsReady) continue;
                if (d.DriveType is not (DriveType.Fixed or DriveType.Removable)) continue;
                if (!OperatingSystem.IsWindows() && d.TotalSize < 1L << 30) continue; // skip pseudo fs on Linux
                list.Add(new DriveSnapshot(d.Name, d.VolumeLabel, d.DriveFormat, d.DriveType.ToString(), d.TotalSize, d.AvailableFreeSpace,
                    string.Equals(d.Name, systemRoot, StringComparison.OrdinalIgnoreCase)));
            }
            catch { /* drive not accessible */ }
        }
        if (list.Count > 0 && !list.Any(d => d.IsSystem))
            list[0] = list[0] with { IsSystem = true };
        return list;
    }

    public MemorySnapshot GetMemory()
    {
        if (OperatingSystem.IsWindows())
        {
            var m = new NativeMethods.MEMORYSTATUSEX();
            if (NativeMethods.GlobalMemoryStatusEx(m)) return new MemorySnapshot((long)m.ullTotalPhys, (long)m.ullAvailPhys);
        }
        try
        {
            var lines = File.ReadAllLines("/proc/meminfo");
            long Val(string key) => long.Parse(lines.First(l => l.StartsWith(key)).Split(' ', StringSplitOptions.RemoveEmptyEntries)[1]) * 1024;
            return new MemorySnapshot(Val("MemTotal:"), Val("MemAvailable:"));
        }
        catch
        {
            var gc = GC.GetGCMemoryInfo();
            return new MemorySnapshot(gc.TotalAvailableMemoryBytes, 0);
        }
    }

    public TimeSpan GetUptime() => TimeSpan.FromMilliseconds(Environment.TickCount64);

    public async Task<double?> GetCpuUsageAsync(TimeSpan sampleInterval, CancellationToken cancellationToken)
    {
        var a = ReadCpuTimes();
        if (a is null) return null;
        await Task.Delay(sampleInterval, cancellationToken).ConfigureAwait(false);
        var b = ReadCpuTimes();
        if (b is null) return null;
        var idle = b.Value.Idle - a.Value.Idle;
        var total = b.Value.Total - a.Value.Total;
        if (total <= 0) return null;
        return Math.Round(Math.Clamp(100.0 * (total - idle) / total, 0, 100), 1);
    }

    private static (long Idle, long Total)? ReadCpuTimes()
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                // Kernel time includes idle time.
                if (NativeMethods.GetSystemTimes(out var idle, out var kernel, out var user)) return (idle, kernel + user);
                return null;
            }
            var parts = File.ReadLines("/proc/stat").First().Split(' ', StringSplitOptions.RemoveEmptyEntries).Skip(1).Select(long.Parse).ToArray();
            var idleAll = parts[3] + (parts.Length > 4 ? parts[4] : 0);
            return (idleAll, parts.Sum());
        }
        catch { return null; }
    }

    public async Task<IReadOnlyList<ProcessSnapshot>> GetTopProcessesAsync(TimeSpan sampleInterval, int top, CancellationToken cancellationToken)
    {
        var first = new Dictionary<int, (string Name, TimeSpan Cpu)>();
        foreach (var p in Process.GetProcesses())
        {
            using (p)
            {
                try { first[p.Id] = (p.ProcessName, p.TotalProcessorTime); } catch { /* access denied for protected processes */ }
            }
        }
        var sw = Stopwatch.StartNew();
        await Task.Delay(sampleInterval, cancellationToken).ConfigureAwait(false);
        var elapsed = sw.Elapsed.TotalMilliseconds * Environment.ProcessorCount;
        var list = new List<ProcessSnapshot>();
        foreach (var p in Process.GetProcesses())
        {
            using (p)
            {
                try
                {
                    var ws = p.WorkingSet64;
                    double cpu = 0;
                    if (first.TryGetValue(p.Id, out var f))
                        cpu = Math.Round(100.0 * (p.TotalProcessorTime - f.Cpu).TotalMilliseconds / elapsed, 1);
                    list.Add(new ProcessSnapshot(p.Id, p.ProcessName, Math.Max(0, cpu), ws));
                }
                catch
                {
                    try { list.Add(new ProcessSnapshot(p.Id, p.ProcessName, 0, p.WorkingSet64)); } catch { }
                }
            }
        }
        return list.Where(p => p.Pid != 0 && p.Name != "Idle")
            .OrderByDescending(p => p.CpuPercent).ThenByDescending(p => p.WorkingSetBytes)
            .Take(Math.Max(top * 3, top)) // keep top by CPU and by memory
            .Concat(list.OrderByDescending(p => p.WorkingSetBytes).Take(top))
            .DistinctBy(p => p.Pid)
            .ToList();
    }

    public string? GetEnvironmentVariable(string name) => Environment.GetEnvironmentVariable(name);

    private static string? SafeEnv(Func<string> f)
    {
        try { return f(); } catch { return null; }
    }
}
