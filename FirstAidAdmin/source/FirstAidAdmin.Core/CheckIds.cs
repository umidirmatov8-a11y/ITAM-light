namespace FirstAidAdmin.Core;

/// <summary>Stable identifiers of modules and checks shared by modules, correlation rules, tests and the knowledge base.</summary>
public static class ModuleIds
{
    public const string Network = "network";
    public const string Dns = "dns";
    public const string WiFi = "wifi";
    public const string Domain = "domain";
    public const string ActiveDirectory = "ad";
    public const string Rdp = "rdp";
    public const string Printer = "printer";
    public const string WindowsUpdate = "windowsupdate";
    public const string Storage = "storage";
    public const string WindowsHealth = "windowshealth";
    public const string Sfc = "sfc";
    public const string DismScan = "dismscan";
    public const string Security = "security";
    public const string Performance = "performance";
    public const string EventLog = "eventlog";
    public const string Services = "services";
    public const string Application = "application";
    public const string NetworkShare = "share";
}

public static class CheckIds
{
    // Network
    public const string NetAdapters = "network.adapters";
    public const string NetIPv4 = "network.ipv4";
    public const string NetIPv6 = "network.ipv6";
    public const string NetDhcp = "network.dhcp";
    public const string NetGatewayConfigured = "network.gateway.configured";
    public const string NetGatewayPing = "network.gateway.ping";
    public const string NetGatewayArp = "network.gateway.arp";
    public const string NetInternetIp = "network.internet.ip";
    public const string NetDnsResolve = "network.dns.resolve";
    public const string NetHttp = "network.http";
    public const string NetProxy = "network.proxy";
    public const string NetRoutes = "network.routes";
    public const string NetTcp = "network.tcp";
    public const string NetUdp = "network.udp";

    // DNS
    public const string DnsClientService = "dns.client.service";
    public const string DnsServersConfigured = "dns.servers.configured";
    public const string DnsServerReachable = "dns.server.reachable";
    public const string DnsResolveExternal = "dns.resolve.external";
    public const string DnsResolveInternal = "dns.resolve.internal";
    public const string DnsReference = "dns.reference";
    public const string DnsSuffix = "dns.suffix";
    public const string DnsCache = "dns.cache";
    public const string DnsDc = "dns.dc";
    public const string DnsSrvLdap = "dns.srv.ldap";
    public const string DnsSrvKerberos = "dns.srv.kerberos";

    // Wi-Fi
    public const string WifiService = "wifi.service";
    public const string WifiInterface = "wifi.interface";
    public const string WifiSignal = "wifi.signal";
    public const string WifiIp = "wifi.ip";
    public const string WifiGateway = "wifi.gateway";
    public const string WifiStage = "wifi.stage";

    // Domain
    public const string DomainMembership = "domain.membership";
    public const string DomainDcDiscovery = "domain.dc.discovery";
    public const string DomainLogonServer = "domain.logonserver";
    public const string DomainSecureChannel = "domain.securechannel";
    public const string DomainDcConnectivity = "domain.dc.connectivity";
    public const string DomainTime = "domain.time";
    public const string DomainGpo = "domain.gpo";
    public const string DomainKerberos = "domain.kerberos";

    // Active Directory
    public const string AdUserContext = "ad.user.context";
    public const string AdDcPorts = "ad.dc.ports";
    public const string AdSysvol = "ad.sysvol";
    public const string AdLogonFailures = "ad.logon.failures";

    // RDP
    public const string RdpService = "rdp.service";
    public const string RdpEnabled = "rdp.enabled";
    public const string RdpNla = "rdp.nla";
    public const string RdpPort = "rdp.port";
    public const string RdpListening = "rdp.listening";
    public const string RdpFirewall = "rdp.firewall";
    public const string RdpTargetPing = "rdp.target.ping";
    public const string RdpTargetTcp = "rdp.target.tcp";

    // Printer
    public const string PrinterSpooler = "printer.spooler";
    public const string PrinterInstalled = "printer.installed";
    public const string PrinterDefault = "printer.default";
    public const string PrinterStatus = "printer.status";
    public const string PrinterQueue = "printer.queue";
    public const string PrinterNetwork = "printer.network";

    // Windows Update
    public const string WuService = "wu.service";
    public const string WuBits = "wu.bits";
    public const string WuRelated = "wu.related";
    public const string WuLastUpdate = "wu.lastupdate";
    public const string WuHistoryErrors = "wu.history.errors";
    public const string WuEvents = "wu.events";
    public const string WuPendingReboot = "wu.pendingreboot";
    public const string WuPolicy = "wu.policy";

