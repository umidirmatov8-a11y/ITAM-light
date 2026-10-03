using System.Diagnostics;
using System.Text.RegularExpressions;
using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;
using K = FirstAidAdmin.Core.Abstractions.InputKeys;

namespace FirstAidAdmin.Diagnostics.Application;

/// <summary>
/// "Программа не работает": file, access, process, crash events, network, related services.
/// The program is launched ONLY when the administrator explicitly allowed it (input app.allowLaunch = true).
/// </summary>
public sealed class ApplicationModule : DiagnosticModuleBase
{
    private readonly IFileSystemProbe _fs;
    private readonly IProcessLauncher _proc;
    private readonly IEventLogProbe _events;
    private readonly INetworkProbe _net;
    private readonly IServiceProbe _services;

    public ApplicationModule(IFileSystemProbe fs, IProcessLauncher proc, IEventLogProbe events, INetworkProbe net, IServiceProbe services)
    {
        _fs = fs;
        _proc = proc;
        _events = events;
        _net = net;
        _services = services;
    }

    public override string Id => ModuleIds.Application;
    public override string Name => "Программа";
    public override DiagnosticCategory Category => DiagnosticCategory.Application;
    public override IReadOnlyList<string> InputKeys => new[] { K.AppName, K.AppExe, K.AppAllowLaunch };

    /// <summary>Extracts the faulting module from an "Application Error" (1000) message, English or Russian.</summary>
    public static string? FaultingModule(string message)
    {
        var m = Regex.Match(message, @"(?:Faulting module name|Имя сбойного модуля|Имя модуля с ошибкой)\s*:\s*([^,\r\n]+)", RegexOptions.IgnoreCase);
        return m.Success ? m.Groups[1].Value.Trim() : null;
    }

    /// <summary>File name from a Windows or POSIX path regardless of the current OS.</summary>
    public static string FileNameAny(string path) => path.Split('\\', '/').Last();

