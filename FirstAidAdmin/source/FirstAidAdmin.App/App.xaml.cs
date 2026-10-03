using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Threading;
using FirstAidAdmin.App.Services;
using FirstAidAdmin.App.ViewModels;
using FirstAidAdmin.Application;
using FirstAidAdmin.Application.Cli;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.KnowledgeBase;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace FirstAidAdmin.App;

public partial class App : System.Windows.Application
{
    private ServiceProvider? _services;

    [DllImport("kernel32.dll")]
    private static extern bool AttachConsole(int processId);

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // ── CLI mode: same diagnostic core, no window ──
        if (CliRunner.IsCliInvocation(e.Args))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            var code = await RunCliAsync(e.Args);
            Shutdown(code);
            return;
        }

        var smoke = e.Args.Any(a => a.Equals("--smoke-test", StringComparison.OrdinalIgnoreCase));
        var services = new ServiceCollection();
        services.AddSingleton<IConfirmationService, WpfConfirmationService>();
        services.AddSingleton<IDialogService, DialogService>();
        services.AddSingleton<IThemeService, ThemeService>();
        services.AddFirstAidAdmin();
        services.AddSingleton<MainViewModel>();
        _services = services.BuildServiceProvider();

        var logger = _services.GetRequiredService<ILoggerFactory>().CreateLogger("App");
        DispatcherUnhandledException += (_, args) =>
        {
            logger.LogError(args.Exception, "Unhandled UI exception");
            if (!smoke) MessageBox.Show(args.Exception.Message, "Первая помощь сисадмина — ошибка", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = !smoke;
        };

        var session = _services.GetRequiredService<DiagnosticSession>();
        _services.GetRequiredService<IThemeService>().Apply(session.Settings.General.Theme);
        var vm = _services.GetRequiredService<MainViewModel>();
        vm.Initialize(); // fast: OS, host, user, admin, basic network — no heavy diagnostics at startup
        var window = new MainWindow { DataContext = vm };
        MainWindow = window;
        window.Show();
        logger.LogInformation("FirstAidAdmin started (admin={IsAdmin})", session.System.IsAdmin);

        if (smoke) await SmokeTest.RunAsync(window, vm, _services);
    }

    private static async Task<int> RunCliAsync(string[] args)
    {
        // A GUI-subsystem exe has no console: attach to the parent console unless output is redirected.
        if (!Console.IsOutputRedirected) AttachConsole(-1);
        try { Console.OutputEncoding = new UTF8Encoding(false); } catch { /* no console */ }
        var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true };

        var services = new ServiceCollection();
        services.AddSingleton<IConfirmationService, NonInteractiveConfirmationService>(); // CLI never changes the system
        services.AddFirstAidAdmin();
        await using var provider = services.BuildServiceProvider();
        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, ev) => { ev.Cancel = true; cts.Cancel(); };
        var code = await new CliRunner(provider.GetRequiredService<DiagnosticSession>(), stdout).RunAsync(args, cts.Token);
        await stdout.FlushAsync();
        return code;
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _services?.Dispose();
        base.OnExit(e);
    }
}

/// <summary>
/// Hidden "--smoke-test" mode used by CI on Windows: opens every view (home, help-desk, a scenario, case, settings),
/// renders each to PNG and exits. Catches XAML/binding/resource errors that compile-time checks cannot.
/// </summary>
internal static class SmokeTest
{
    public static async Task RunAsync(MainWindow window, MainViewModel vm, IServiceProvider services)
    {
        var outDir = Path.Combine(Environment.GetEnvironmentVariable("FIRSTAIDADMIN_SMOKE_OUT") ?? Path.Combine(Path.GetTempPath(), "faa-smoke"));
        Directory.CreateDirectory(outDir);
        var exitCode = 0;
        try
        {
            await Snap(window, outDir, "1-home");
            vm.ToggleModeCommand.Execute(null);
            await Snap(window, outDir, "2-helpdesk");
            vm.ToggleModeCommand.Execute(null);
            var scenario = Core.Scenarios.ScenarioCatalog.Get(Core.Models.ProblemScenario.Rdp); // has inputs → does not auto start
            vm.Current = new RunViewModel(scenario, services.GetRequiredService<DiagnosticSession>(), services.GetRequiredService<IDialogService>(), services.GetRequiredService<KnowledgeBaseService>(), () => { });
            await Snap(window, outDir, "3-run");
            ((RunViewModel)vm.Current).RdpTarget = "127.0.0.1";
            await ((RunViewModel)vm.Current).StartCommand.ExecuteAsync(null);
            await Snap(window, outDir, "4-run-results");
            vm.OpenCaseCommand.Execute(null);
            await Snap(window, outDir, "5-case");
            vm.OpenSettingsCommand.Execute(null);
            await Snap(window, outDir, "6-settings");
            vm.ToggleThemeCommand.Execute(null);
            vm.GoHomeCommand.Execute(null);
            await Snap(window, outDir, "7-home-dark");
            vm.ToggleThemeCommand.Execute(null);
            Console.WriteLine("SMOKE OK " + outDir);
        }
        catch (Exception ex)
        {
            File.WriteAllText(Path.Combine(outDir, "smoke-error.txt"), ex.ToString());
            exitCode = 1;
        }
        System.Windows.Application.Current.Shutdown(exitCode);
    }

    private static async Task Snap(Window w, string dir, string name)
    {
        await w.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
        await Task.Delay(400);
        await w.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
        var element = (FrameworkElement)w.Content;
        var width = (int)Math.Max(1, element.ActualWidth);
        var height = (int)Math.Max(1, element.ActualHeight);
        var bmp = new System.Windows.Media.Imaging.RenderTargetBitmap(width, height, 96, 96, System.Windows.Media.PixelFormats.Pbgra32);
        bmp.Render(element);
        var enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
        enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
        await using var fs = File.Create(Path.Combine(dir, name + ".png"));
        enc.Save(fs);
    }
}
