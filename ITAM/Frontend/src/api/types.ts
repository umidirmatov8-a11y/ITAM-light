export type Guid = string;

export type AssetStateKind = 'Ordered' | 'InStock' | 'Assigned' | 'Reserved' | 'InRepair' | 'Lost' | 'Stolen' | 'Disposed' | 'WrittenOff' | 'Archived';
export type EmployeeStatusKind = 'Active' | 'Leave' | 'Suspended' | 'Terminated' | 'Archived';
export type AssetCondition = 'New' | 'Good' | 'Fair' | 'Poor' | 'Broken';
export type OperationType = 'Issue' | 'Return' | 'Transfer' | 'StatusChange' | 'Repair';
export type SignatureStatus = 'NotRequired' | 'Pending' | 'Signed' | 'Refused';
export type SignatureMethod = 'None' | 'Paper' | 'Scan' | 'Electronic';
export type RepairStage = 'Created' | 'Sent' | 'Diagnostics' | 'Repairing' | 'WaitingParts' | 'Completed' | 'Returned' | 'Cancelled';
export type LicenseModel = 'PerUser' | 'PerDevice' | 'Subscription' | 'Perpetual' | 'Volume' | 'Concurrent' | 'Site';
export type AccessStatus = 'Requested' | 'Active' | 'Suspended' | 'Revoked';
export type ChecklistKind = 'Onboarding' | 'Offboarding';
export type ChecklistStatus = 'InProgress' | 'Completed' | 'Cancelled';
export type DocumentType = 'EquipmentIssue' | 'EquipmentReturn' | 'EquipmentTransfer' | 'EquipmentRepair' | 'EmployeeOnboarding' | 'EmployeeOffboarding' | 'InventoryAct' | 'WriteOffAct' | 'Other';
export type CustomFieldType = 'Text' | 'Number' | 'Date' | 'DateTime' | 'Boolean' | 'Dropdown' | 'MultiSelect' | 'Url' | 'Email' | 'Currency' | 'LongText';
export type CustomFieldEntity = 'Employee' | 'Asset' | 'License' | 'Software' | 'Repair' | 'Access' | 'Department' | 'Location';

export interface Me {
  id: Guid;
  userName: string;
  displayName: string;
  email?: string;
  employeeId?: Guid;
  allRegions: boolean;
  regions: { id: Guid; name: string }[];
  roles: string[];
  permissions: string[];
  mustChangePassword: boolean;
  language?: string;
  timeZone?: string;
  preferences?: string;
  lastLoginAt?: string;
  organizationName: string;
  orgTimeZone: string;
  currency: string;
  dateFormat: string;
}

export interface EmployeeListItem {
  id: Guid; employeeNumber: string; fullName: string; login?: string; email?: string; phone?: string;
  positionId?: Guid; positionName?: string; departmentId?: Guid; departmentName?: string; regionId: Guid; regionName?: string;
  locationId?: Guid; locationName?: string; statusId: Guid; statusName?: string; statusColor?: string; statusKind: EmployeeStatusKind;
  hireDate?: string; terminationDate?: string; assetCount: number; photoFileId?: Guid;
}

export interface Employee {
  id: Guid; employeeNumber: string; lastName: string; firstName: string; middleName?: string; fullName: string;
  login?: string; email?: string; phone?: string; positionId?: Guid; positionName?: string; departmentId?: Guid; departmentName?: string;
  departmentPath?: string; regionId: Guid; regionName?: string; locationId?: Guid; locationName?: string; roomId?: Guid; roomName?: string;
  managerId?: Guid; managerName?: string; hireDate?: string; terminationDate?: string; statusId: Guid; statusName?: string; statusColor?: string;
  statusKind: EmployeeStatusKind; comment?: string; photoFileId?: Guid; customFields?: Record<string, unknown> | null; externalId?: string;
  createdAt: string; updatedAt?: string; version: number; assetCount: number; licenseCount: number; accessCount: number;
}

export interface AssetListItem {
  id: Guid; inventoryNumber: string; name: string; assetTypeId: Guid; typeName?: string; categoryName?: string; manufacturerName?: string;
  model?: string; serialNumber?: string; statusId: Guid; statusName?: string; statusColor?: string; statusKind: AssetStateKind;
  employeeId?: Guid; employeeName?: string; departmentId?: Guid; departmentName?: string; regionId: Guid; regionName?: string;
  locationId?: Guid; locationName?: string; responsibleEmployeeId?: Guid; responsibleName?: string; purchaseDate?: string;
  purchasePrice?: number; currency?: string; warrantyExpiration?: string; hostname?: string; ipAddress?: string; condition: AssetCondition;
  customFields?: Record<string, unknown> | null; createdAt: string;
}