    protected override async Task ExecuteAsync(DiagnosticResult root, DiagnosticContext ctx, CancellationToken ct)
    {
        var name = ctx.Input(K.AppName);
        var exe = ctx.Input(K.AppExe);
        if (name is null && exe is null)
        {
            Check(root, C.AppFile, "Программа", DiagnosticStatus.Skipped, "Не указано название программы или путь к EXE");
            return;
        }

        var lookup = exe ?? name!;
        var found = _fs.FindExecutable(lookup);
        var path = found.FirstOrDefault();
        var exeName = FileNameAny(path ?? (lookup.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ? lookup : lookup + ".exe"));
        var displayName = name ?? Path.GetFileNameWithoutExtension(exeName);

        if (path is null)
        {
            Check(root, C.AppFile, "Исполняемый файл", exe is not null ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                    exe is not null ? $"Файл не найден: {exe}" : $"«{lookup}» не найден в PATH и App Paths — укажите полный путь к EXE")
                .WithEvidence("lookup", lookup);
        }
        else
        {
            string version = "";
            try { var vi = FileVersionInfo.GetVersionInfo(path); version = $"{vi.ProductName} {vi.FileVersion}".Trim(); } catch { }
            Check(root, C.AppFile, "Исполняемый файл", DiagnosticStatus.Ok, $"{path}{(version.Length > 0 ? $" ({version})" : "")}")
                .WithEvidence("path", path).WithEvidence("version", version);

            var err = _fs.TryOpenRead(path);
            Check(root, C.AppAccess, "Права доступа к файлу", err is null ? DiagnosticStatus.Ok : DiagnosticStatus.Error,
                err is null ? "Текущий пользователь может прочитать файл" : $"Нет доступа: {err}");
        }

        var running = _proc.FindRunningProcesses(exeName);
        Check(root, C.AppProcess, "Процесс", DiagnosticStatus.Info,
            running.Count > 0 ? $"Запущено процессов {exeName}: {running.Count} (PID {string.Join(", ", running.Take(5))})" : $"{exeName} сейчас не запущен")
            .WithEvidence("count", running.Count);

        if (path is not null && string.Equals(ctx.Input(K.AppAllowLaunch), "true", StringComparison.OrdinalIgnoreCase))
        {
            var (started, exitedEarly, exit, error) = await _proc.LaunchAndObserveAsync(path, TimeSpan.FromSeconds(10), ct).ConfigureAwait(false);
            Check(root, C.AppLaunch, "Пробный запуск (разрешён администратором)",
                    !started ? DiagnosticStatus.Error : exitedEarly && exit != 0 ? DiagnosticStatus.Error : DiagnosticStatus.Ok,
                    !started ? $"Не запускается: {error}"
                    : exitedEarly ? $"Процесс завершился в первые 10 с с кодом {exit} (0x{exit:X8})"
                    : "Процесс запустился и работает")
                .WithEvidence("exitCode", exit);
        }
        else
        {
            Skipped(root, C.AppLaunch, "Пробный запуск", "Запуск программы не разрешён (по умолчанию программа не запускается)");
        }

        // Crash / hang events of this executable
        var ev = await _events.QueryAsync("Application", TimeSpan.FromDays(7), 500, false, ct, new[] { 1000, 1002, 1026 }).ConfigureAwait(false);
        if (ev.Available && !ev.AccessDenied)
        {
            var mine = ev.Events.Where(e => e.Message.Contains(exeName, StringComparison.OrdinalIgnoreCase)).ToList();
            var module = mine.Select(e => FaultingModule(e.Message)).FirstOrDefault(m => m is not null);
            var c = Check(root, C.AppEvents, "Сбои в журнале Application (7 дней)",
                    mine.Count == 0 ? DiagnosticStatus.Ok : mine.Count >= 3 ? DiagnosticStatus.Error : DiagnosticStatus.Warning,
                    mine.Count == 0 ? $"Сбоев {exeName} не зарегистрировано"
                                    : $"Сбоев/зависаний: {mine.Count}; последнее {mine[0].TimeCreated.ToLocalTime():dd.MM.yyyy HH:mm}{(module is null ? "" : $"; модуль: {module}")}")
                .WithEvidence("count", mine.Count).WithEvidence("faultingModule", module);
            foreach (var e in mine.Take(5)) c.WithEvidence($"{e.TimeCreated.ToLocalTime():dd.MM HH:mm} {e.Provider} {e.EventId}", e.Message.Split('\n')[0]);
            if (mine.Count > 0) c.WithRecommendation("Восстановите/переустановите программу; проверьте обновления и надстройки.", A.OpenEventViewer);
        }

        // Network (most business apps need it)
        var tcp = await _net.TcpConnectAsync(ctx.Settings.Diagnostics.InternetProbeIps.LastOrDefault() ?? "1.1.1.1", 443, ctx.Settings.Diagnostics.TcpTimeoutMs, ct).ConfigureAwait(false);
        Check(root, C.AppNetwork, "Сетевое подключение", tcp.Success ? DiagnosticStatus.Ok : DiagnosticStatus.Warning,
            tcp.Success ? "Внешние HTTPS-подключения работают" : "Внешние HTTPS-подключения не проходят — сетевым программам может быть недоступен сервер");

        // Related services (by name match)
        var token = Path.GetFileNameWithoutExtension(displayName);
        if (token.Length >= 3)
        {
            var related = _services.GetAll().Where(s => s.Name.Contains(token, StringComparison.OrdinalIgnoreCase) || s.DisplayName.Contains(token, StringComparison.OrdinalIgnoreCase)).ToList();
            if (related.Count > 0)
            {
                var stopped = related.Where(s => s.State != ServiceState.Running && s.StartMode == ServiceStartMode.Automatic).ToList();
                var c = Check(root, C.AppServices, "Связанные службы", stopped.Count > 0 ? DiagnosticStatus.Error : DiagnosticStatus.Ok,
                    stopped.Count > 0 ? $"Не запущены: {string.Join(", ", stopped.Select(s => s.DisplayName))}" : $"Найдено служб: {related.Count}, автоматические работают");
                foreach (var s in related) c.WithEvidence(s.Name, $"{s.State}; {s.StartMode}");
                if (stopped.Count > 0) c.WithRecommendation("Запустите связанные службы.", A.StartService, A.OpenServices);
            }
        }
    }
}
