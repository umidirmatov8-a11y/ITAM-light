using FirstAidAdmin.Core.Abstractions;
using FirstAidAdmin.Core.Models;

namespace FirstAidAdmin.Core.Scenarios;

public sealed record ScenarioDefinition(
    ProblemScenario Scenario,
    string Icon,
    string Title,
    string Description,
    IReadOnlyList<string> Modules,
    IReadOnlyList<string> RequiredInputs,
    IReadOnlyList<string> OptionalInputs,
    bool HelpDesk);

/// <summary>Maps "what happened" to the set of diagnostic modules that the program runs by itself.</summary>
public static class ScenarioCatalog
{
    private static readonly string[] Quick =
    {
        ModuleIds.Network, ModuleIds.Dns, ModuleIds.Storage, ModuleIds.Performance,
        ModuleIds.Security, ModuleIds.Services, ModuleIds.EventLog
    };

    public static readonly IReadOnlyList<ScenarioDefinition> All = new List<ScenarioDefinition>
    {
        new(ProblemScenario.NoInternet, "🌐", "Нет интернета", "Адаптер, IP, шлюз, Интернет по IP, DNS, прокси, маршруты",
            new[] { ModuleIds.Network, ModuleIds.Dns, ModuleIds.WiFi }, Array.Empty<string>(), Array.Empty<string>(), true),
        new(ProblemScenario.SlowComputer, "🐌", "Компьютер тормозит", "CPU, RAM, диск, uptime, автозагрузка, службы",
            new[] { ModuleIds.Performance, ModuleIds.Storage, ModuleIds.Services, ModuleIds.EventLog }, Array.Empty<string>(), Array.Empty<string>(), true),
        new(ProblemScenario.CannotLogin, "🔐", "Не могу войти", "Домен, безопасный канал, DNS, Kerberos, время, неудачные входы",
            new[] { ModuleIds.Network, ModuleIds.Dns, ModuleIds.Domain, ModuleIds.ActiveDirectory }, Array.Empty<string>(), Array.Empty<string>(), true),
        new(ProblemScenario.Rdp, "🖥", "RDP не работает", "TermService, порт 3389, брандмауэр, NLA, доступность цели",
            new[] { ModuleIds.Rdp, ModuleIds.Network }, Array.Empty<string>(), new[] { InputKeys.RdpTarget, InputKeys.RdpPort }, true),
        new(ProblemScenario.Printer, "🖨", "Принтер не работает", "Spooler, очередь, принтеры, сетевой принтер",
            new[] { ModuleIds.Printer }, Array.Empty<string>(), Array.Empty<string>(), true),
        new(ProblemScenario.WindowsUpdate, "🔄", "Windows Update", "Службы WU/BITS, история, ошибки, место на диске",
            new[] { ModuleIds.WindowsUpdate, ModuleIds.Storage, ModuleIds.Network, ModuleIds.Dns, ModuleIds.WindowsHealth }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.Disk, "💾", "Проблемы с диском", "Свободное место, временные файлы, состояние и ошибки дисков",
            new[] { ModuleIds.Storage }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.WindowsErrors, "🛠", "Ошибки Windows", "DISM, CBS, сбои, анализ журналов событий",
            new[] { ModuleIds.WindowsHealth, ModuleIds.EventLog, ModuleIds.Services }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.WiFi, "📡", "Проблемы Wi-Fi", "SSID, сигнал, канал, скорость, этап отказа",
            new[] { ModuleIds.WiFi, ModuleIds.Network, ModuleIds.Dns }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.Dns, "🌐", "Проблемы с DNS", "DNS-серверы, внешние/внутренние имена, SRV, кэш",
            new[] { ModuleIds.Dns, ModuleIds.Network }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.Domain, "🏢", "Диагностика домена", "Домен, DC, Logon Server, Secure Channel, Kerberos, время, GPO",
            new[] { ModuleIds.Domain, ModuleIds.ActiveDirectory, ModuleIds.Dns }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.ApplicationNotWorking, "📦", "Не работает программа", "Файл, процесс, журнал событий, права, сеть",
            new[] { ModuleIds.Application }, Array.Empty<string>(), new[] { InputKeys.AppName, InputKeys.AppExe }, true),
        new(ProblemScenario.NetworkShare, "🗂", "Не работает сетевой ресурс", "Имя сервера, ping, SMB 445, доступ к папке",
            new[] { ModuleIds.NetworkShare, ModuleIds.Network, ModuleIds.Dns }, new[] { InputKeys.SharePath }, Array.Empty<string>(), false),
        new(ProblemScenario.ServiceNotWorking, "⚙", "Не работает служба", "Состояние важных служб и указанной службы",
            new[] { ModuleIds.Services, ModuleIds.EventLog }, Array.Empty<string>(), new[] { InputKeys.ServiceName }, false),
        new(ProblemScenario.SlowBoot, "⏱", "Долго загружается", "Время загрузки, автозагрузка, службы, диск",
            new[] { ModuleIds.Performance, ModuleIds.Storage, ModuleIds.Services }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.Security, "🛡", "Безопасность", "Defender, брандмауэр, UAC, сигнатуры",
            new[] { ModuleIds.Security }, Array.Empty<string>(), Array.Empty<string>(), false),
        new(ProblemScenario.FirstResponse, "🚑", "FIRST RESPONSE", "Быстрая первичная картина за 1–3 минуты",
            Quick, Array.Empty<string>(), Array.Empty<string>(), true),
        new(ProblemScenario.FullDiagnostics, "🩺", "Полная диагностика", "Все модули, кроме длительных SFC/DISM ScanHealth",
            new[]
            {
                ModuleIds.Network, ModuleIds.Dns, ModuleIds.WiFi, ModuleIds.Domain, ModuleIds.ActiveDirectory, ModuleIds.Rdp,
                ModuleIds.Printer, ModuleIds.WindowsUpdate, ModuleIds.Storage, ModuleIds.WindowsHealth, ModuleIds.Security,
                ModuleIds.Performance, ModuleIds.Services, ModuleIds.EventLog
            }, Array.Empty<string>(), Array.Empty<string>(), true),
    };