export interface DepreciationInfo {
  method: string; usefulLifeMonths: number; monthsElapsed: number; cost: number; salvage: number; monthlyAmount: number;
  accumulated: number; bookValue: number; fullyDepreciatedOn: string; isFullyDepreciated: boolean;
}

export interface Asset {
  id: Guid; inventoryNumber: string; name: string; assetTypeId: Guid; typeName?: string; typePrefix?: string; categoryId?: Guid; categoryName?: string;
  manufacturerId?: Guid; manufacturerName?: string; model?: string; serialNumber?: string; statusId: Guid; statusName?: string; statusColor?: string;
  statusKind: AssetStateKind; employeeId?: Guid; employeeName?: string; employeeNumber?: string; departmentId?: Guid; departmentName?: string;
  regionId: Guid; regionName?: string; locationId?: Guid; locationName?: string; responsibleEmployeeId?: Guid; responsibleName?: string;
  parentAssetId?: Guid; parentAssetNumber?: string; hostname?: string; ipAddress?: string; macAddress?: string; purchaseDate?: string;
  purchasePrice?: number; currency?: string; supplierId?: Guid; supplierName?: string; contractId?: Guid; contractNumber?: string;
  invoiceNumber?: string; warrantyExpiration?: string; depreciationMethod: string; usefulLifeMonths?: number; salvageValue?: number;
  depreciation?: DepreciationInfo; condition: AssetCondition; notes?: string; customFields?: Record<string, unknown> | null;
  lastInventoryAt?: string; createdAt: string; updatedAt?: string; version: number;
  currentAssignment?: { assignmentId: Guid; batchId: Guid; batchNumber: string; effectiveFrom: string; recordedAt: string; expectedReturnDate?: string; accessories?: string };
  components: { id: Guid; inventoryNumber: string; name: string; statusName?: string }[];
  openRepair?: { id: Guid; number: string; status: string; openedAt: string };
}

export interface TimelineItem {
  date: string; recordedAt?: string; type: string; title: string; description?: string; link?: string; user?: string;
  isBackdated: boolean; isCancelled: boolean; color?: string;
}

export interface AssetEvent {
  id: Guid; sequence: number; eventType: string; affectsState: boolean; effectiveAt: string; recordedAt: string; recordedByName?: string;
  operationType?: OperationType; operationId?: Guid; batchId?: Guid; description?: string; data?: any; statusName?: string; employeeName?: string;
  departmentName?: string; regionName?: string; locationName?: string; isCancelled: boolean; cancelReason?: string; isBackdated: boolean;
}

export interface BatchListItem {
  id: Guid; number: string; type: OperationType; effectiveAt: string; recordedAt: string; createdBy?: string; employeeId?: Guid; employeeName?: string;
  assetCount: number; assetNumbers?: string; isBackdated: boolean; isCancelled: boolean; employeeSignatureStatus: SignatureStatus; comment?: string; documentCount: number;
}

export interface Batch {
  id: Guid; number: string; type: OperationType; effectiveAt: string; recordedAt: string; createdBy?: string; employeeId?: Guid; employeeName?: string;
  employeeSnapshot?: any; responsibleEmployeeId?: Guid; responsibleSnapshot?: any; comment?: string; isBackdated: boolean; isCancelled: boolean;
  cancelReason?: string; cancelledAt?: string; employeeSignatureStatus: SignatureStatus; responsibleSignatureStatus: SignatureStatus; signedAt?: string;
  signatureMethod: SignatureMethod;
  lines: { id: Guid; assetId: Guid; inventoryNumber: string; assetName: string; serialNumber?: string; condition?: AssetCondition; accessories?: string;
    damage?: string; missingItems?: string; from?: string; to?: string; comment?: string; effectiveTo?: string; isCancelled: boolean }[];
  documents: { id: Guid; number: string; title: string; createdAt: string; docxFileId?: Guid; pdfFileId?: Guid; templateVersion: number }[];
}

export interface OperationResult { batchId: Guid; number: string; type: OperationType; assetCount: number; isBackdated: boolean; documentId?: Guid; repairIds?: Guid[] }

export interface Repair {
  id: Guid; number: string; assetId: Guid; inventoryNumber: string; assetName: string; serialNumber?: string; statusId: Guid; statusName: string;
  statusColor?: string; stage: RepairStage; openedAt: string; recordedAt: string; sentAt?: string; serviceCenterId?: Guid; serviceCenterName?: string;
  problem: string; diagnosis?: string; repairDescription?: string; parts?: string; cost?: number; currency?: string; isWarranty: boolean;
  expectedReturnDate?: string; actualReturnAt?: string; technician?: string; comment?: string; employeeId?: Guid; employeeName?: string;
  customFields?: any; version: number; history: { id: Guid; statusName: string; changedAt: string; recordedAt: string; recordedByName?: string; comment?: string }[];
}

