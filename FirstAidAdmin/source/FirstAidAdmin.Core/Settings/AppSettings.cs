namespace FirstAidAdmin.Core.Settings;

public enum UiMode { HelpDesk, Administrator }
public enum AppTheme { Light, Dark }
public enum ReportFormat { Html, Json, Both }

public sealed class GeneralSettings
{
    public string Language { get; set; } = "ru";
    public AppTheme Theme { get; set; } = AppTheme.Light;
    public UiMode Mode { get; set; } = UiMode.Administrator;
}

public sealed class DiagnosticsSettings
{
    public int CommandTimeoutSeconds { get; set; } = 60;
    public int PingTimeoutMs { get; set; } = 1500;
    public int PingCount { get; set; } = 3;
    public int TcpTimeoutMs { get; set; } = 2000;
    /// <summary>Public IPs used to test Internet reachability without DNS.</summary>
    public List<string> InternetProbeIps { get; set; } = new() { "8.8.8.8", "1.1.1.1" };
    /// <summary>Public DNS servers used as a reference when the configured server fails.</summary>
    public List<string> ReferenceDnsServers { get; set; } = new() { "8.8.8.8", "1.1.1.1" };
    public List<string> ExternalTestNames { get; set; } = new() { "www.microsoft.com", "www.google.com" };
    public string HttpProbeUrl { get; set; } = "http://www.msftconnecttest.com/connecttest.txt";
    public string HttpProbeExpected { get; set; } = "Microsoft Connect Test";
    public int EventLogHours { get; set; } = 24;
    public int EventLogMaxEvents { get; set; } = 2000;
    public int DiskWarningPercent { get; set; } = 85;
    public int DiskCriticalPercent { get; set; } = 95;
    public int RamWarningPercent { get; set; } = 80;
    public int RamCriticalPercent { get; set; } = 92;
    public int CpuWarningPercent { get; set; } = 80;
    public int UptimeWarningDays { get; set; } = 14;
    public int UpdateWarningDays { get; set; } = 45;
    public int TimeSkewWarningSeconds { get; set; } = 60;
    public int TimeSkewCriticalSeconds { get; set; } = 300;
    /// <summary>Module ids excluded from full diagnostics.</summary>
    public List<string> DisabledModules { get; set; } = new();
    public bool LoadPlugins { get; set; }
}

public sealed class SecuritySettings
{
    /// <summary>Always true in practice: remediation is never silent. Kept for explicit documentation.</summary>
    public bool ConfirmRemediation { get; set; } = true;
    public bool RedactUserNames { get; set; } = true;
    public bool RedactHostNames { get; set; }
    public bool RedactDomain { get; set; }
    public bool RedactIpAddresses { get; set; }
    public string UserPlaceholder { get; set; } = "USER";
    public string HostPlaceholder { get; set; } = "HOST";
    public string DomainPlaceholder { get; set; } = "DOMAIN";
}

public sealed class ReportSettings
{
    /// <summary>Empty means %USERPROFILE%\Documents\FirstAidAdmin\Reports.</summary>
    public string ReportFolder { get; set; } = "";
    public ReportFormat Format { get; set; } = ReportFormat.Both;
    public bool AutoZip { get; set; }
}

public sealed class AiSettings
{
    /// <summary>Optional AI assistant is disabled by default; the app is fully functional offline.</summary>
    public bool Enabled { get; set; }
    public string Provider { get; set; } = "";
    public string Endpoint { get; set; } = "";
}

public sealed class AppSettings
{
    public GeneralSettings General { get; set; } = new();
    public DiagnosticsSettings Diagnostics { get; set; } = new();
    public SecuritySettings Security { get; set; } = new();
    public ReportSettings Reports { get; set; } = new();
    public AiSettings Ai { get; set; } = new();
    /// <summary>Telemetry is OFF and not implemented. Nothing is ever sent outside.</summary>
    public bool Telemetry { get; set; }

    public string ResolveReportFolder()
    {
        if (!string.IsNullOrWhiteSpace(Reports.ReportFolder)) return Reports.ReportFolder;
        var docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
        if (string.IsNullOrEmpty(docs)) docs = Path.GetTempPath();
        return Path.Combine(docs, "FirstAidAdmin", "Reports");
    }
}
