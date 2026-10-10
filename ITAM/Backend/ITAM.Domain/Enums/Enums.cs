namespace ITAM.Domain.Enums;

public enum LocationType { City = 0, Branch = 1, Office = 2, Building = 3, Floor = 4, Room = 5, Warehouse = 6, DataCenter = 7, Other = 99 }

public enum DepartmentType { Division = 0, Department = 1, Unit = 2, Group = 3 }

/// <summary>System meaning of an admin-defined employee status.</summary>
public enum EmployeeStatusKind { Active = 0, Leave = 1, Suspended = 2, Terminated = 3, Archived = 4 }

/// <summary>System meaning of an admin-defined asset status. Business rules depend on the kind, not the name.</summary>
public enum AssetStateKind
{
    Ordered = 0,
    InStock = 1,
    Assigned = 2,
    Reserved = 3,
    InRepair = 4,
    Lost = 5,
    Stolen = 6,
    Disposed = 7,
    WrittenOff = 8,
    Archived = 9
}

public enum AssetCondition { New = 0, Good = 1, Fair = 2, Poor = 3, Broken = 4 }

public enum AssetEventType
{
    Created = 0,
    Updated = 1,
    Assigned = 2,
    Returned = 3,
    Transferred = 4,
    StatusChanged = 5,
    RepairOpened = 6,
    RepairUpdated = 7,
    RepairClosed = 8,
    InventoryChecked = 9,
    LicenseAssigned = 10,
    LicenseRevoked = 11,
    DocumentGenerated = 12,
    AttachmentAdded = 13,
    OperationCancelled = 14,
    AgentInventory = 15
}

public enum OperationType { Issue = 0, Return = 1, Transfer = 2, StatusChange = 3, Repair = 4 }

public enum RepairStage { Created = 0, Sent = 1, Diagnostics = 2, Repairing = 3, WaitingParts = 4, Completed = 5, Returned = 6, Cancelled = 7 }

public enum LicenseModel { PerUser = 0, PerDevice = 1, Subscription = 2, Perpetual = 3, Volume = 4, Concurrent = 5, Site = 6 }

public enum AccessStatus { Requested = 0, Active = 1, Suspended = 2, Revoked = 3 }

public enum ChecklistKind { Onboarding = 0, Offboarding = 1 }

public enum ChecklistActionType
{
    Manual = 0,
    IssueAssetType = 1,
    GrantAccess = 2,
    AssignSoftware = 3,
    SignDocuments = 4,
    ReturnAllAssets = 5,
    RevokeAllAccess = 6,
    RevokeAllLicenses = 7,
    CloseRepairs = 8,
    GenerateDocument = 9
}

public enum ChecklistStatus { InProgress = 0, Completed = 1, Cancelled = 2 }

public enum DocumentType
{
    EquipmentIssue = 0,
    EquipmentReturn = 1,
    EquipmentTransfer = 2,
    EquipmentRepair = 3,
    EmployeeOnboarding = 4,
    EmployeeOffboarding = 5,
    InventoryAct = 6,
    WriteOffAct = 7,
    Other = 99
}

public enum SignatureStatus { NotRequired = 0, Pending = 1, Signed = 2, Refused = 3 }

public enum SignatureMethod { None = 0, Paper = 1, Scan = 2, Electronic = 3 }

public enum FileCategory { Document = 0, Template = 1, Attachment = 2, Photo = 3, Logo = 4, Import = 5, Backup = 6, Export = 7 }

public enum NotificationSeverity { Info = 0, Warning = 1, Critical = 2 }

public enum BackupKind { Manual = 0, Scheduled = 1, PreRestore = 2 }

public enum BackupStatus { Running = 0, Completed = 1, Failed = 2 }

public enum ImportStatus { Uploaded = 0, Validated = 1, Completed = 2, Failed = 3 }

public enum InventoryCampaignStatus { Draft = 0, InProgress = 1, Completed = 2, Cancelled = 3 }

public enum InventoryItemResult { Pending = 0, Found = 1, Missing = 2, Misplaced = 3, Unexpected = 4 }

public enum StockMovementType { Receipt = 0, Issue = 1, Transfer = 2, Adjustment = 3, UsedInRepair = 4 }

public enum ContractType { Purchase = 0, Lease = 1, Maintenance = 2, License = 3, Support = 4, Other = 99 }

public enum CustomFieldType { Text = 0, Number = 1, Date = 2, DateTime = 3, Boolean = 4, Dropdown = 5, MultiSelect = 6, Url = 7, Email = 8, Currency = 9, LongText = 10 }

public enum CustomFieldEntity { Employee = 0, Asset = 1, License = 2, Software = 3, Repair = 4, Access = 5, Department = 6, Location = 7 }

public enum DepreciationMethod { None = 0, StraightLine = 1, DecliningBalance = 2 }

public enum AgentDeviceStatus { New = 0, Linked = 1, Ignored = 2 }