    public static ScenarioDefinition Get(ProblemScenario scenario) => All.First(s => s.Scenario == scenario);

    /// <summary>Parses a CLI/user token ("network", "dns", "full", ...) into a scenario.</summary>
    public static ProblemScenario? Parse(string token)
    {
        var t = token.Trim().TrimStart('/', '-').ToLowerInvariant();
        return t switch
        {
            "diagnose" or "full" or "all" => ProblemScenario.FullDiagnostics,
            "firstresponse" or "first-response" or "quick" => ProblemScenario.FirstResponse,
            "network" or "internet" or "nointernet" => ProblemScenario.NoInternet,
            "dns" => ProblemScenario.Dns,
            "wifi" or "wi-fi" => ProblemScenario.WiFi,
            "domain" or "ad" => ProblemScenario.Domain,
            "login" or "logon" => ProblemScenario.CannotLogin,
            "rdp" => ProblemScenario.Rdp,
            "printer" or "print" => ProblemScenario.Printer,
            "update" or "windowsupdate" or "wu" => ProblemScenario.WindowsUpdate,
            "disk" or "storage" => ProblemScenario.Disk,
            "health" or "errors" or "windowserrors" => ProblemScenario.WindowsErrors,
            "performance" or "slow" or "perf" => ProblemScenario.SlowComputer,
            "boot" or "slowboot" => ProblemScenario.SlowBoot,
            "app" or "application" => ProblemScenario.ApplicationNotWorking,
            "share" => ProblemScenario.NetworkShare,
            "service" or "services" => ProblemScenario.ServiceNotWorking,
            "security" => ProblemScenario.Security,
            _ => Enum.TryParse<ProblemScenario>(t, true, out var s) ? s : null
        };
    }
}
