using System.ComponentModel.DataAnnotations;
using System.Text.Json;
using ITAM.Application.Common;
using ITAM.Domain.Enums;

namespace ITAM.Application.Agents;

/// <summary>Settings of the inventory agents (group "agent").</summary>
public sealed class AgentSettings
{
    /// <summary>Shared registration key (protected). Agents present it once to obtain their own device token.</summary>
    public string? EnrollmentKeyProtected { get; set; }
    /// <summary>Create an asset automatically for a computer that matches no existing asset.</summary>
    public bool AutoCreateAssets { get; set; } = true;
    /// <summary>Region (and optional location) for automatically created assets. Without a region, devices wait for manual linking.</summary>
    public Guid? DefaultRegionId { get; set; }
    public Guid? DefaultLocationId { get; set; }
    /// <summary>Keep host name, IP/MAC, model, CPU/RAM/disk/OS of linked assets in sync with the agent data.</summary>
    public bool UpdateAssetFields { get; set; } = true;
    public int InventoryIntervalHours { get; set; } = 4;
    /// <summary>A device that has not reported for this many days is shown as "not reporting".</summary>
    public int StaleAfterDays { get; set; } = 7;
}

public sealed class AgentSettingsDto
{
    public string? EnrollmentKey { get; set; }
    /// <summary>Read-only: public server address from the general settings (what agents should use).</summary>
    public string? ServerUrl { get; set; }
    public bool AutoCreateAssets { get; set; } = true;
    public Guid? DefaultRegionId { get; set; }
    public Guid? DefaultLocationId { get; set; }
    public bool UpdateAssetFields { get; set; } = true;
    [Range(1, 168)] public int InventoryIntervalHours { get; set; } = 4;
    [Range(1, 365)] public int StaleAfterDays { get; set; } = 7;
}

// ---------------------------------------------------------------- agent protocol

public sealed class AgentRegisterRequest
{
    [Required, MaxLength(256)] public string EnrollmentKey { get; set; } = string.Empty;
    [Required, MaxLength(64)] public string MachineId { get; set; } = string.Empty;
    [Required, MaxLength(128)] public string Hostname { get; set; } = string.Empty;
    [MaxLength(64)] public string? AgentVersion { get; set; }
}

public sealed record AgentRegisterResponse(Guid DeviceId, string Token, int IntervalHours);

public sealed record AgentInventoryResponse(Guid DeviceId, int IntervalHours, DateTime ServerTime, string? AssetNumber);

/// <summary>Inventory report sent by the Windows agent (ITAM-Agent.ps1).</summary>
public sealed class AgentInventoryReport
{
    [MaxLength(64)] public string? AgentVersion { get; set; }
    [Required, MaxLength(128)] public string Hostname { get; set; } = string.Empty;
    [MaxLength(256)] public string? Domain { get; set; }
    [MaxLength(256)] public string? Manufacturer { get; set; }
    [MaxLength(256)] public string? Model { get; set; }
    [MaxLength(256)] public string? SerialNumber { get; set; }
    [MaxLength(256)] public string? HardwareUuid { get; set; }
    [MaxLength(64)] public string? FormFactor { get; set; }
    [MaxLength(256)] public string? OsName { get; set; }
    [MaxLength(64)] public string? OsVersion { get; set; }
    [MaxLength(64)] public string? OsBuild { get; set; }
    [MaxLength(64)] public string? OsArchitecture { get; set; }
    public DateTime? OsInstallDate { get; set; }
    public DateTime? LastBootAt { get; set; }
    [MaxLength(256)] public string? Cpu { get; set; }
    public int? CpuCores { get; set; }
    public int? RamMb { get; set; }
    [MaxLength(64)] public string? BiosVersion { get; set; }
    [MaxLength(256)] public string? CurrentUser { get; set; }
    [MaxLength(256)] public string? Antivirus { get; set; }
    public List<AgentDisk> Disks { get; set; } = new();
    public List<AgentVolume> Volumes { get; set; } = new();
    public List<AgentNetworkAdapter> Network { get; set; } = new();
    public List<AgentMonitor> Monitors { get; set; } = new();
    public List<string> Gpus { get; set; } = new();
    public List<string> Printers { get; set; } = new();
    public List<AgentSoftwareItem> Software { get; set; } = new();
}

