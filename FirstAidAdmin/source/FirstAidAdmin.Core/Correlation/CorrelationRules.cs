using FirstAidAdmin.Core.Models;
using C = FirstAidAdmin.Core.CheckIds;
using A = FirstAidAdmin.Core.ActionIds;

namespace FirstAidAdmin.Core.Correlation;

/// <summary>
/// Built-in correlation rules. Every rule states facts (basis) and a hypothesis with confidence.
/// Wording deliberately avoids claiming certainty.
/// </summary>
public static class CorrelationRules
{
    /// <summary>Finding ids that make other (more generic) findings redundant.</summary>
    public static IEnumerable<string> Supersedes(string findingId) => findingId switch
    {
        "net.no-adapter" => new[] { "net.no-ip", "net.gateway-unreachable", "net.external", "net.dns", "net.http", "net.no-gateway" },
        "net.no-ip" => new[] { "net.gateway-unreachable", "net.external", "net.dns", "net.http", "net.no-gateway" },
        "net.no-gateway" => new[] { "net.gateway-unreachable", "net.external", "net.dns", "net.http" },
        "net.gateway-unreachable" => new[] { "net.external", "net.dns", "net.http" },
        "net.external" => new[] { "net.dns", "net.http" },
        "net.dns" => new[] { "net.http", "dns.internal-only" },
        "domain.public-dns" => new[] { "dns.internal-only", "domain.dc-unreachable" },
        "wu.disk-space" => new[] { "disk.system-low" },
        "health.unexpected-shutdown" => new[] { "events.serious" },
        "wu.component-store" => new[] { "health.dism-repairable" },
        "rdp.disabled" => new[] { "rdp.not-listening" },
        "rdp.service-stopped" => new[] { "rdp.not-listening" },
        "printer.spooler" => new[] { "printer.queue-stuck", "printer.offline" },
        "share.dns" => new[] { "share.unreachable" },
        _ => Array.Empty<string>()
    };

    /// <summary>Failed checks that are fully explained by other results and need no finding of their own.</summary>
    public static IEnumerable<string> ExplainedChecks(ResultSet s)
    {
        if (s.FailedOrWarn(C.NetGatewayPing) && s.IsOk(C.NetInternetIp)) yield return C.NetGatewayPing; // ICMP blocked on gateway
        if (s.FailedOrWarn(C.RdpListening) && (s.Failed(C.RdpEnabled) || s.Failed(C.RdpService))) yield return C.RdpListening;
    }

    private static Finding F(string id, string title, DiagnosticCategory cat, Severity sev, Confidence conf,
        string found, string cause, string recommendation, params string[] related)
        => new()
        {
            Id = id,
            Title = title,
            Category = cat,
            Severity = sev,
            Confidence = conf,
            WhatWasFound = found,
            ProbableCause = cause,
            Recommendation = recommendation,
            RelatedCheckIds = related.ToList(),
            KnowledgeBaseId = id
        };

    private static Finding Fix(this Finding f, params string[] actions) { f.RemediationIds.AddRange(actions); return f; }
    private static Finding Reboot(this Finding f) { f.MayRequireReboot = true; return f; }

    /// <summary>Adds a ✓/✗ line for a check if it ran.</summary>
    private static Finding Line(this Finding f, ResultSet s, string id, string okText, string failText)
    {
        if (!s.Ran(id)) return f;
        if (s.Failed(id)) f.Against(failText);
        else if (s.Warn(id)) f.Against(failText + " (частично)");
        else f.Support(okText);
        return f;
    }

    private static bool DnsFailed(ResultSet s) => s.AnyFailed(C.DnsResolveExternal, C.NetDnsResolve);
    private static bool DnsOk(ResultSet s) => s.AnyOk(C.DnsResolveExternal, C.NetDnsResolve) && !DnsFailed(s);

    private static Finding NetChain(this Finding f, ResultSet s) => f
        .Line(s, C.NetAdapters, "Сетевой адаптер подключён", "Нет активного сетевого адаптера")
        .Line(s, C.NetIPv4, "IPv4-адрес получен", "Нет корректного IPv4-адреса")
        .Line(s, C.NetGatewayConfigured, "Шлюз по умолчанию задан", "Шлюз по умолчанию не задан")
        .Line(s, C.NetGatewayPing, "Шлюз доступен", "Шлюз не отвечает")
        .Line(s, C.NetInternetIp, "Интернет по IP работает", "Внешние IP-адреса недоступны")
        .Line(s, C.DnsResolveExternal, "DNS-запросы проходят", "DNS-запросы не проходят")
        .Line(s, C.NetDnsResolve, "Имена разрешаются", "Имена не разрешаются")
        .Line(s, C.NetHttp, "HTTP-проверка проходит", "HTTP-проверка не проходит");

