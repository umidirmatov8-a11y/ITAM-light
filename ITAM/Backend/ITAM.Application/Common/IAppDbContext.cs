using ITAM.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace ITAM.Application.Common;

public interface IAppDbContext
{
    DbSet<Organization> Organizations { get; }
    DbSet<Region> Regions { get; }
    DbSet<Location> Locations { get; }
    DbSet<Department> Departments { get; }
    DbSet<Position> Positions { get; }
    DbSet<EmployeeStatus> EmployeeStatuses { get; }
    DbSet<Employee> Employees { get; }
    DbSet<EmployeeOrgHistory> EmployeeOrgHistory { get; }
    DbSet<AssetCategory> AssetCategories { get; }
    DbSet<AssetType> AssetTypes { get; }
    DbSet<AssetStatus> AssetStatuses { get; }
    DbSet<Manufacturer> Manufacturers { get; }
    DbSet<Supplier> Suppliers { get; }
    DbSet<Contract> Contracts { get; }
    DbSet<Asset> Assets { get; }
    DbSet<AssetEvent> AssetEvents { get; }
    DbSet<CustomFieldDefinition> CustomFieldDefinitions { get; }
    DbSet<NumberSequence> NumberSequences { get; }
    DbSet<OperationBatch> OperationBatches { get; }
    DbSet<Assignment> Assignments { get; }
    DbSet<AssetReturn> AssetReturns { get; }
    DbSet<AssetTransfer> AssetTransfers { get; }
    DbSet<AssetStatusChange> AssetStatusChanges { get; }
    DbSet<RepairStatus> RepairStatuses { get; }
    DbSet<Repair> Repairs { get; }
    DbSet<RepairStatusHistory> RepairStatusHistory { get; }
    DbSet<Software> Software { get; }
    DbSet<LicenseType> LicenseTypes { get; }
    DbSet<License> Licenses { get; }
    DbSet<LicenseAssignment> LicenseAssignments { get; }
    DbSet<AccessSystem> AccessSystems { get; }
    DbSet<AccessLevel> AccessLevels { get; }
    DbSet<EmployeeAccess> EmployeeAccesses { get; }
    DbSet<ChecklistTemplate> ChecklistTemplates { get; }
    DbSet<ChecklistTemplateItem> ChecklistTemplateItems { get; }
    DbSet<EmployeeChecklist> EmployeeChecklists { get; }
    DbSet<EmployeeChecklistItem> EmployeeChecklistItems { get; }
    DbSet<DocumentTemplate> DocumentTemplates { get; }
    DbSet<DocumentTemplateVersion> DocumentTemplateVersions { get; }
    DbSet<GeneratedDocument> GeneratedDocuments { get; }
    DbSet<StoredFile> StoredFiles { get; }
    DbSet<User> Users { get; }
    DbSet<Role> Roles { get; }
    DbSet<Permission> Permissions { get; }
    DbSet<RolePermission> RolePermissions { get; }
    DbSet<UserRole> UserRoles { get; }
    DbSet<UserRegion> UserRegions { get; }
    DbSet<UserSession> UserSessions { get; }
    DbSet<ApiToken> ApiTokens { get; }
    DbSet<AuditLog> AuditLogs { get; }
    DbSet<Notification> Notifications { get; }
    DbSet<NotificationRead> NotificationReads { get; }
    DbSet<NotificationDelivery> NotificationDeliveries { get; }
    DbSet<Setting> Settings { get; }
    DbSet<Backup> Backups { get; }
    DbSet<ImportJob> ImportJobs { get; }
    DbSet<InventoryCampaign> InventoryCampaigns { get; }
    DbSet<InventoryCampaignItem> InventoryCampaignItems { get; }
    DbSet<StockItem> StockItems { get; }
    DbSet<StockBalance> StockBalances { get; }
    DbSet<StockMovement> StockMovements { get; }

    DatabaseFacade Database { get; }
    Microsoft.EntityFrameworkCore.Metadata.IModel Model { get; }
    DbSet<T> Set<T>() where T : class;
    Task<int> SaveChangesAsync(CancellationToken ct = default);
}