public sealed class AgentDisk { public string? Model { get; set; } public string? SerialNumber { get; set; } public double? SizeGb { get; set; } public string? MediaType { get; set; } }
public sealed class AgentVolume { public string? Drive { get; set; } public double? SizeGb { get; set; } public double? FreeGb { get; set; } public string? FileSystem { get; set; } }
public sealed class AgentNetworkAdapter { public string? Name { get; set; } public string? MacAddress { get; set; } public List<string> Ip { get; set; } = new(); public List<string> Gateway { get; set; } = new(); public bool Dhcp { get; set; } }
public sealed class AgentMonitor { public string? Manufacturer { get; set; } public string? Model { get; set; } public string? SerialNumber { get; set; } }
public sealed class AgentSoftwareItem { public string? Name { get; set; } public string? Version { get; set; } public string? Publisher { get; set; } public string? InstallDate { get; set; } }

// ---------------------------------------------------------------- admin

public sealed class AgentDeviceQuery : PagedRequest
{
    public AgentDeviceStatus? Status { get; set; }
    /// <summary>true = only devices that have not reported for StaleAfterDays.</summary>
    public bool? Stale { get; set; }
}

public sealed record AgentDeviceListItem(Guid Id, string Hostname, string? Domain, AgentDeviceStatus Status, Guid? AssetId, string? AssetNumber,
    string? AssetName, string? Manufacturer, string? Model, string? SerialNumber, string? FormFactor, string? OsName, string? CurrentUser,
    Guid? CurrentEmployeeId, string? CurrentEmployeeName, string? IpAddress, string? AgentVersion, DateTime RegisteredAt, DateTime? LastSeenAt,
    bool IsStale, int SoftwareCount);

public sealed record AgentDeviceDto(Guid Id, string Hostname, string? Domain, AgentDeviceStatus Status, Guid? AssetId, string? AssetNumber, string? AssetName,
    Guid? AssetEmployeeId, string? AssetEmployeeName, string? Manufacturer, string? Model, string? SerialNumber, string? HardwareUuid, string? FormFactor,
    string? OsName, string? OsVersion, string? OsBuild, string? OsArchitecture, DateTime? OsInstallDate, DateTime? LastBootAt, string? Cpu, int? CpuCores,
    int? RamMb, int? StorageGb, string? IpAddress, string? MacAddress, string? BiosVersion, string? CurrentUser, Guid? CurrentEmployeeId,
    string? CurrentEmployeeName, string? Antivirus, string? AgentVersion, JsonElement? Data, int SoftwareCount, DateTime RegisteredAt, DateTime? LastSeenAt,
    string? LastIp, bool IsStale, string? Comment, bool UserMismatch);

public sealed record DiscoveredSoftwareDto(Guid Id, string Name, string? Version, string? Publisher, DateOnly? InstallDate);

public sealed class AgentLinkRequest { [Required] public Guid AssetId { get; set; } }

public sealed class AgentCreateAssetRequest
{
    public Guid? AssetTypeId { get; set; }
    public Guid? RegionId { get; set; }
    public Guid? LocationId { get; set; }
}

public sealed class AgentSoftwareQuery : PagedRequest { public string? Publisher { get; set; } }

public sealed record SoftwareSummaryItem(string Name, string? Publisher, int Devices, int Versions, string? LatestVersion);

public sealed record AgentSummaryDto(int Total, int Linked, int New, int Ignored, int Stale, int ReportedToday, string? LatestAgentVersion);