    public static IReadOnlyList<ICorrelationRule> All() => new ICorrelationRule[]
    {
        // ───────────── NETWORK ─────────────
        new DelegateRule("net.no-adapter", s => !s.Failed(C.NetAdapters) ? null :
            F("net.no-adapter", "Нет активного сетевого подключения", DiagnosticCategory.Network, Severity.Critical, Confidence.High,
                s.Summary(C.NetAdapters),
                "Кабель не подключён, Wi-Fi отключён, адаптер выключен или неисправен драйвер.",
                "Проверьте кабель/Wi-Fi и состояние адаптера в «Сетевых подключениях».", C.NetAdapters)
            .NetChain(s).Fix(A.OpenNetworkConnections, A.OpenWifiSettings)),

        new DelegateRule("net.no-ip", s => !s.Failed(C.NetIPv4) ? null :
            F("net.no-ip", "Не получен корректный IP-адрес", DiagnosticCategory.Network, Severity.High, Confidence.High,
                s.Summary(C.NetIPv4),
                s.Evidence(C.NetIPv4, "apipa") == "True"
                    ? "Адрес 169.254.x.x (APIPA): DHCP-сервер недоступен или не выдал адрес."
                    : "IPv4-адрес отсутствует: адаптер не настроен или DHCP недоступен.",
                "Обновите IP-адрес (ipconfig /renew). Если не помогло — проверьте DHCP-сервер и порт коммутатора.",
                C.NetIPv4, C.NetDhcp)
            .NetChain(s).Fix(A.RenewIp, A.OpenNetworkConnections)),

        new DelegateRule("net.no-gateway", s => !s.Failed(C.NetGatewayConfigured) || s.Failed(C.NetIPv4) ? null :
            F("net.no-gateway", "Не задан шлюз по умолчанию", DiagnosticCategory.Network, Severity.High, Confidence.High,
                s.Summary(C.NetGatewayConfigured),
                "Статическая настройка без шлюза или DHCP не передаёт параметр Router.",
                "Проверьте настройки IPv4 адаптера или параметры DHCP-области.", C.NetGatewayConfigured, C.NetRoutes)
            .NetChain(s).Fix(A.RenewIp, A.OpenNetworkConnections)),

        new DelegateRule("net.gateway-unreachable", s =>
        {
            if (!s.Failed(C.NetGatewayPing)) return null;
            var arpOk = s.IsOk(C.NetGatewayArp);
            var internetOk = s.IsOk(C.NetInternetIp);
            if (internetOk) return null; // gateway just blocks ICMP
            var f = F("net.gateway-unreachable", "Шлюз по умолчанию недоступен", DiagnosticCategory.Network, Severity.High,
                arpOk ? Confidence.Medium : Confidence.High,
                s.Summary(C.NetGatewayPing),
                arpOk
                    ? "Шлюз виден на канальном уровне (есть ARP-запись), но не отвечает: возможна блокировка ICMP или проблема маршрутизатора."
                    : "Нет связи с локальной сетью: кабель, порт коммутатора, Wi-Fi или сам маршрутизатор.",
                "Проверьте физическое подключение и маршрутизатор; сравните с другим компьютером в этой сети.",
                C.NetGatewayPing, C.NetGatewayArp, C.NetInternetIp).NetChain(s);
            return f.Fix(A.RenewIp, A.OpenNetworkConnections);
        }),

        new DelegateRule("net.external", s =>
            !(s.IsOk(C.NetGatewayPing) || s.IsOk(C.NetGatewayArp)) || !s.Failed(C.NetInternetIp) ? null :
            F("net.external", "Вероятная проблема с доступом во внешнюю сеть", DiagnosticCategory.Network, Severity.High,
                DnsFailed(s) ? Confidence.High : Confidence.Medium,
                "Локальная сеть работает, но внешние IP-адреса недоступны.",
                "Нет доступа в Интернет за маршрутизатором: провайдер, межсетевой экран, NAT или маршрутизация.",
                "Проверьте маршрутизатор/межсетевой экран и канал провайдера. Проверьте, есть ли Интернет на других ПК.",
                C.NetInternetIp, C.NetHttp, C.DnsResolveExternal, C.NetDnsResolve)
            .NetChain(s)),

        new DelegateRule("net.dns", s => !s.IsOk(C.NetInternetIp) || !DnsFailed(s) ? null :
            F("net.dns", "Проблема DNS", DiagnosticCategory.Dns, Severity.High,
                s.IsOk(C.DnsReference) ? Confidence.High : Confidence.Medium,
                "Интернет по IP работает, но DNS-имена не разрешаются.",
                s.IsOk(C.DnsReference)
                    ? "Настроенный DNS-сервер не отвечает или отвечает с ошибкой; эталонный DNS работает."
                    : "Некорректный или недоступный DNS-сервер, либо DNS-трафик блокируется.",
                "Очистите кэш DNS и проверьте адреса DNS-серверов в настройках адаптера.",
                C.DnsResolveExternal, C.NetDnsResolve, C.DnsServerReachable, C.DnsReference, C.DnsServersConfigured)
            .NetChain(s)
            .Line(s, C.DnsServerReachable, "Настроенный DNS-сервер отвечает", "Настроенный DNS-сервер не отвечает")
            .Line(s, C.DnsReference, "Эталонный DNS (8.8.8.8) отвечает", "Эталонный DNS тоже недоступен")
            .Fix(A.FlushDns, A.RegisterDns, A.OpenNetworkConnections)),

        new DelegateRule("net.http", s =>
            !s.IsOk(C.NetInternetIp) || !DnsOk(s) || !s.Failed(C.NetHttp) ? null :
            F("net.http", s.Evidence(C.NetProxy, "enabled") == "True" ? "Вероятная проблема с прокси-сервером" : "HTTP-доступ блокируется",
                DiagnosticCategory.Network, Severity.Medium, Confidence.Medium,
                "IP и DNS работают, но HTTP-проверка подключения не проходит.",
                s.Evidence(C.NetProxy, "enabled") == "True"
                    ? "Настроен прокси-сервер, который недоступен или требует аутентификации."
                    : "HTTP блокируется межсетевым экраном/фильтром или требуется вход на captive-портал.",
                "Проверьте настройки прокси и политику веб-фильтрации.", C.NetHttp, C.NetProxy)
            .NetChain(s).Fix(A.OpenProxySettings)),

        new DelegateRule("net.tcp-retransmits", s => !s.Warn(C.NetTcp) ? null :
            F("net.tcp-retransmits", "Высокий уровень повторных передач TCP", DiagnosticCategory.Network, Severity.Medium, Confidence.Low,
                s.Summary(C.NetTcp),
                "Потери пакетов: плохой кабель, слабый Wi-Fi или перегруженный канал.",
                "Проверьте качество канала (кабель, уровень Wi-Fi) и загрузку сети.", C.NetTcp)
            .Line(s, C.WifiSignal, "Сигнал Wi-Fi в норме", "Слабый сигнал Wi-Fi")),

        // ───────────── DNS / DOMAIN DNS ─────────────
        new DelegateRule("domain.public-dns", s =>
            s.Evidence(C.DnsServersConfigured, "publicOnDomain") != "True" ? null :
            F("domain.public-dns", "Доменный компьютер использует внешний DNS", DiagnosticCategory.Dns, Severity.High, Confidence.High,
                s.Summary(C.DnsServersConfigured),
                "В настройках адаптера указаны публичные DNS-серверы. Они не знают записей домена, поэтому вход в домен, GPO и Kerberos не работают.",
                "Укажите в качестве DNS адреса контроллеров домена (или корпоративных DNS).",
                C.DnsServersConfigured, C.DnsSrvLdap, C.DnsSrvKerberos, C.DnsResolveInternal, C.DomainDcDiscovery)
            .Line(s, C.DnsSrvLdap, "SRV _ldap._tcp найдены", "SRV _ldap._tcp не найдены")
            .Line(s, C.DomainDcDiscovery, "Контроллер домена обнаружен", "Контроллер домена не обнаружен")
            .Fix(A.OpenNetworkConnections)),

        new DelegateRule("dns.internal-only", s =>
            !(s.IsOk(C.DnsResolveExternal) && s.AnyFailed(C.DnsResolveInternal, C.DnsSrvLdap, C.DnsSrvKerberos)) ? null :
            F("dns.internal-only", "Не разрешаются внутренние (доменные) имена", DiagnosticCategory.Dns, Severity.High, Confidence.Medium,
                "Внешние имена разрешаются, внутренние — нет.",
                "DNS-сервер не обслуживает зону домена или недоступен доменный DNS.",
                "Проверьте, что DNS указывает на доменные DNS-серверы, и выполните ipconfig /registerdns.",
                C.DnsResolveInternal, C.DnsSrvLdap, C.DnsSrvKerberos)
            .Line(s, C.DnsResolveExternal, "Внешние имена разрешаются", "Внешние имена не разрешаются")
            .Line(s, C.DnsSrvLdap, "SRV _ldap._tcp найдены", "SRV _ldap._tcp не найдены")
            .Line(s, C.DnsSrvKerberos, "SRV _kerberos._tcp найдены", "SRV _kerberos._tcp не найдены")
            .Fix(A.FlushDns, A.RegisterDns)),

        // ───────────── DOMAIN ─────────────
        new DelegateRule("domain.secure-channel", s => !s.Failed(C.DomainSecureChannel) ? null :
            F("domain.secure-channel", "Нарушено доверительное отношение с доменом", DiagnosticCategory.Domain, Severity.Critical,
                s.IsOk(C.DomainDcConnectivity) ? Confidence.High : Confidence.Medium,
                s.Summary(C.DomainSecureChannel),
                s.IsOk(C.DomainDcConnectivity)
                    ? "Контроллер домена доступен, но безопасный канал не устанавливается: вероятно, рассинхронизирован пароль учётной записи компьютера."
                    : "Безопасный канал не устанавливается; контроллер домена может быть недоступен.",
                "Под учётной записью администратора домена выполните Test-ComputerSecureChannel -Repair -Credential (вручную) или повторно введите ПК в домен.",
                C.DomainSecureChannel, C.DomainDcConnectivity)
            .Line(s, C.DomainDcConnectivity, "Порты контроллера домена доступны", "Контроллер домена недоступен")
            .Line(s, C.DomainTime, "Время синхронизировано", "Расхождение времени")),

        new DelegateRule("domain.dc-unreachable", s =>
            !s.Failed(C.DomainDcConnectivity) && !s.Failed(C.DomainDcDiscovery) ? null :
            F("domain.dc-unreachable", "Контроллер домена недоступен", DiagnosticCategory.Domain, Severity.High,
                s.IsOk(C.NetGatewayPing) ? Confidence.High : Confidence.Medium,
                s.Failed(C.DomainDcDiscovery) ? s.Summary(C.DomainDcDiscovery) : s.Summary(C.DomainDcConnectivity),
                s.AnyFailed(C.DnsSrvLdap, C.DnsSrvKerberos)
                    ? "DNS не находит SRV-записи домена — компьютер не может найти контроллер."
                    : "Сеть до контроллера домена недоступна (VPN, маршрутизация, межсетевой экран).",
                "Проверьте DNS и сетевой доступ к контроллеру домена (порты 53, 88, 389, 445).",
                C.DomainDcConnectivity, C.DomainDcDiscovery, C.AdDcPorts)
            .Line(s, C.NetGatewayPing, "Локальная сеть работает", "Локальная сеть недоступна")
            .Line(s, C.DnsSrvLdap, "SRV _ldap._tcp найдены", "SRV _ldap._tcp не найдены")
            .Fix(A.FlushDns, A.RegisterDns)),

        new DelegateRule("domain.time-skew", s => !s.FailedOrWarn(C.DomainTime) ? null :
            F("domain.time-skew", "Расхождение времени с контроллером домена", DiagnosticCategory.Domain,
                s.Failed(C.DomainTime) ? Severity.High : Severity.Medium, Confidence.High,
                s.Summary(C.DomainTime),
                "Kerberos допускает расхождение не более 5 минут; при большем расхождении вход и доступ к ресурсам перестают работать.",
                "Выполните синхронизацию времени (w32tm /resync) и проверьте источник времени.",
                C.DomainTime, C.DomainKerberos)
            .Line(s, C.DomainKerberos, "Билеты Kerberos есть", "Проблемы Kerberos")
            .Fix(A.TimeResync)),

        new DelegateRule("domain.gpo", s => !s.FailedOrWarn(C.DomainGpo) ? null :
            F("domain.gpo", "Ошибки применения групповых политик", DiagnosticCategory.Domain, Severity.Medium, Confidence.Medium,
                s.Summary(C.DomainGpo),
                "Групповые политики не применяются: недоступен SYSVOL/контроллер, DNS или ошибки отдельных расширений.",
                "Проверьте доступ к \\\\домен\\SYSVOL и выполните gpupdate /force.", C.DomainGpo, C.AdSysvol)
            .Line(s, C.AdSysvol, "SYSVOL доступен", "SYSVOL недоступен")
            .Fix(A.GpUpdate)),

        new DelegateRule("ad.logon-failures", s => !s.FailedOrWarn(C.AdLogonFailures) ? null :
            F("ad.logon-failures", "Неудачные попытки входа", DiagnosticCategory.ActiveDirectory, Severity.Medium, Confidence.Medium,
                s.Summary(C.AdLogonFailures),
                "Неверный пароль, заблокированная/просроченная учётная запись или сохранённые старые учётные данные.",
                "Проверьте учётную запись в AD (блокировка, срок пароля) и сохранённые учётные данные пользователя.",
                C.AdLogonFailures)),

        // ───────────── RDP ─────────────
        new DelegateRule("rdp.disabled", s => !s.Failed(C.RdpEnabled) ? null :
            F("rdp.disabled", "Удалённый рабочий стол отключён на этом компьютере", DiagnosticCategory.Rdp, Severity.High, Confidence.High,
                s.Summary(C.RdpEnabled), "В настройках системы запрещены удалённые подключения (fDenyTSConnections = 1).",
                "Включите удалённый рабочий стол вручную (Параметры → Система → Удалённый рабочий стол), если это разрешено политикой.",
                C.RdpEnabled).Fix(A.OpenRemoteSettings)),

        new DelegateRule("rdp.service-stopped", s => !s.Failed(C.RdpService) ? null :
            F("rdp.service-stopped", "Служба удалённых рабочих столов не запущена", DiagnosticCategory.Rdp, Severity.High, Confidence.High,
                s.Summary(C.RdpService), "Служба TermService остановлена или отключена.",
                "Запустите службу TermService и проверьте тип её запуска.", C.RdpService).Fix(A.OpenServices)),

        new DelegateRule("rdp.not-listening", s => !s.Failed(C.RdpListening) ? null :
            F("rdp.not-listening", "RDP-порт не прослушивается", DiagnosticCategory.Rdp, Severity.High, Confidence.Medium,
                s.Summary(C.RdpListening), "RDP не принимает подключения на настроенном порту.",
                "Проверьте службу TermService и номер порта RDP-Tcp.", C.RdpListening, C.RdpPort)
            .Line(s, C.RdpService, "Служба TermService запущена", "Служба TermService не запущена")
            .Line(s, C.RdpEnabled, "RDP разрешён", "RDP запрещён")),

        new DelegateRule("rdp.firewall", s => !s.Failed(C.RdpFirewall) ? null :
            F("rdp.firewall", "Брандмауэр может блокировать RDP", DiagnosticCategory.Rdp, Severity.Medium, Confidence.Medium,
                s.Summary(C.RdpFirewall), "Правила группы «Удалённый рабочий стол» выключены при включённом брандмауэре.",
                "Включите правила «Удалённый рабочий стол» в брандмауэре Windows для нужного профиля.", C.RdpFirewall)
            .Fix(A.OpenFirewall)),

        new DelegateRule("rdp.target", s =>
        {
            if (!s.Failed(C.RdpTargetTcp)) return null;
            var target = s.Evidence(C.RdpTargetTcp, "target") ?? "цель";
            var pingOk = s.IsOk(C.RdpTargetPing);
            return F("rdp.target", $"Порт RDP на {target} недоступен", DiagnosticCategory.Rdp, Severity.High,
                    pingOk ? Confidence.High : Confidence.Medium,
                    s.Summary(C.RdpTargetTcp),
                    pingOk
                        ? "Узел отвечает на ping, но порт закрыт: RDP выключен на целевом ПК, служба остановлена или порт блокирует брандмауэр."
                        : "Узел не отвечает: выключен, недоступен по сети или блокирует ICMP и RDP.",
                    pingOk ? "Проверьте RDP и брандмауэр на целевом компьютере." : "Проверьте, включён ли компьютер и доступен ли он по сети/VPN.",
                    C.RdpTargetTcp, C.RdpTargetPing)
                .Line(s, C.RdpTargetPing, "Узел отвечает на ping", "Узел не отвечает на ping");
        }),

        // ───────────── PRINTER ─────────────
        new DelegateRule("printer.spooler", s => !s.Failed(C.PrinterSpooler) ? null :
            F("printer.spooler", "Служба печати (Print Spooler) не работает", DiagnosticCategory.Printer, Severity.High, Confidence.High,
                s.Summary(C.PrinterSpooler), "Без службы диспетчера печати печать невозможна.",
                "Перезапустите Print Spooler (требуется подтверждение и права администратора).", C.PrinterSpooler)
            .Fix(A.RestartSpooler)),

        new DelegateRule("printer.queue-stuck", s => !s.FailedOrWarn(C.PrinterQueue) ? null :
            F("printer.queue-stuck", "Задания печати застряли в очереди", DiagnosticCategory.Printer, Severity.Medium, Confidence.Medium,
                s.Summary(C.PrinterQueue), "Ошибочное задание блокирует очередь печати.",
                "Перезапустите Print Spooler; при необходимости очистите очередь.", C.PrinterQueue)
            .Fix(A.RestartSpooler, A.ClearPrintQueue)),

        new DelegateRule("printer.unreachable", s => !s.Failed(C.PrinterNetwork) ? null :
            F("printer.unreachable", "Сетевой принтер недоступен", DiagnosticCategory.Printer, Severity.High, Confidence.High,
                s.Summary(C.PrinterNetwork), "Принтер выключен, сменил IP-адрес или недоступен по сети.",
                "Проверьте питание принтера, его IP-адрес на панели и сетевое подключение.", C.PrinterNetwork)
            .Line(s, C.NetGatewayPing, "Локальная сеть работает", "Локальная сеть недоступна")),

        new DelegateRule("printer.offline", s => !s.FailedOrWarn(C.PrinterStatus) ? null :
            F("printer.offline", "Принтер в состоянии ошибки или «Автономно»", DiagnosticCategory.Printer, Severity.Medium, Confidence.Medium,
                s.Summary(C.PrinterStatus), "Принтер помечен как автономный, нет бумаги/тонера или замятие.",
                "Проверьте принтер физически и снимите режим «Работать автономно».", C.PrinterStatus)
            .Fix(A.OpenPrinters)),

        // ───────────── WINDOWS UPDATE ─────────────
        new DelegateRule("wu.disk-space", s =>
            !s.FailedOrWarn(C.StorageSystem) || !(s.FailedOrWarn(C.WuHistoryErrors) || s.FailedOrWarn(C.WuEvents) || s.FailedOrWarn(C.WuLastUpdate)) ? null :
            F("wu.disk-space", "Недостаточно места на системном диске может мешать Windows Update", DiagnosticCategory.WindowsUpdate,
                Severity.High, (s.Evidence(C.WuHistoryErrors, "codes") ?? "").Contains("0x80070070", StringComparison.OrdinalIgnoreCase) ? Confidence.High : Confidence.Medium,
                $"{s.Summary(C.StorageSystem)}; {s.Summary(C.WuHistoryErrors)}",
                "Для загрузки и установки обновлений нужно несколько ГБ свободного места.",
                "Освободите место на системном диске, затем повторите установку обновлений.",
                C.StorageSystem, C.WuHistoryErrors, C.WuEvents, C.StorageTemp)
            .Line(s, C.StorageSystem, "Места на диске достаточно", "Мало места на системном диске")
            .Line(s, C.WuHistoryErrors, "Ошибок установки нет", "Ошибки установки обновлений")
            .Line(s, C.StorageTemp, "Временные файлы в норме", "Много временных файлов")
            .Fix(A.ClearUserTemp, A.OpenDiskCleanup)),

        new DelegateRule("wu.component-store", s =>
        {
            var codes = s.Evidence(C.WuHistoryErrors, "codes") ?? "";
            var dismBad = s.FailedOrWarn(C.HealthDism) || s.FailedOrWarn(C.HealthDismScan);
            var storeCode = codes.Contains("0x80073712", StringComparison.OrdinalIgnoreCase) || codes.Contains("0x800f081f", StringComparison.OrdinalIgnoreCase)
                            || codes.Contains("0x800f0831", StringComparison.OrdinalIgnoreCase);
            if (!(dismBad && (storeCode || s.FailedOrWarn(C.WuHistoryErrors)))) return null;
            return F("wu.component-store", "Повреждение хранилища компонентов мешает обновлениям", DiagnosticCategory.WindowsHealth,
                    Severity.High, storeCode ? Confidence.High : Confidence.Medium,
                    $"{s.Summary(C.HealthDism)}; {s.Summary(C.WuHistoryErrors)}",
                    "Хранилище компонентов Windows (WinSxS) повреждено, поэтому обновления не устанавливаются.",
                    "Выполните DISM /RestoreHealth, затем sfc /scannow, затем повторите обновление.",
                    C.HealthDism, C.HealthDismScan, C.WuHistoryErrors)
                .Line(s, C.HealthDism, "Хранилище компонентов исправно", "Хранилище компонентов повреждено")
                .Fix(A.DismRestoreHealth, A.SfcScanNow).Reboot();
        }),

        new DelegateRule("wu.network", s =>
        {
            var codes = s.Evidence(C.WuHistoryErrors, "codes") ?? "";
            var netCode = codes.Contains("0x8024402c", StringComparison.OrdinalIgnoreCase) || codes.Contains("0x80072ee2", StringComparison.OrdinalIgnoreCase)
                          || codes.Contains("0x80072efd", StringComparison.OrdinalIgnoreCase) || codes.Contains("0x8024401c", StringComparison.OrdinalIgnoreCase);
            var netBad = s.AnyFailed(C.NetInternetIp, C.DnsResolveExternal, C.NetDnsResolve, C.NetHttp);
            if (!netCode && !(netBad && s.FailedOrWarn(C.WuHistoryErrors))) return null;
            return F("wu.network", "Windows Update не может связаться с сервером обновлений", DiagnosticCategory.WindowsUpdate, Severity.High,
                    netCode && netBad ? Confidence.High : Confidence.Medium,
                    s.Summary(C.WuHistoryErrors),
                    "Ошибки подключения: DNS, прокси, межсетевой экран или недоступен WSUS.",
                    "Устраните сетевую проблему (см. сетевые находки), проверьте прокси и адрес WSUS.",
                    C.WuHistoryErrors, C.WuPolicy)
                .Line(s, C.NetInternetIp, "Интернет по IP работает", "Нет доступа в Интернет")
                .Line(s, C.DnsResolveExternal, "DNS работает", "DNS не работает")
                .Line(s, C.WuPolicy, "Сервер обновлений по умолчанию", "Используется WSUS");
        }),

        new DelegateRule("wu.services", s => !s.AnyFailed(C.WuService, C.WuBits, C.WuRelated) ? null :
            F("wu.services", "Службы Windows Update отключены или не работают", DiagnosticCategory.WindowsUpdate, Severity.High, Confidence.High,
                string.Join("; ", new[] { C.WuService, C.WuBits, C.WuRelated }.Where(s.Failed).Select(s.Summary)),
                "Отключённая служба wuauserv/BITS/CryptSvc делает обновление невозможным.",
                "Верните тип запуска служб по умолчанию и перезапустите службы Windows Update.",
                C.WuService, C.WuBits, C.WuRelated).Fix(A.RestartWindowsUpdate, A.OpenServices)),

        new DelegateRule("wu.outdated", s => !s.FailedOrWarn(C.WuLastUpdate) ? null :
            F("wu.outdated", "Обновления давно не устанавливались", DiagnosticCategory.WindowsUpdate,
                s.Failed(C.WuLastUpdate) ? Severity.High : Severity.Medium, Confidence.Medium,
                s.Summary(C.WuLastUpdate), "Обновления не устанавливаются (ошибки, отключение, политика WSUS) или компьютер давно был выключен.",
                "Откройте Центр обновления Windows и выполните поиск обновлений.", C.WuLastUpdate)
            .Line(s, C.WuService, "Служба wuauserv в порядке", "Служба wuauserv не работает")
            .Fix(A.OpenWindowsUpdate)),

        new DelegateRule("wu.pending-reboot", s => !s.FailedOrWarn(C.WuPendingReboot) && !s.FailedOrWarn(C.HealthPendingReboot) ? null :
            F("wu.pending-reboot", "Ожидается перезагрузка", DiagnosticCategory.WindowsUpdate, Severity.Medium, Confidence.High,
                s.Ran(C.WuPendingReboot) ? s.Summary(C.WuPendingReboot) : s.Summary(C.HealthPendingReboot),
                "Установка обновлений или компонентов не завершена до перезагрузки.",
                "Перезагрузите компьютер в удобное для пользователя время.", C.WuPendingReboot, C.HealthPendingReboot).Reboot()),

        // ───────────── STORAGE ─────────────
        new DelegateRule("disk.system-low", s => !s.FailedOrWarn(C.StorageSystem) ? null :
            F("disk.system-low", "Недостаточно места на системном диске", DiagnosticCategory.Storage,
                s.Failed(C.StorageSystem) ? Severity.High : Severity.Medium, Confidence.High,
                s.Summary(C.StorageSystem),
                "Заполненный системный диск замедляет работу и мешает обновлениям, файлу подкачки и временным файлам.",
                "Освободите место: очистите временные файлы, корзину, старые обновления (cleanmgr).", C.StorageSystem, C.StorageTemp)
            .Line(s, C.StorageTemp, "Временные файлы в норме", "Много временных файлов")
            .Fix(A.ClearUserTemp, A.OpenDiskCleanup, A.OpenStorageSettings)),

        new DelegateRule("disk.hardware", s =>
            !s.FailedOrWarn(C.StoragePhysical) && !s.FailedOrWarn(C.StorageEvents) ? null :
            F("disk.hardware", "Признаки неисправности диска", DiagnosticCategory.Storage,
                s.Failed(C.StoragePhysical) ? Severity.Critical : Severity.High,
                s.FailedOrWarn(C.StoragePhysical) && s.FailedOrWarn(C.StorageEvents) ? Confidence.High : Confidence.Medium,
                string.Join("; ", new[] { C.StoragePhysical, C.StorageEvents }.Where(s.FailedOrWarn).Select(s.Summary)),
                "Ошибки ввода-вывода или состояние диска указывают на возможный аппаратный сбой.",
                "Сделайте резервную копию данных. Выполните CHKDSK /scan; при подтверждении — замените диск.",
                C.StoragePhysical, C.StorageEvents)
            .Line(s, C.StoragePhysical, "Состояние физического диска: Healthy", "Физический диск не в состоянии Healthy")
            .Line(s, C.StorageEvents, "Ошибок диска в журнале нет", "Ошибки диска в журнале System")
            .Fix(A.ChkdskScan)),

        // ───────────── PERFORMANCE ─────────────
        new DelegateRule("perf.summary", s =>
        {
            var causes = new List<string>();
            if (s.FailedOrWarn(C.PerfRam)) causes.Add("Высокая загрузка RAM");
            if (s.FailedOrWarn(C.PerfCpu)) causes.Add("Высокая загрузка CPU");
            if (s.FailedOrWarn(C.PerfDisk) || s.FailedOrWarn(C.StorageSystem)) causes.Add("Недостаточно свободного места на системном диске");
            if (s.FailedOrWarn(C.StoragePerformance)) causes.Add("Высокая загрузка/задержка диска");
            if (s.FailedOrWarn(C.PerfUptime)) causes.Add("Очень длительное время непрерывной работы");
            if (s.FailedOrWarn(C.PerfStartup)) causes.Add("Много программ в автозагрузке");
            if (causes.Count == 0) return null;
            var f = F("perf.summary", "Обнаружены потенциальные причины снижения производительности", DiagnosticCategory.Performance,
                causes.Count >= 2 ? Severity.High : Severity.Medium, causes.Count >= 2 ? Confidence.Medium : Confidence.Low,
                string.Join("; ", causes.Select((c, i) => $"{i + 1}. {c}")),
                "Перечисленные факторы могут влиять на производительность. Причинно-следственная связь не доказана — сравните с жалобой пользователя.",
                "Закройте ресурсоёмкие процессы, освободите место, перезагрузите компьютер при длительном uptime.",
                C.PerfRam, C.PerfCpu, C.PerfDisk, C.PerfUptime, C.PerfStartup, C.StoragePerformance);
            f.Line(s, C.PerfCpu, "CPU в норме", "Высокая загрузка CPU")
             .Line(s, C.PerfRam, "RAM в норме", "Высокая загрузка RAM")
             .Line(s, C.PerfDisk, "Места на C: достаточно", "Мало места на C:")
             .Line(s, C.PerfUptime, "Uptime в норме", "Длительный uptime");
            return f.Fix(A.OpenTaskManager, A.OpenResourceMonitor, A.OpenStartupApps);
        }),

        // ───────────── WINDOWS HEALTH ─────────────
        new DelegateRule("health.dism-repairable", s => !s.FailedOrWarn(C.HealthDism) && !s.FailedOrWarn(C.HealthDismScan) ? null :
            F("health.dism-repairable", "Повреждено хранилище компонентов Windows", DiagnosticCategory.WindowsHealth, Severity.High, Confidence.High,
                s.Ran(C.HealthDism) ? s.Summary(C.HealthDism) : s.Summary(C.HealthDismScan),
                "DISM сообщает о повреждении образа Windows.",
                "Выполните DISM /Online /Cleanup-Image /RestoreHealth (HIGH risk, требуется подтверждение), затем sfc /scannow.",
                C.HealthDism, C.HealthDismScan).Fix(A.DismRestoreHealth, A.SfcScanNow).Reboot()),

        new DelegateRule("health.sfc", s => !s.FailedOrWarn(C.HealthSfc) && !s.FailedOrWarn(C.HealthCbs) ? null :
            F("health.sfc", "Обнаружены повреждённые системные файлы", DiagnosticCategory.WindowsHealth, Severity.High,
                s.FailedOrWarn(C.HealthSfc) ? Confidence.High : Confidence.Medium,
                s.Ran(C.HealthSfc) ? s.Summary(C.HealthSfc) : s.Summary(C.HealthCbs),
                "Проверка целостности системных файлов нашла нарушения.",
                "Выполните DISM /RestoreHealth, затем sfc /scannow.", C.HealthSfc, C.HealthCbs)
            .Line(s, C.HealthDism, "Хранилище компонентов исправно", "Хранилище компонентов повреждено")
            .Fix(A.DismRestoreHealth, A.SfcScanNow).Reboot()),

        new DelegateRule("health.unexpected-shutdown", s =>
        {
            var kp = s.All.FirstOrDefault(r => r.Id.EndsWith("kernel-power.41", StringComparison.OrdinalIgnoreCase));
            var crash = s.FailedOrWarn(C.HealthCrashes);
            if (kp is null && !crash) return null;
            var f = F("health.unexpected-shutdown", "Неожиданные выключения или сбои системы", DiagnosticCategory.WindowsHealth, Severity.High,
                kp is not null && crash ? Confidence.High : Confidence.Medium,
                kp?.Summary ?? s.Summary(C.HealthCrashes),
                "Kernel-Power 41 / BugCheck: пропадание питания, перегрев, драйверы или неисправность оборудования.",
                "Проверьте питание (ИБП, БП), температуру, обновите драйверы; изучите дампы памяти.",
                C.HealthCrashes);
            if (kp is not null) f.RelatedCheckIds.Add(kp.Id);
            return f.Line(s, C.StorageEvents, "Ошибок диска нет", "Есть ошибки диска").Fix(A.OpenEventViewer);
        }),

        new DelegateRule("events.serious", s =>
        {
            var logs = new[] { C.EventsSystem, C.EventsApplication }.Where(s.Failed).ToList();
            if (logs.Count == 0) return null;
            var groups = logs.SelectMany(l => s.Get(l)!.Checks).Where(g => g.IsProblem).ToList();
            var f = F("events.serious", "Серьёзные события в журналах Windows", DiagnosticCategory.EventLog, Severity.High,
                groups.Count >= 2 ? Confidence.Medium : Confidence.Low,
                string.Join("; ", groups.Select(g => $"{g.Name}: {g.Summary}")),
                "В журналах зарегистрированы сбои служб, питания, дисков или оборудования. Связь с жалобой пользователя нужно подтвердить по времени событий.",
                "Сопоставьте время событий с моментом проблемы и изучите их в «Просмотре событий».",
                logs.ToArray());
            foreach (var g in groups) f.Against($"{g.Name} — {g.Summary}");
            return f.Fix(A.OpenEventViewer);
        }),

        // ───────────── SECURITY ─────────────
        new DelegateRule("security.no-av", s =>
            !s.Failed(C.SecDefender) || !string.IsNullOrEmpty(s.Evidence(C.SecAntivirus, "thirdParty")) ? null :
            F("security.no-av", "Защита от вирусов в реальном времени отключена", DiagnosticCategory.Security, Severity.Critical, Confidence.High,
                s.Summary(C.SecDefender), "Microsoft Defender отключён, сторонний антивирус не обнаружен.",
                "Включите защиту в реальном времени в «Безопасность Windows» или проверьте сторонний антивирус.",
                C.SecDefender, C.SecAntivirus).Fix(A.OpenWindowsSecurity)),

        new DelegateRule("security.firewall", s => !s.Failed(C.SecFirewall) ? null :
            F("security.firewall", "Брандмауэр Windows отключён", DiagnosticCategory.Security, Severity.High, Confidence.High,
                s.Summary(C.SecFirewall), "Один или несколько профилей брандмауэра выключены.",
                "Включите брандмауэр для всех профилей (если нет стороннего межсетевого экрана).", C.SecFirewall)
            .Fix(A.OpenFirewall)),

        new DelegateRule("security.signatures", s => !s.FailedOrWarn(C.SecSignatures) ? null :
            F("security.signatures", "Антивирусные базы устарели", DiagnosticCategory.Security, Severity.Medium, Confidence.High,
                s.Summary(C.SecSignatures), "Обновление сигнатур не выполняется (нет сети, WSUS, политика).",
                "Обновите сигнатуры Microsoft Defender.", C.SecSignatures)
            .Line(s, C.NetInternetIp, "Интернет доступен", "Интернет недоступен")
            .Fix(A.DefenderUpdateSignatures)),

        new DelegateRule("security.uac", s => !s.Failed(C.SecUac) ? null :
            F("security.uac", "Контроль учётных записей (UAC) отключён", DiagnosticCategory.Security, Severity.High, Confidence.High,
                s.Summary(C.SecUac), "EnableLUA = 0: все программы администратора работают с полными правами.",
                "Включите UAC через политику или реестр (требуется перезагрузка) по согласованию с ИБ.", C.SecUac)),

        // ───────────── SERVICES ─────────────
        new DelegateRule("services.critical", s => !s.Failed(C.ServicesCritical) ? null :
            F("services.critical", "Важные системные службы не работают", DiagnosticCategory.Services, Severity.High, Confidence.High,
                s.Summary(C.ServicesCritical), "Остановлены службы, от которых зависят сеть, DNS, обновления или печать.",
                "Запустите указанные службы и проверьте, почему они остановились (журнал System).", C.ServicesCritical)
            .Fix(A.OpenServices, A.OpenEventViewer)),

        // ───────────── WI-FI ─────────────
        new DelegateRule("wifi.stage", s => !s.Failed(C.WifiStage) ? null :
            F("wifi.stage", "Wi-Fi подключён, но связь отсутствует", DiagnosticCategory.WiFi, Severity.High, Confidence.Medium,
                s.Summary(C.WifiStage), s.Get(C.WifiStage)?.Details ?? "Определён этап отказа подключения.",
                s.Get(C.WifiStage)?.Recommendation ?? "Переподключитесь к сети Wi-Fi.", C.WifiStage, C.WifiIp, C.WifiGateway)
            .Line(s, C.WifiInterface, "Wi-Fi подключён", "Wi-Fi не подключён")
            .Line(s, C.WifiIp, "IP-адрес по Wi-Fi получен", "IP-адрес по Wi-Fi не получен")
            .Line(s, C.WifiGateway, "Шлюз Wi-Fi доступен", "Шлюз Wi-Fi недоступен")
            .Line(s, C.NetInternetIp, "Интернет по IP работает", "Нет Интернета по IP")
            .Fix(A.RenewIp, A.OpenWifiSettings)),

        new DelegateRule("wifi.weak", s => !s.FailedOrWarn(C.WifiSignal) ? null :
            F("wifi.weak", "Слабый сигнал Wi-Fi", DiagnosticCategory.WiFi, Severity.Medium, Confidence.Medium,
                s.Summary(C.WifiSignal), "Слабый сигнал вызывает обрывы и низкую скорость.",
                "Приблизьтесь к точке доступа, используйте 5 ГГц или кабель.", C.WifiSignal)
            .Line(s, C.NetTcp, "Повторные передачи TCP в норме", "Много повторных передач TCP")),

        // ───────────── APPLICATION ─────────────
        new DelegateRule("app.crash", s => !s.FailedOrWarn(C.AppEvents) ? null :
            F("app.crash", "Программа аварийно завершается", DiagnosticCategory.Application, Severity.High,
                string.IsNullOrEmpty(s.Evidence(C.AppEvents, "faultingModule")) ? Confidence.Medium : Confidence.High,
                s.Summary(C.AppEvents),
                string.IsNullOrEmpty(s.Evidence(C.AppEvents, "faultingModule"))
                    ? "В журнале Application есть сбои этой программы."
                    : $"Сбой в модуле {s.Evidence(C.AppEvents, "faultingModule")}: повреждённая установка, несовместимая надстройка или компонент (.NET/VC++).",
                "Переустановите/восстановите программу и необходимые компоненты; проверьте обновления программы.", C.AppEvents)
            .Line(s, C.AppFile, "Файл программы найден", "Файл программы не найден")
            .Fix(A.OpenEventViewer)),

        new DelegateRule("app.missing", s => !s.Failed(C.AppFile) ? null :
            F("app.missing", "Исполняемый файл программы не найден", DiagnosticCategory.Application, Severity.High, Confidence.High,
                s.Summary(C.AppFile), "Программа удалена, перемещена или ярлык указывает на неверный путь.",
                "Проверьте путь ярлыка и переустановите программу.", C.AppFile)),

        // ───────────── NETWORK SHARE ─────────────
        new DelegateRule("share.dns", s => !s.Failed(C.ShareDns) ? null :
            F("share.dns", "Имя сервера сетевого ресурса не разрешается", DiagnosticCategory.NetworkShare, Severity.High, Confidence.High,
                s.Summary(C.ShareDns), "DNS не знает имя файлового сервера.",
                "Проверьте имя сервера и DNS; попробуйте подключиться по IP-адресу.", C.ShareDns)
            .Line(s, C.DnsResolveExternal, "Внешние имена разрешаются", "DNS не работает в целом")
            .Fix(A.FlushDns)),

        new DelegateRule("share.unreachable", s => !s.Failed(C.ShareSmb) ? null :
            F("share.unreachable", "Файловый сервер недоступен по SMB (TCP 445)", DiagnosticCategory.NetworkShare, Severity.High,
                s.IsOk(C.SharePing) ? Confidence.High : Confidence.Medium,
                s.Summary(C.ShareSmb),
                s.IsOk(C.SharePing) ? "Сервер отвечает, но порт 445 закрыт: брандмауэр или служба Server остановлена." : "Сервер недоступен по сети (выключен, VPN, маршрут).",
                "Проверьте доступность сервера и порт 445 (брандмауэр, VPN).", C.ShareSmb, C.SharePing)
            .Line(s, C.SharePing, "Сервер отвечает на ping", "Сервер не отвечает на ping")),

        new DelegateRule("share.access", s => !s.Failed(C.ShareAccess) || s.Failed(C.ShareSmb) ? null :
            F("share.access", "Нет доступа к сетевой папке", DiagnosticCategory.NetworkShare, Severity.Medium, Confidence.Medium,
                s.Summary(C.ShareAccess), "Сервер доступен, но папка не открывается: права доступа, неверный путь или учётные данные.",
                "Проверьте путь, права пользователя на ресурс и сохранённые учётные данные.", C.ShareAccess)
            .Line(s, C.ShareSmb, "Порт SMB открыт", "Порт SMB закрыт")),
    };
}
