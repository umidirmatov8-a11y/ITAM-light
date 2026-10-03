using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Analysis;
using FirstAidAdmin.Core.Cases;
using FirstAidAdmin.Core.Correlation;
using FirstAidAdmin.Core.Engine;
using FirstAidAdmin.Core.KnowledgeBase;
using FirstAidAdmin.Core.Plugins;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Diagnostics.ActiveDirectory;
using FirstAidAdmin.Diagnostics.Application;
using FirstAidAdmin.Diagnostics.Dns;
using FirstAidAdmin.Diagnostics.Domain;
using FirstAidAdmin.Diagnostics.EventLog;
using FirstAidAdmin.Diagnostics.Network;
using FirstAidAdmin.Diagnostics.NetworkShare;
using FirstAidAdmin.Diagnostics.Performance;
using FirstAidAdmin.Diagnostics.Printer;
using FirstAidAdmin.Diagnostics.Rdp;
using FirstAidAdmin.Diagnostics.Security;
using FirstAidAdmin.Diagnostics.Services;
using FirstAidAdmin.Diagnostics.Storage;
using FirstAidAdmin.Diagnostics.WiFi;
using FirstAidAdmin.Diagnostics.WindowsHealth;
using FirstAidAdmin.Diagnostics.WindowsUpdate;
using FirstAidAdmin.Infrastructure.Commands;
using FirstAidAdmin.Infrastructure.Network;
using FirstAidAdmin.Infrastructure.Windows;
using FirstAidAdmin.Logging;
using FirstAidAdmin.Remediation;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.Application;

public static class ServiceRegistration
{
    /// <summary>Registers the whole diagnostic core. UI/CLI register their own IConfirmationService.</summary>
    public static IServiceCollection AddFirstAidAdmin(this IServiceCollection services, AppSettings? settings = null, string? logFolder = null)
    {
        var settingsStore = new JsonSettingsStore();
        settings ??= settingsStore.Load();
        services.AddSingleton<ISettingsStore>(settingsStore);
        services.AddSingleton(settings);

        services.AddLogging(b =>
        {
            b.SetMinimumLevel(LogLevel.Information);
            b.AddProvider(new FileLoggerProvider(logFolder ?? AppPaths.Logs));
        });

        // Infrastructure (OS access)
        services.TryAddSingleton<ICommandLog, CommandLog>();
        services.TryAddSingleton<ICommandRunner, ProcessCommandRunner>();
        services.TryAddSingleton<IPowerShellRunner, PowerShellRunner>();
        services.TryAddSingleton<IRegistryProbe, RegistryProbe>();
        services.TryAddSingleton<INetworkProbe, NetworkProbe>();
        services.TryAddSingleton<IServiceProbe, ServiceProbe>();
        services.TryAddSingleton<IEventLogProbe, EventLogProbe>();
        services.TryAddSingleton<ISystemProbe>(sp => new SystemProbe(sp.GetRequiredService<INetworkProbe>()));
        services.TryAddSingleton<IFileSystemProbe, FileSystemProbe>();
        services.TryAddSingleton<IProcessLauncher, ProcessLauncher>();
        services.TryAddSingleton<IShellLauncher, ShellLauncher>();
        services.TryAddSingleton<IOperationExecutor>(sp => new OperationExecutor(sp.GetRequiredService<ICommandRunner>(), sp.GetRequiredService<IPowerShellRunner>(), sp.GetRequiredService<IShellLauncher>()));
        services.TryAddSingleton<IElevationService>(sp => new UacElevationService(sp.GetRequiredService<IOperationExecutor>()));

        // Diagnostic modules (built-in). Plugins are added in BuildRunner when enabled.
        services.AddSingleton<IDiagnosticModule, NetworkModule>();
        services.AddSingleton<IDiagnosticModule, DnsModule>();
        services.AddSingleton<IDiagnosticModule, WiFiModule>();
        services.AddSingleton<IDiagnosticModule, DomainModule>();
        services.AddSingleton<IDiagnosticModule, ActiveDirectoryModule>();
        services.AddSingleton<IDiagnosticModule, RdpModule>();
        services.AddSingleton<IDiagnosticModule, PrinterModule>();
        services.AddSingleton<IDiagnosticModule>(sp => new WindowsUpdateModule(sp.GetRequiredService<IServiceProbe>(), sp.GetRequiredService<IPowerShellRunner>(), sp.GetRequiredService<IEventLogProbe>(), sp.GetRequiredService<IRegistryProbe>()));
        services.AddSingleton<IDiagnosticModule, StorageModule>();
        services.AddSingleton<IDiagnosticModule, WindowsHealthModule>();
        services.AddSingleton<IDiagnosticModule, SfcModule>();
        services.AddSingleton<IDiagnosticModule, DismScanModule>();
        services.AddSingleton<IDiagnosticModule, SecurityModule>();
        services.AddSingleton<IDiagnosticModule, PerformanceModule>();
        services.AddSingleton<IDiagnosticModule, ServicesModule>();
        services.AddSingleton<IDiagnosticModule, EventLogModule>();
        services.AddSingleton<IDiagnosticModule, ApplicationModule>();
        services.AddSingleton<IDiagnosticModule, NetworkShareModule>();

        services.TryAddSingleton<IDiagnosticTarget, LocalDiagnosticTarget>();
        services.TryAddSingleton(sp =>
        {
            var modules = sp.GetServices<IDiagnosticModule>().ToList();
            var cfg = sp.GetRequiredService<AppSettings>();
            if (cfg.Diagnostics.LoadPlugins)
            {
                var loader = new PluginLoader();
                modules.AddRange(loader.LoadFrom(AppPaths.PluginsFolder));
                var log = sp.GetRequiredService<ILoggerFactory>().CreateLogger("Plugins");
                foreach (var r in loader.Reports)
                    log.LogInformation("Plugin {Path}: modules [{Modules}] {Error}", r.Path, string.Join(",", r.ModuleIds), r.Error);
            }
            return new DiagnosticRunner(modules, sp.GetRequiredService<IDiagnosticTarget>());
        });

        services.TryAddSingleton(_ => new CorrelationEngine()); // built-in rules (not the empty IEnumerable<ICorrelationRule> ctor)
        services.TryAddSingleton<IAnalysisProvider>(sp => new LocalRuleEngine(sp.GetRequiredService<CorrelationEngine>()));
        services.TryAddSingleton(sp => new OptionalAIProvider(sp.GetRequiredService<AppSettings>()));
        services.TryAddSingleton(_ => KnowledgeBaseService.LoadDefault());
        services.TryAddSingleton<ICaseStore>(_ => new FileCaseStore());
        services.TryAddSingleton<RemediationEngine>();
        services.TryAddSingleton<DiagnosticSession>();
        return services;
    }
}
