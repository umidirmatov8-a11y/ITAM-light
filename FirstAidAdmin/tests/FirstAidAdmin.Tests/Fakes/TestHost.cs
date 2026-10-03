using FirstAidAdmin.Application;
using FirstAidAdmin.Application.Cli;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Cases;
using FirstAidAdmin.Core.Settings;
using FirstAidAdmin.Remediation;
using Microsoft.Extensions.DependencyInjection;

namespace FirstAidAdmin.Tests.Fakes;

/// <summary>Builds the real DI graph with fake OS probes (same core as GUI/CLI).</summary>
public sealed class TestHost : IDisposable
{
    public FakeNetworkProbe Network { get; init; } = FakeNetworkProbe.Healthy();
    public FakeCommandRunner Commands { get; } = new();
    public FakePowerShell PowerShell { get; } = new();
    public FakeServiceProbe Services { get; init; } = FakeServiceProbe.Healthy();
    public FakeEventLogProbe Events { get; } = new();
    public FakeRegistry Registry { get; } = new();
    public FakeSystemProbe System { get; } = new();
    public FakeFileSystem FileSystem { get; } = new();
    public FakeProcessLauncher Processes { get; } = new();
    public IConfirmationService Confirmation { get; set; } = new NonInteractiveConfirmationService();
    public IElevationService? Elevation { get; set; }
    public IShellLauncher? Shell { get; set; }
    public string DataFolder { get; } = Path.Combine(Path.GetTempPath(), "faa-tests-" + Guid.NewGuid().ToString("N"));
    public AppSettings Settings { get; } = new();

    private ServiceProvider? _provider;

    public ServiceProvider Provider => _provider ??= Build();

    private ServiceProvider Build()
    {
        Directory.CreateDirectory(DataFolder);
        Settings.Reports.ReportFolder = Path.Combine(DataFolder, "Reports");
        var services = new ServiceCollection();
        services.AddSingleton<INetworkProbe>(Network);
        services.AddSingleton<ICommandRunner>(Commands);
        services.AddSingleton<IPowerShellRunner>(PowerShell);
        services.AddSingleton<IServiceProbe>(Services);
        services.AddSingleton<IEventLogProbe>(Events);
        services.AddSingleton<IRegistryProbe>(Registry);
        services.AddSingleton<ISystemProbe>(System);
        services.AddSingleton<IFileSystemProbe>(FileSystem);
        services.AddSingleton<IProcessLauncher>(Processes);
        services.AddSingleton<ICaseStore>(new FileCaseStore(Path.Combine(DataFolder, "Cases")));
        services.AddSingleton(Confirmation);
        if (Elevation is not null) services.AddSingleton(Elevation);
        if (Shell is not null) services.AddSingleton(Shell);
        services.AddFirstAidAdmin(Settings, Path.Combine(DataFolder, "Logs"));
        return services.BuildServiceProvider();
    }

    public DiagnosticSession Session => Provider.GetRequiredService<DiagnosticSession>();
    public T Get<T>() where T : notnull => Provider.GetRequiredService<T>();

    public void Dispose()
    {
        _provider?.Dispose();
        try { Directory.Delete(DataFolder, true); } catch { }
    }
}
