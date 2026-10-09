export type AgentStatus = 'New' | 'Linked' | 'Ignored';

export interface AgentDeviceListItem {
  id: string; hostname: string; domain?: string; status: AgentStatus; assetId?: string; assetNumber?: string; assetName?: string;
  manufacturer?: string; model?: string; serialNumber?: string; formFactor?: string; osName?: string; currentUser?: string;
  currentEmployeeId?: string; currentEmployeeName?: string; ipAddress?: string; agentVersion?: string; registeredAt: string;
  lastSeenAt?: string; isStale: boolean; softwareCount: number;
}

export interface AgentDisk { model?: string; serialNumber?: string; sizeGb?: number; mediaType?: string }
export interface AgentVolume { drive?: string; sizeGb?: number; freeGb?: number; fileSystem?: string }
export interface AgentNetwork { name?: string; macAddress?: string; ip: string[]; gateway: string[]; dhcp: boolean }
export interface AgentMonitor { manufacturer?: string; model?: string; serialNumber?: string }

export interface AgentDevice extends Omit<AgentDeviceListItem, 'currentEmployeeName'> {
  assetEmployeeId?: string; assetEmployeeName?: string; hardwareUuid?: string; osVersion?: string; osBuild?: string; osArchitecture?: string;
  osInstallDate?: string; lastBootAt?: string; cpu?: string; cpuCores?: number; ramMb?: number; storageGb?: number; macAddress?: string;
  biosVersion?: string; currentEmployeeName?: string; antivirus?: string; lastIp?: string; comment?: string; userMismatch: boolean;
  data?: { disks?: AgentDisk[]; volumes?: AgentVolume[]; network?: AgentNetwork[]; monitors?: AgentMonitor[]; gpus?: string[]; printers?: string[] };
}

export interface DiscoveredSoftware { id: string; name: string; version?: string; publisher?: string; installDate?: string }
export interface SoftwareSummary { name: string; publisher?: string; devices: number; versions: number; latestVersion?: string }
export interface AgentSummary { total: number; linked: number; new: number; ignored: number; stale: number; reportedToday: number; latestAgentVersion?: string }
export interface AgentSettings {
  enrollmentKey: string; serverUrl?: string; autoCreateAssets: boolean; defaultRegionId?: string; defaultLocationId?: string; updateAssetFields: boolean;
  inventoryIntervalHours: number; staleAfterDays: number;
}

export const ramGb = (mb: number | undefined, unit: string) => (mb ? `${Math.round(mb / 1024)} ${unit}` : '');