export interface RepairListItem {
  id: Guid; number: string; assetId: Guid; inventoryNumber: string; assetName: string; statusId: Guid; statusName: string; statusColor?: string;
  stage: RepairStage; openedAt: string; sentAt?: string; serviceCenterName?: string; problem: string; cost?: number; currency?: string; isWarranty: boolean;
  expectedReturnDate?: string; actualReturnAt?: string; technician?: string; regionName?: string; isOverdue: boolean;
}

export interface LicenseListItem {
  id: Guid; name: string; softwareId?: Guid; softwareName?: string; vendorName?: string; licenseTypeName?: string; model: LicenseModel;
  seats: number; usedSeats: number; availableSeats: number; expiredSeats: number; purchaseDate?: string; expirationDate?: string;
  renewalDate?: string; cost?: number; currency?: string; regionName?: string; isExpired: boolean; daysToExpiry?: number; isArchived: boolean; hasKey: boolean;
}

export interface License extends Omit<LicenseListItem, 'hasKey' | 'vendorName' | 'licenseTypeName' | 'regionName'> {
  vendorId?: Guid; vendorName?: string; supplierId?: Guid; supplierName?: string; licenseTypeId?: Guid; licenseTypeName?: string;
  licenseKeyMasked?: string; contractId?: Guid; contractNumber?: string; notes?: string; regionId?: Guid; regionName?: string;
  customFields?: any; version: number; createdAt: string;
}

export interface LicenseAssignment {
  id: Guid; licenseId: Guid; licenseName: string; softwareName?: string; employeeId?: Guid; employeeName?: string; assetId?: Guid;
  assetInventoryNumber?: string; assignedAt: string; revokedAt?: string; recordedAt: string; seatCount: number; comment?: string; revokeReason?: string;
}

export interface AccessItem {
  id: Guid; employeeId: Guid; employeeName: string; employeeNumber?: string; departmentName?: string; regionName?: string; accessSystemId: Guid;
  systemName: string; accessLevelId?: Guid; levelName?: string; username?: string; role?: string; grantedAt: string; revokedAt?: string;
  recordedAt: string; status: AccessStatus; responsibleEmployeeId?: Guid; responsibleName?: string; requestReference?: string;
  reviewDueDate?: string; lastReviewedAt?: string; comment?: string; revokeReason?: string; customFields?: any; employeeTerminated: boolean;
}

export interface ChecklistItem {
  id: Guid; title: string; description?: string; actionType: string; targetId?: Guid; targetName?: string; isRequired: boolean; isDone: boolean;
  isAuto: boolean; doneAt?: string; doneByName?: string; comment?: string;
}
export interface Checklist {
  id: Guid; employeeId: Guid; employeeName: string; title: string; kind: ChecklistKind; status: ChecklistStatus; startedAt: string;
  dueDate?: string; completedAt?: string; comment?: string; done: number; total: number; items: ChecklistItem[];
}

export interface DocumentItem {
  id: Guid; number: string; title: string; documentType: DocumentType; sourceType: string; sourceId?: Guid; employeeId?: Guid; employeeName?: string;
  assetId?: Guid; templateName?: string; templateVersionNumber: number; docxFileId?: Guid; pdfFileId?: Guid; employeeSignatureStatus: SignatureStatus;
  responsibleSignatureStatus: SignatureStatus; employeeSignedAt?: string; signatureMethod: SignatureMethod; signedScanFileId?: Guid;
  isVoided: boolean; voidReason?: string; createdAt: string; createdByName?: string;
}

export interface StoredFile { id: Guid; fileName: string; contentType: string; size: number; sha256: string; category: string; description?: string; createdAt: string; createdByName?: string }

export interface CustomFieldDef {
  id: Guid; entityType: CustomFieldEntity; assetTypeId?: Guid; assetTypeName?: string; key: string; label: string; dataType: CustomFieldType;
  options: string[]; isRequired: boolean; isSearchable: boolean; showInList: boolean; defaultValue?: string; helpText?: string; group?: string;
  sortOrder: number; isArchived: boolean;
}

export interface NotificationItem { id: Guid; type: string; severity: 'Info' | 'Warning' | 'Critical'; title: string; message: string; link?: string; createdAt: string; isRead: boolean }

export type LookupItem = Record<string, any> & { id: Guid; name: string; code?: string; isArchived: boolean };
