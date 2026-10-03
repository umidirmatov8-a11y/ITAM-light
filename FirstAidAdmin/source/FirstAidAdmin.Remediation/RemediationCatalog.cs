using FirstAidAdmin.Core;
using FirstAidAdmin.Core.Models;
using A = FirstAidAdmin.Core.ActionIds;
using C = FirstAidAdmin.Core.CheckIds;
using M = FirstAidAdmin.Core.ModuleIds;

namespace FirstAidAdmin.Remediation;

/// <summary>All actions the program can offer. Nothing here runs without explicit confirmation.</summary>
public static class RemediationCatalog
{
    private static RemediationAction Tool(string id, string title, string target) => new()
    {
        Id = id, Title = title, Description = $"Открыть стандартный инструмент Windows: {target}", WhatChanges = "Ничего не меняет — только открывает окно",
        Risk = RiskLevel.Low, Kind = RemediationKind.OpenTool, CommandPreview = target, Reversible = true
    };

    public static readonly IReadOnlyList<RemediationAction> All = new List<RemediationAction>
    {
        // ── LOW ──
        new() { Id = A.FlushDns, Title = "Очистить кэш DNS", Description = "Удаляет устаревшие записи из кэша DNS-клиента.",
            WhatChanges = "Кэш DNS будет пуст; имена разрешатся заново. Настройки не меняются.", Risk = RiskLevel.Low, CommandPreview = "ipconfig /flushdns",
            Reversible = true, RetestModuleIds = new[] { M.Dns, M.Network }, VerifyCheckIds = new[] { C.DnsResolveExternal, C.NetDnsResolve } },
        new() { Id = A.DismCheckHealth, Title = "Проверить хранилище компонентов (DISM CheckHealth)", Description = "Быстрая проверка образа Windows (только чтение).",
            WhatChanges = "Ничего не меняет.", Risk = RiskLevel.Low, RequiresAdmin = true, CommandPreview = "DISM /Online /Cleanup-Image /CheckHealth", Reversible = true },
        new() { Id = A.DismScanHealth, Title = "Сканировать хранилище компонентов (DISM ScanHealth)", Description = "Глубокая проверка образа Windows (только чтение), 5–20 минут.",
            WhatChanges = "Ничего не меняет.", Risk = RiskLevel.Low, RequiresAdmin = true, IsLongRunning = true, CommandPreview = "DISM /Online /Cleanup-Image /ScanHealth", Reversible = true },
        new() { Id = A.SfcVerify, Title = "Проверить системные файлы (SFC /verifyonly)", Description = "Проверка целостности без исправления, 5–20 минут.",
            WhatChanges = "Ничего не меняет.", Risk = RiskLevel.Low, RequiresAdmin = true, IsLongRunning = true, CommandPreview = "sfc /verifyonly", Reversible = true },
        new() { Id = A.DefenderUpdateSignatures, Title = "Обновить сигнатуры Microsoft Defender", Description = "Загружает актуальные антивирусные базы.",
            WhatChanges = "Обновятся антивирусные базы.", Risk = RiskLevel.Low, RequiresAdmin = true, CommandPreview = "Update-MpSignature",
            RetestModuleIds = new[] { M.Security }, VerifyCheckIds = new[] { C.SecSignatures } },

        // ── MEDIUM ──
        new() { Id = A.RegisterDns, Title = "Перерегистрировать DNS-имя компьютера", Description = "Повторно регистрирует A/PTR-записи компьютера на DNS-сервере.",
            WhatChanges = "Компьютер обновит свои записи в DNS.", Risk = RiskLevel.Medium, RequiresAdmin = true, CommandPreview = "ipconfig /registerdns",
            RetestModuleIds = new[] { M.Dns }, VerifyCheckIds = new[] { C.DnsResolveInternal } },
        new() { Id = A.RenewIp, Title = "Обновить IP-адрес (DHCP)", Description = "Запрашивает у DHCP-сервера новый адрес.",
            WhatChanges = "Сетевое подключение может кратковременно прерваться (несколько секунд).", Risk = RiskLevel.Medium, RequiresAdmin = true,
            CommandPreview = "ipconfig /renew", RetestModuleIds = new[] { M.Network }, VerifyCheckIds = new[] { C.NetIPv4, C.NetGatewayPing } },
        new() { Id = A.RestartSpooler, Title = "Перезапустить Print Spooler", Description = "Перезапускает диспетчер очереди печати.",
            WhatChanges = "Печать будет недоступна несколько секунд; текущие задания могут быть прерваны.", Risk = RiskLevel.Medium, RequiresAdmin = true,
            CommandPreview = "Restart-Service Spooler -Force", RetestModuleIds = new[] { M.Printer }, VerifyCheckIds = new[] { C.PrinterSpooler, C.PrinterQueue } },
        new() { Id = A.ClearPrintQueue, Title = "Очистить очередь печати", Description = "Останавливает Spooler, удаляет файлы заданий и запускает службу снова.",
            WhatChanges = "ВСЕ задания печати будут удалены без печати.", Risk = RiskLevel.Medium, RequiresAdmin = true,
            CommandPreview = "Stop-Service Spooler; Remove-Item %windir%\\System32\\spool\\PRINTERS\\*; Start-Service Spooler",
            RetestModuleIds = new[] { M.Printer }, VerifyCheckIds = new[] { C.PrinterQueue, C.PrinterSpooler } },
        new() { Id = A.RestartService, Title = "Перезапустить службу", Description = "Перезапускает выбранную службу (только из разрешённого списка).",
            WhatChanges = "Служба будет кратковременно остановлена.", Risk = RiskLevel.Medium, RequiresAdmin = true, Parameter = "service",
            CommandPreview = "Restart-Service <name> -Force", RetestModuleIds = new[] { M.Services }, VerifyCheckIds = new[] { C.ServicesTarget, C.ServicesCritical } },
        new() { Id = A.StartService, Title = "Запустить службу", Description = "Запускает остановленную службу (только из разрешённого списка).",
            WhatChanges = "Служба будет запущена. Тип запуска не меняется.", Risk = RiskLevel.Medium, RequiresAdmin = true, Parameter = "service",
            CommandPreview = "Start-Service <name>", RetestModuleIds = new[] { M.Services }, VerifyCheckIds = new[] { C.ServicesCritical, C.ServicesTarget } },
        new() { Id = A.RestartWindowsUpdate, Title = "Перезапустить службы Windows Update", Description = "Перезапускает wuauserv, BITS и CryptSvc.",
            WhatChanges = "Текущая загрузка обновлений будет прервана и продолжится позже.", Risk = RiskLevel.Medium, RequiresAdmin = true,
            CommandPreview = "Restart-Service wuauserv,BITS,CryptSvc -Force", RetestModuleIds = new[] { M.WindowsUpdate }, VerifyCheckIds = new[] { C.WuService, C.WuBits } },
        new() { Id = A.ClearUserTemp, Title = "Очистить временные файлы пользователя (старше 7 дней)", Description = "Удаляет из %TEMP% файлы старше 7 дней; занятые файлы пропускаются.",
            WhatChanges = "Будут удалены старые временные файлы текущего пользователя. Документы не затрагиваются.", Risk = RiskLevel.Medium,
            CommandPreview = "Remove %TEMP%\\* (older than 7 days)", RetestModuleIds = new[] { M.Storage }, VerifyCheckIds = new[] { C.StorageSystem, C.StorageTemp } },
        new() { Id = A.TimeResync, Title = "Синхронизировать время", Description = "Принудительная синхронизация времени с источником.",
            WhatChanges = "Системное время может измениться.", Risk = RiskLevel.Medium, RequiresAdmin = true, CommandPreview = "w32tm /resync",
            RetestModuleIds = new[] { M.Domain }, VerifyCheckIds = new[] { C.DomainTime } },
        new() { Id = A.GpUpdate, Title = "Обновить групповые политики", Description = "Принудительное применение групповых политик.",
            WhatChanges = "Политики будут применены повторно; может потребоваться выход из системы.", Risk = RiskLevel.Medium, CommandPreview = "gpupdate /force",
            RetestModuleIds = new[] { M.Domain }, VerifyCheckIds = new[] { C.DomainGpo } },
        new() { Id = A.ChkdskScan, Title = "Проверить диск онлайн (CHKDSK /scan)", Description = "Проверка файловой системы без отключения тома.",
            WhatChanges = "Диск будет нагружен во время проверки; исправления не выполняются.", Risk = RiskLevel.Medium, RequiresAdmin = true, IsLongRunning = true,
            Parameter = "drive", CommandPreview = "chkdsk C: /scan" },

        // ── HIGH ──
        new() { Id = A.ResetWindowsUpdateCache, Title = "Сбросить кэш Windows Update (SoftwareDistribution)", Description = "Останавливает службы WU и переименовывает SoftwareDistribution и catroot2 в .bak.",
            WhatChanges = "История загрузок будет сброшена, обновления загрузятся заново. Папки сохраняются как резервная копия (.bak) — действие обратимо.",
            Risk = RiskLevel.High, RequiresAdmin = true, Reversible = true,
            CommandPreview = "Stop-Service wuauserv,BITS,CryptSvc; Rename SoftwareDistribution → SoftwareDistribution.bak-<дата>; Start-Service ...",
            RetestModuleIds = new[] { M.WindowsUpdate }, VerifyCheckIds = new[] { C.WuService, C.WuBits } },
        new() { Id = A.DismRestoreHealth, Title = "Восстановить хранилище компонентов (DISM RestoreHealth)", Description = "Восстанавливает образ Windows, может загружать файлы с Windows Update. 10–40 минут.",
            WhatChanges = "Будут заменены повреждённые файлы хранилища компонентов. Может потребоваться перезагрузка.", Risk = RiskLevel.High, RequiresAdmin = true,
            RequiresReboot = true, IsLongRunning = true, CommandPreview = "DISM /Online /Cleanup-Image /RestoreHealth",
            RetestModuleIds = new[] { M.WindowsHealth }, VerifyCheckIds = new[] { C.HealthDism } },
        new() { Id = A.SfcScanNow, Title = "Восстановить системные файлы (SFC /scannow)", Description = "Проверяет и заменяет повреждённые системные файлы. 10–30 минут.",
            WhatChanges = "Повреждённые системные файлы будут заменены. Может потребоваться перезагрузка.", Risk = RiskLevel.High, RequiresAdmin = true,
            RequiresReboot = true, IsLongRunning = true, CommandPreview = "sfc /scannow", RetestModuleIds = new[] { M.WindowsHealth }, VerifyCheckIds = new[] { C.HealthCbs } },
        new() { Id = A.ChkdskFix, Title = "Запланировать CHKDSK /f при перезагрузке", Description = "Помечает том для проверки и исправления при следующей загрузке.",
            WhatChanges = "При следующей загрузке компьютер будет проверять диск (может занять долгое время).", Risk = RiskLevel.High, RequiresAdmin = true,
            RequiresReboot = true, Parameter = "drive", CommandPreview = "fsutil dirty set C:  (CHKDSK /f при загрузке)" },
        new() { Id = A.ChkdskRepair, Title = "Запланировать CHKDSK /r при перезагрузке", Description = "Поиск повреждённых секторов и восстановление данных при следующей загрузке.",
            WhatChanges = "Очень долгая проверка (часы) при следующей загрузке.", Risk = RiskLevel.High, RequiresAdmin = true, RequiresReboot = true,
            Parameter = "drive", CommandPreview = "chkdsk C: /r (подтверждение Y — запуск при перезагрузке)" },
        new() { Id = A.WinsockReset, Title = "Сбросить Winsock", Description = "Возвращает каталог Winsock к состоянию по умолчанию (последнее средство при «сломанном» сетевом стеке).",
            WhatChanges = "Будут удалены сторонние LSP (VPN/антивирусы могут потребовать переустановки). Нужна перезагрузка.", Risk = RiskLevel.High,
            RequiresAdmin = true, RequiresReboot = true, CommandPreview = "netsh winsock reset" },

        // ── Tools (LOW) ──
        Tool(A.OpenNetworkConnections, "Открыть «Сетевые подключения»", "ncpa.cpl"),
        Tool(A.OpenServices, "Открыть «Службы»", "services.msc"),
        Tool(A.OpenEventViewer, "Открыть «Просмотр событий»", "eventvwr.msc"),
        Tool(A.OpenPrinters, "Открыть «Принтеры и сканеры»", "ms-settings:printers"),
        Tool(A.OpenWindowsUpdate, "Открыть «Центр обновления Windows»", "ms-settings:windowsupdate"),
        Tool(A.OpenDiskCleanup, "Открыть «Очистка диска»", "cleanmgr.exe"),
        Tool(A.OpenTaskManager, "Открыть «Диспетчер задач»", "taskmgr.exe"),
        Tool(A.OpenResourceMonitor, "Открыть «Монитор ресурсов»", "resmon.exe"),
        Tool(A.OpenStorageSettings, "Открыть «Память устройства»", "ms-settings:storagesense"),
        Tool(A.OpenRemoteSettings, "Открыть настройки удалённого рабочего стола", "ms-settings:remotedesktop"),
        Tool(A.OpenFirewall, "Открыть «Брандмауэр Windows»", "wf.msc"),
        Tool(A.OpenWindowsSecurity, "Открыть «Безопасность Windows»", "windowsdefender:"),
        Tool(A.OpenWifiSettings, "Открыть настройки Wi-Fi", "ms-settings:network-wifi"),
        Tool(A.OpenProxySettings, "Открыть настройки прокси", "ms-settings:network-proxy"),
        Tool(A.OpenStartupApps, "Открыть «Автозагрузка»", "ms-settings:startupapps"),
    };

    public static RemediationAction? Find(string id) => All.FirstOrDefault(a => a.Id.Equals(id, StringComparison.OrdinalIgnoreCase));
}
