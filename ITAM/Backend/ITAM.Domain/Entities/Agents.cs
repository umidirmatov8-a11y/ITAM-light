using ITAM.Domain.Common;
using ITAM.Domain.Enums;

namespace ITAM.Domain.Entities;

/// <summary>
/// A computer reporting through the ITAM Windows agent. Holds the latest inventory snapshot; the device is linked to an
/// <see cref="Asset"/> (matched by serial number / host name, created automatically or linked manually).
/// Not audited row by row: inventory arrives every few hours, meaningful changes are written to the asset timeline instead.
/// </summary>
public class AgentDevice : Entity, ITenantEntity
{
    public Guid OrganizationId { get; set; }
    /// <summary>Windows MachineGuid (stable per OS installation), sent by the agent on registration.</summary>
    public string MachineId { get; set; } = string.Empty;
    /// <summary>SHA-256 of the per-device secret issued at registration.</summary>
    public string TokenHash { get; set; } = string.Empty;
    public AgentDeviceStatus Status { get; set; }
    public Guid? AssetId { get; set; }
    public Asset? Asset { get; set; }

    public string Hostname { get; set; } = string.Empty;
    public string? Domain { get; set; }
    public string? Manufacturer { get; set; }
    public string? Model { get; set; }
    public string? SerialNumber { get; set; }
    public string? HardwareUuid { get; set; }
    /// <summary>Laptop | Desktop | AllInOne | Server | Tablet | Virtual | Other.</summary>
    public string? FormFactor { get; set; }
    public string? OsName { get; set; }
    public string? OsVersion { get; set; }
    public string? OsBuild { get; set; }
    public string? OsArchitecture { get; set; }
    public DateTime? OsInstallDate { get; set; }
    public DateTime? LastBootAt { get; set; }
    public string? Cpu { get; set; }
    public int? CpuCores { get; set; }
    public int? RamMb { get; set; }
    public int? StorageGb { get; set; }
    public string? IpAddress { get; set; }
    public string? MacAddress { get; set; }
    public string? BiosVersion { get; set; }
    /// <summary>DOMAIN\user of the interactive session at the time of the last report.</summary>
    public string? CurrentUser { get; set; }
    public Guid? CurrentEmployeeId { get; set; }
    public string? Antivirus { get; set; }
    public string? AgentVersion { get; set; }
    /// <summary>jsonb: disks, volumes, network adapters, monitors, GPUs, printers.</summary>
    public string? Data { get; set; }
    public int SoftwareCount { get; set; }

    public DateTime RegisteredAt { get; set; }
    public DateTime? LastSeenAt { get; set; }
    public string? LastIp { get; set; }
    public string? Comment { get; set; }
    public List<DiscoveredSoftware> Software { get; set; } = new();
}

/// <summary>Installed program reported by the agent (replaced on every inventory).</summary>
public class DiscoveredSoftware : Entity
{
    public Guid DeviceId { get; set; }
    public AgentDevice? Device { get; set; }
    public string Name { get; set; } = string.Empty;
    public string? Version { get; set; }
    public string? Publisher { get; set; }
    public DateOnly? InstallDate { get; set; }
}
