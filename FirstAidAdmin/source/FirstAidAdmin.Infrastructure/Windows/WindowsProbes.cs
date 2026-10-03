using System.Diagnostics.Eventing.Reader;
using System.ServiceProcess;
using FirstAidAdmin.Core.Abstractions;
using Microsoft.Win32;
using RegistryHive = FirstAidAdmin.Core.Abstractions.RegistryHive;
using ServiceStartMode = FirstAidAdmin.Core.Abstractions.ServiceStartMode;

namespace FirstAidAdmin.Infrastructure.Windows;

public sealed class ServiceProbe : IServiceProbe
{
    public ServiceInfo Get(string name)
    {
        if (!OperatingSystem.IsWindows()) return new ServiceInfo(name, name, ServiceState.NotFound, ServiceStartMode.Unknown);
        try
        {
            using var sc = new ServiceController(name);
            return Map(sc);
        }
        catch (InvalidOperationException)
        {
            return new ServiceInfo(name, name, ServiceState.NotFound, ServiceStartMode.Unknown);
        }
    }

    public IReadOnlyList<ServiceInfo> GetAll()
    {
        if (!OperatingSystem.IsWindows()) return Array.Empty<ServiceInfo>();
        var list = new List<ServiceInfo>();
        foreach (var sc in ServiceController.GetServices())
        {
            using (sc)
            {
                try { list.Add(Map(sc)); } catch { /* service vanished or access denied */ }
            }
        }
        return list;
    }

    private static ServiceInfo Map(ServiceController sc)
    {
        var state = sc.Status switch
        {
            ServiceControllerStatus.Running => ServiceState.Running,
            ServiceControllerStatus.Stopped => ServiceState.Stopped,
            ServiceControllerStatus.StartPending => ServiceState.StartPending,
            ServiceControllerStatus.StopPending => ServiceState.StopPending,
            ServiceControllerStatus.Paused => ServiceState.Paused,
            ServiceControllerStatus.PausePending => ServiceState.PausePending,
            ServiceControllerStatus.ContinuePending => ServiceState.ContinuePending,
            _ => ServiceState.Unknown
        };
        ServiceStartMode mode;
        try
        {
            mode = sc.StartType switch
            {
                System.ServiceProcess.ServiceStartMode.Automatic => ServiceStartMode.Automatic,
                System.ServiceProcess.ServiceStartMode.Manual => ServiceStartMode.Manual,
                System.ServiceProcess.ServiceStartMode.Disabled => ServiceStartMode.Disabled,
                System.ServiceProcess.ServiceStartMode.Boot => ServiceStartMode.Boot,
                System.ServiceProcess.ServiceStartMode.System => ServiceStartMode.System,
                _ => ServiceStartMode.Unknown
            };
        }
        catch { mode = ServiceStartMode.Unknown; }
        return new ServiceInfo(sc.ServiceName, sc.DisplayName, state, mode);
    }
}

public sealed class EventLogProbe : IEventLogProbe
{
    public Task<EventQueryResult> QueryAsync(string logName, TimeSpan window, int maxEvents, bool includeWarnings,
        CancellationToken cancellationToken, IReadOnlyCollection<int>? eventIds = null)
        => Task.Run(() => Query(logName, window, maxEvents, includeWarnings, cancellationToken, eventIds), cancellationToken);

    public static string BuildXPath(TimeSpan window, bool includeWarnings, IReadOnlyCollection<int>? eventIds)
    {
        var levels = includeWarnings ? "Level=1 or Level=2 or Level=3" : "Level=1 or Level=2";
        var ms = (long)window.TotalMilliseconds;
        var ids = eventIds is { Count: > 0 } ? " and (" + string.Join(" or ", eventIds.Select(i => $"EventID={i}")) + ")" : "";
        // When explicit ids are requested, levels are not restricted (e.g. Security 4625 is "Information").
        var levelPart = eventIds is { Count: > 0 } ? "" : $"({levels}) and ";
        return $"*[System[{levelPart}TimeCreated[timediff(@SystemTime) <= {ms}]{ids}]]";
    }

    private static EventQueryResult Query(string logName, TimeSpan window, int maxEvents, bool includeWarnings,
        CancellationToken ct, IReadOnlyCollection<int>? eventIds)
    {
        if (!OperatingSystem.IsWindows())
            return new EventQueryResult { Log = logName, Available = false, Error = "Журналы событий Windows недоступны на этой ОС" };
        var events = new List<EventRecordInfo>();
        try
        {
            var query = new EventLogQuery(logName, PathType.LogName, BuildXPath(window, includeWarnings, eventIds)) { ReverseDirection = true };
            using var reader = new EventLogReader(query);
            for (var rec = reader.ReadEvent(); rec is not null && events.Count < maxEvents; rec = reader.ReadEvent())
            {
                using (rec)
                {
                    ct.ThrowIfCancellationRequested();
                    string message;
                    try { message = rec.FormatDescription() ?? ""; } catch { message = ""; }
                    if (string.IsNullOrWhiteSpace(message))
                        message = string.Join("; ", rec.Properties.Take(6).Select(p => p.Value?.ToString()));
                    events.Add(new EventRecordInfo(logName, rec.ProviderName ?? "", rec.Id, rec.Level ?? 0,
                        rec.TimeCreated is { } t ? new DateTimeOffset(t) : DateTimeOffset.MinValue, message.Trim()));
                }
            }
            return new EventQueryResult { Log = logName, Events = events };
        }
        catch (UnauthorizedAccessException ex)
        {
            return new EventQueryResult { Log = logName, AccessDenied = true, Error = ex.Message };
        }
        catch (EventLogNotFoundException ex)
        {
            return new EventQueryResult { Log = logName, Available = false, Error = ex.Message };
        }
        catch (EventLogException ex)
        {
            return new EventQueryResult { Log = logName, Available = false, Error = ex.Message, Events = events };
        }
    }
}

public sealed class RegistryProbe : IRegistryProbe
{
    private static RegistryKey? Open(RegistryHive hive, string path)
    {
        if (!OperatingSystem.IsWindows()) return null;
        var root = hive == RegistryHive.LocalMachine
            ? RegistryKey.OpenBaseKey(Microsoft.Win32.RegistryHive.LocalMachine, RegistryView.Registry64)
            : Registry.CurrentUser;
        return root.OpenSubKey(path, false);
    }

    public object? GetValue(RegistryHive hive, string path, string name)
    {
        try
        {
            using var key = Open(hive, path);
            return key?.GetValue(name);
        }
        catch { return null; }
    }

    public bool KeyExists(RegistryHive hive, string path)
    {
        try
        {
            using var key = Open(hive, path);
            return key is not null;
        }
        catch { return false; }
    }

    public IReadOnlyList<string> GetSubKeyNames(RegistryHive hive, string path)
    {
        try
        {
            using var key = Open(hive, path);
            return key?.GetSubKeyNames() ?? Array.Empty<string>();
        }
        catch { return Array.Empty<string>(); }
    }
}