    // Storage
    public const string StorageSystem = "storage.system";
    public const string StorageDrives = "storage.drives";
    public const string StorageTemp = "storage.temp";
    public const string StoragePhysical = "storage.physical";
    public const string StoragePerformance = "storage.performance";
    public const string StorageEvents = "storage.events";

    // Windows health
    public const string HealthDism = "health.dism.check";
    public const string HealthDismScan = "health.dism.scan";
    public const string HealthSfc = "health.sfc.verify";
    public const string HealthCbs = "health.cbs";
    public const string HealthPendingReboot = "health.reboot.pending";
    public const string HealthCrashes = "health.crashes";

    // Security
    public const string SecDefender = "security.defender";
    public const string SecAntivirus = "security.av";
    public const string SecFirewall = "security.firewall";
    public const string SecUac = "security.uac";
    public const string SecSignatures = "security.signatures";

    // Performance
    public const string PerfCpu = "perf.cpu";
    public const string PerfRam = "perf.ram";
    public const string PerfUptime = "perf.uptime";
    public const string PerfProcesses = "perf.processes";
    public const string PerfDisk = "perf.disk";
    public const string PerfStartup = "perf.startup";
    public const string PerfServices = "perf.services";
    public const string PerfBoot = "perf.boot";

    // Event logs
    public const string EventsSystem = "events.system";
    public const string EventsApplication = "events.application";
    public const string EventsWindowsUpdate = "events.windowsupdate";
    public const string EventsSecurity = "events.security";

    // Services
    public const string ServicesCritical = "services.critical";
    public const string ServicesAutoStopped = "services.autostopped";
    public const string ServicesTarget = "services.target";

    // Application
    public const string AppFile = "app.file";
    public const string AppProcess = "app.process";
    public const string AppLaunch = "app.launch";
    public const string AppEvents = "app.events";
    public const string AppAccess = "app.access";
    public const string AppNetwork = "app.network";
    public const string AppServices = "app.services";

    // Network share
    public const string SharePath = "share.path";
    public const string ShareDns = "share.dns";
    public const string SharePing = "share.ping";
    public const string ShareSmb = "share.smb";
    public const string ShareAccess = "share.access";
    public const string ShareWorkstation = "share.workstation";
}

/// <summary>Remediation action ids (catalog lives in FirstAidAdmin.Remediation).</summary>
public static class ActionIds
{
    public const string FlushDns = "flushdns";
    public const string RegisterDns = "registerdns";
    public const string RenewIp = "renewip";
    public const string RestartService = "restart-service";
    public const string StartService = "start-service";
    public const string RestartSpooler = "restart-spooler";
    public const string ClearPrintQueue = "clear-print-queue";
    public const string RestartWindowsUpdate = "restart-wu";
    public const string ResetWindowsUpdateCache = "reset-wu-cache";
    public const string ClearUserTemp = "clear-user-temp";
    public const string TimeResync = "w32tm-resync";
    public const string GpUpdate = "gpupdate";
    public const string DismCheckHealth = "dism-checkhealth";
    public const string DismScanHealth = "dism-scanhealth";
    public const string DismRestoreHealth = "dism-restorehealth";
    public const string SfcVerify = "sfc-verifyonly";
    public const string SfcScanNow = "sfc-scannow";
    public const string ChkdskScan = "chkdsk-scan";
    public const string ChkdskFix = "chkdsk-f";
    public const string ChkdskRepair = "chkdsk-r";
    public const string WinsockReset = "winsock-reset";
    public const string DefenderUpdateSignatures = "defender-update";
    public const string OpenNetworkConnections = "open-ncpa";
    public const string OpenServices = "open-services";
    public const string OpenEventViewer = "open-eventvwr";
    public const string OpenPrinters = "open-printers";
    public const string OpenWindowsUpdate = "open-windowsupdate";
    public const string OpenDiskCleanup = "open-cleanmgr";
    public const string OpenTaskManager = "open-taskmgr";
    public const string OpenResourceMonitor = "open-resmon";
    public const string OpenStorageSettings = "open-storage";
    public const string OpenRemoteSettings = "open-remote";
    public const string OpenFirewall = "open-firewall";
    public const string OpenWindowsSecurity = "open-security";
    public const string OpenWifiSettings = "open-wifi";
    public const string OpenProxySettings = "open-proxy";
    public const string OpenStartupApps = "open-startup";
}
