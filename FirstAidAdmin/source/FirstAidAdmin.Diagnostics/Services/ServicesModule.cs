using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Diagnostics.Services;

public static class ServiceAnalyzer
{
    /// <summary>Services that should be running on a healthy workstation.</summary>
    public static readonly IReadOnlyDictionary<string, string> Critical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["RpcSs"] = "RPC", ["EventLog"] = "Журнал событий", ["Winmgmt"] = "WMI", ["Dhcp"] = "DHCP-клиент",
        ["Dnscache"] = "DNS-клиент", ["NlaSvc"] = "Сетевое расположение", ["LanmanWorkstation"] = "Рабочая станция (SMB-клиент)",
        ["BFE"] = "Base Filtering Engine", ["mpssvc"] = "Брандмауэр Windows", ["CryptSvc"] = "Службы криптографии",
        ["Schedule"] = "Планировщик заданий", ["ProfSvc"] = "Профили пользователей", ["Power"] = "Питание", ["PlugPlay"] = "Plug and Play",
    };

    public static readonly IReadOnlyDictionary<string, string> DomainCritical = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["Netlogon"] = "Netlogon", ["W32Time"] = "Служба времени Windows",
    };

    /// <summary>Automatic services that are commonly stopped by design (trigger start / run on demand).</summary>
    private static readonly string[] BenignStopped =
    {
        "gupdate", "edgeupdate", "MapsBroker", "sppsvc", "RemoteRegistry", "wuauserv", "BITS", "TrustedInstaller", "WbioSrvc",
        "clr_optimization", "ShellHWDetection", "tiledatamodelsvc", "GoogleUpdater", "MozillaMaintenance", "CDPSvc", "OneSyncSvc",
        "UsoSvc", "WaaSMedicSvc", "DoSvc", "StateRepository", "Intel(R) TPM Provisioning Service", "sedsvc", "dbupdate", "AdobeARMservice",
    };

    public static bool IsBenign(string name) => BenignStopped.Any(b => name.StartsWith(b, StringComparison.OrdinalIgnoreCase)) || name.Contains('_');

    public static List<ServiceInfo> StoppedCritical(IEnumerable<ServiceInfo> all, bool domainJoined)
    {
        var list = all.ToList();
        var names = Critical.Keys.Concat(domainJoined ? DomainCritical.Keys : Array.Empty<string>());
        return names
            .Select(n => list.FirstOrDefault(s => s.Name.Equals(n, StringComparison.OrdinalIgnoreCase)))
            // Demand/trigger-start services (e.g. NlaSvc on recent builds) may legitimately be stopped:
            // only automatic or disabled ones are a problem.
            .Where(s => s is not null && s.State != ServiceState.Running && s.State != ServiceState.StartPending
                        && s.StartMode is ServiceStartMode.Automatic or ServiceStartMode.Disabled)
            .Cast<ServiceInfo>()
            .ToList();
    }

    public static List<ServiceInfo> AutoNotRunning(IEnumerable<ServiceInfo> all)
        => all.Where(s => s.StartMode == ServiceStartMode.Automatic && s.State == ServiceState.Stopped && !IsBenign(s.Name)).ToList();
}

public sealed class ServicesModule : DiagnosticModuleBase
{
    private readonly IServiceProbe _services;

    public ServicesModule(IServiceProbe services) => _services = services;

    public override string Id => ModuleIds.Services;
    public override string Name => "Службы Windows";
    public override DiagnosticCategory Category => DiagnosticCategory.Services;
    public override IReadOnlyList<string> InputKeys => new[] { Core.Abstractions.InputKeys.ServiceName };

    protected override Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var all = _services.GetAll();
        if (all.Count == 0)
        {
            root.Status = DiagnosticStatus.Skipped;
            root.Summary = "Список служб недоступен на этой системе";
            return Task.CompletedTask;
        }

        var stopped = ServiceAnalyzer.StoppedCritical(all, ctx.System.IsDomainJoined);
        var crit = Check(root, C.ServicesCritical, "Важные системные службы", stopped.Count == 0 ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
            stopped.Count == 0 ? $"Все важные службы работают ({ServiceAnalyzer.Critical.Count + (ctx.System.IsDomainJoined ? ServiceAnalyzer.DomainCritical.Count : 0)})"
                               : $"Не работают: {string.Join(", ", stopped.Select(s => $"{s.Name} ({s.State}, {s.StartMode})"))}");
        foreach (var s in stopped) crit.WithEvidence(s.Name, $"{s.DisplayName}: {s.State}; {s.StartMode}");
        if (stopped.Count > 0) crit.WithRecommendation("Запустите службы и выясните причину остановки в журнале System.", A.StartService, A.OpenServices);

        var auto = ServiceAnalyzer.AutoNotRunning(all);
        var autoCheck = Check(root, C.ServicesAutoStopped, "Автоматические службы, которые не запущены",
            auto.Count == 0 ? DiagnosticStatus.Ok : auto.Count > 5 ? DiagnosticStatus.Warning : DiagnosticStatus.Info,
            auto.Count == 0 ? "Все автоматические службы запущены" : $"Не запущено: {auto.Count} ({string.Join(", ", auto.Take(8).Select(s => s.Name))}{(auto.Count > 8 ? ", …" : "")})");
        foreach (var s in auto.Take(30)) autoCheck.WithEvidence(s.Name, s.DisplayName);

        var target = ctx.Input(Core.Abstractions.InputKeys.ServiceName);
        if (target is not null)
        {
            var s = all.FirstOrDefault(x => x.Name.Equals(target, StringComparison.OrdinalIgnoreCase) || x.DisplayName.Equals(target, StringComparison.OrdinalIgnoreCase))
                    ?? all.FirstOrDefault(x => x.DisplayName.Contains(target, StringComparison.OrdinalIgnoreCase));
            if (s is null)
                Check(root, C.ServicesTarget, $"Служба «{target}»", DiagnosticStatus.Error, "Служба не найдена");
            else
            {
                var st = s.State == ServiceState.Running ? DiagnosticStatus.Ok : s.StartMode == ServiceStartMode.Disabled ? DiagnosticStatus.Error : DiagnosticStatus.Error;
                Check(root, C.ServicesTarget, $"Служба «{s.DisplayName}»", st, $"{s.Name}: {s.State}, тип запуска {s.StartMode}")
                    .WithEvidence("service", s.Name)
                    .WithRecommendation(st == DiagnosticStatus.Ok ? "" : s.StartMode == ServiceStartMode.Disabled
                        ? "Служба отключена: проверьте, не отключена ли она политикой, и смените тип запуска вручную."
                        : "Запустите (перезапустите) службу.", st == DiagnosticStatus.Ok ? Array.Empty<string>() : new[] { A.RestartService, A.OpenServices });
            }
        }
        return Task.CompletedTask;
    }
}
