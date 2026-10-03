using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata;

namespace ITAM.Infrastructure.Persistence;

internal static class ModelConfiguration
{
    private static readonly HashSet<string> JsonbNames = new()
    {
        "CustomFields", "Delta", "Data", "Snapshot", "OldValues", "NewValues", "Options", "Placeholders",
        "Mapping", "Errors", "Preferences", "DataSnapshot"
    };

    public static void Configure(ModelBuilder b)
    {
        b.HasPostgresExtension("pg_trgm");
        b.HasSequence<long>("asset_event_seq");

        // ---------------- Organization ----------------
        b.Entity<Organization>(e => { e.Property(x => x.Name).HasMaxLength(256).IsRequired(); });
        Lookup<Region>(b);
        Lookup<Location>(b, e =>
        {
            e.HasOne(x => x.Region).WithMany().HasForeignKey(x => x.RegionId);
            e.HasOne(x => x.Parent).WithMany(x => x.Children).HasForeignKey(x => x.ParentId);
            e.Property(x => x.Address).HasMaxLength(512);
            e.Property(x => x.FullPath).HasMaxLength(1024);
            e.HasIndex(x => x.RegionId);
            e.HasIndex(x => x.ParentId);
        });
        Lookup<Department>(b, e =>
        {
            e.HasOne(x => x.Parent).WithMany(x => x.Children).HasForeignKey(x => x.ParentId);
            e.HasOne(x => x.Region).WithMany().HasForeignKey(x => x.RegionId);
            e.HasOne<Employee>().WithMany().HasForeignKey(x => x.HeadEmployeeId);
            e.Property(x => x.FullPath).HasMaxLength(1024);
            e.Property(x => x.CostCenter).HasMaxLength(64);
        });
        Lookup<Position>(b);

        // ---------------- Employees ----------------
        Lookup<EmployeeStatus>(b, e => e.Property(x => x.Color).HasMaxLength(32));
        b.Entity<Employee>(e =>
        {
            e.Property(x => x.EmployeeNumber).HasMaxLength(64).IsRequired();
            e.Property(x => x.LastName).HasMaxLength(128).IsRequired();
            e.Property(x => x.FirstName).HasMaxLength(128).IsRequired();
            e.Property(x => x.MiddleName).HasMaxLength(128);
            e.Property(x => x.FullName).HasMaxLength(400).IsRequired();
            e.Property(x => x.Login).HasMaxLength(128);
            e.Property(x => x.Email).HasMaxLength(256);
            e.Property(x => x.Phone).HasMaxLength(64);
            e.Property(x => x.ExternalId).HasMaxLength(256);
            e.Property(x => x.ExternalSource).HasMaxLength(64);
            e.HasOne(x => x.Position).WithMany().HasForeignKey(x => x.PositionId);
            e.HasOne(x => x.Department).WithMany().HasForeignKey(x => x.DepartmentId);
            e.HasOne(x => x.Region).WithMany().HasForeignKey(x => x.RegionId);
            e.HasOne(x => x.Location).WithMany().HasForeignKey(x => x.LocationId);
            e.HasOne(x => x.Room).WithMany().HasForeignKey(x => x.RoomId);
            e.HasOne(x => x.Manager).WithMany().HasForeignKey(x => x.ManagerId);
            e.HasOne(x => x.Status).WithMany().HasForeignKey(x => x.StatusId);
            e.HasOne<StoredFile>().WithMany().HasForeignKey(x => x.PhotoFileId);
            e.HasIndex(x => new { x.OrganizationId, x.EmployeeNumber }).IsUnique().HasFilter("\"IsDeleted\" = false");
            e.HasIndex(x => x.FullName).HasMethod("gin").HasOperators("gin_trgm_ops");
            e.HasIndex(x => x.Login);
            e.HasIndex(x => x.Email);
            e.HasIndex(x => x.RegionId);
            e.HasIndex(x => x.DepartmentId);
            e.HasIndex(x => x.StatusId);
            e.HasIndex(x => x.ExternalId);
            e.Property(x => x.Version).IsRowVersion();
        });
        b.Entity<EmployeeOrgHistory>(e =>
        {
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasIndex(x => new { x.EmployeeId, x.EffectiveFrom });
            e.Property(x => x.Reason).HasMaxLength(1000);
        });

        // ---------------- Assets ----------------
        Lookup<AssetCategory>(b, e => e.HasOne(x => x.Parent).WithMany().HasForeignKey(x => x.ParentId));
        Lookup<AssetType>(b, e =>
        {
            e.HasOne(x => x.Category).WithMany().HasForeignKey(x => x.CategoryId);
            e.Property(x => x.Prefix).HasMaxLength(16).IsRequired();
            e.Property(x => x.InventoryNumberFormat).HasMaxLength(64);
            e.Property(x => x.Icon).HasMaxLength(64);
        });
        Lookup<AssetStatus>(b, e => e.Property(x => x.Color).HasMaxLength(32));
        Lookup<Manufacturer>(b, e => { e.Property(x => x.Website).HasMaxLength(256); e.Property(x => x.SupportPhone).HasMaxLength(64); });
        Lookup<Supplier>(b, e =>
        {
            e.Property(x => x.ContactPerson).HasMaxLength(256);
            e.Property(x => x.Phone).HasMaxLength(64);
            e.Property(x => x.Email).HasMaxLength(256);
            e.Property(x => x.Address).HasMaxLength(512);
            e.Property(x => x.TaxId).HasMaxLength(64);
            e.Property(x => x.Website).HasMaxLength(256);
        });
        b.Entity<Contract>(e =>
        {
            e.Property(x => x.Number).HasMaxLength(128).IsRequired();
            e.Property(x => x.Title).HasMaxLength(512).IsRequired();
            e.Property(x => x.Currency).HasMaxLength(8);
            e.Property(x => x.Amount).HasPrecision(18, 2);
            e.HasOne(x => x.Supplier).WithMany().HasForeignKey(x => x.SupplierId);
            e.HasOne<Region>().WithMany().HasForeignKey(x => x.RegionId);
            e.HasIndex(x => x.EndDate);
        });
        b.Entity<Asset>(e =>
        {
            e.Property(x => x.InventoryNumber).HasMaxLength(64).IsRequired();
            e.Property(x => x.Name).HasMaxLength(256).IsRequired();
            e.Property(x => x.Model).HasMaxLength(256);
            e.Property(x => x.SerialNumber).HasMaxLength(128);
            e.Property(x => x.Hostname).HasMaxLength(128);
            e.Property(x => x.IpAddress).HasMaxLength(64);
            e.Property(x => x.MacAddress).HasMaxLength(64);
            e.Property(x => x.Currency).HasMaxLength(8);
            e.Property(x => x.InvoiceNumber).HasMaxLength(128);
            e.Property(x => x.PurchasePrice).HasPrecision(18, 2);
            e.Property(x => x.SalvageValue).HasPrecision(18, 2);
            e.HasOne(x => x.AssetType).WithMany().HasForeignKey(x => x.AssetTypeId);
            e.HasOne(x => x.Category).WithMany().HasForeignKey(x => x.CategoryId);
            e.HasOne(x => x.Manufacturer).WithMany().HasForeignKey(x => x.ManufacturerId);
            e.HasOne(x => x.Status).WithMany().HasForeignKey(x => x.StatusId);
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne(x => x.ResponsibleEmployee).WithMany().HasForeignKey(x => x.ResponsibleEmployeeId);
            e.HasOne(x => x.Department).WithMany().HasForeignKey(x => x.DepartmentId);
            e.HasOne(x => x.Region).WithMany().HasForeignKey(x => x.RegionId);
            e.HasOne(x => x.Location).WithMany().HasForeignKey(x => x.LocationId);
            e.HasOne(x => x.ParentAsset).WithMany().HasForeignKey(x => x.ParentAssetId);
            e.HasOne(x => x.Supplier).WithMany().HasForeignKey(x => x.SupplierId);
            e.HasOne(x => x.Contract).WithMany().HasForeignKey(x => x.ContractId);
            e.HasIndex(x => new { x.OrganizationId, x.InventoryNumber }).IsUnique();
            e.HasIndex(x => x.InventoryNumber).HasMethod("gin").HasOperators("gin_trgm_ops").HasDatabaseName("IX_Assets_InventoryNumber_trgm");
            e.HasIndex(x => x.SerialNumber);
            e.HasIndex(x => x.Name).HasMethod("gin").HasOperators("gin_trgm_ops");
            e.HasIndex(x => x.StatusId);
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => x.RegionId);
            e.HasIndex(x => x.AssetTypeId);
            e.HasIndex(x => x.DepartmentId);
            e.HasIndex(x => x.LocationId);
            e.HasIndex(x => x.WarrantyExpiration);
            e.HasIndex(x => x.CustomFields).HasMethod("gin");
            e.Property(x => x.Version).IsRowVersion();
        });
        b.Entity<AssetEvent>(e =>
        {
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.Property(x => x.Sequence).HasDefaultValueSql("nextval('asset_event_seq')").ValueGeneratedOnAdd();
            e.Property(x => x.RecordedByName).HasMaxLength(256);
            e.Property(x => x.Description).HasMaxLength(2000);
            e.Property(x => x.CancelReason).HasMaxLength(1000);
            e.HasIndex(x => new { x.AssetId, x.EffectiveAt, x.Sequence });
            e.HasIndex(x => x.OperationId);
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => x.EffectiveAt);
        });
        b.Entity<CustomFieldDefinition>(e =>
        {
            e.Property(x => x.Key).HasMaxLength(64).IsRequired();
            e.Property(x => x.Label).HasMaxLength(256).IsRequired();
            e.Property(x => x.Group).HasMaxLength(128);
            e.HasOne(x => x.AssetType).WithMany().HasForeignKey(x => x.AssetTypeId);
            e.HasIndex(x => new { x.OrganizationId, x.EntityType, x.AssetTypeId, x.Key }).IsUnique();
        });
        b.Entity<NumberSequence>(e =>
        {
            e.HasKey(x => new { x.OrganizationId, x.Key });
            e.Property(x => x.Key).HasMaxLength(128);
        });

        // ---------------- Operations ----------------
        b.Entity<OperationBatch>(e =>
        {
            e.Property(x => x.Number).HasMaxLength(64).IsRequired();
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne<Employee>().WithMany().HasForeignKey(x => x.ResponsibleEmployeeId);
            e.HasOne<Region>().WithMany().HasForeignKey(x => x.RegionId);
            e.HasIndex(x => new { x.OrganizationId, x.Number }).IsUnique();
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => x.EffectiveAt);
            e.Property(x => x.CancelReason).HasMaxLength(1000);
        });
        b.Entity<Assignment>(e =>
        {
            e.HasOne(x => x.Batch).WithMany(x => x.Assignments).HasForeignKey(x => x.BatchId);
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne<Location>().WithMany().HasForeignKey(x => x.LocationId);
            e.HasOne<Employee>().WithMany().HasForeignKey(x => x.ResponsibleEmployeeId);
            e.HasIndex(x => x.AssetId).IsUnique().HasFilter("\"EffectiveTo\" IS NULL AND \"IsCancelled\" = false")
                .HasDatabaseName("UX_Assignments_OneOpenPerAsset");
            e.HasIndex(x => new { x.AssetId, x.EffectiveFrom });
            e.HasIndex(x => x.EmployeeId);
        });
        b.Entity<AssetReturn>(e =>
        {
            e.HasOne(x => x.Batch).WithMany(x => x.Returns).HasForeignKey(x => x.BatchId);
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne<Assignment>().WithMany().HasForeignKey(x => x.AssignmentId);
            e.HasOne<AssetStatus>().WithMany().HasForeignKey(x => x.ResultStatusId);
            e.HasOne<Location>().WithMany().HasForeignKey(x => x.LocationId);
            e.HasIndex(x => x.AssetId);
            e.HasIndex(x => x.EmployeeId);
        });
        b.Entity<AssetTransfer>(e =>
        {
            e.HasOne(x => x.Batch).WithMany(x => x.Transfers).HasForeignKey(x => x.BatchId);
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasIndex(x => x.AssetId);
            e.Property(x => x.Reason).HasMaxLength(1000);
        });
        b.Entity<AssetStatusChange>(e =>
        {
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasOne(x => x.Batch).WithMany(x => x.StatusChanges).HasForeignKey(x => x.BatchId);
            e.HasOne<AssetStatus>().WithMany().HasForeignKey(x => x.FromStatusId);
            e.HasOne<AssetStatus>().WithMany().HasForeignKey(x => x.ToStatusId);
            e.Property(x => x.Number).HasMaxLength(64);
            e.HasIndex(x => x.AssetId);
        });
        Lookup<RepairStatus>(b, e => { e.Property(x => x.Color).HasMaxLength(32); e.Ignore(x => x.IsClosed); });
        b.Entity<Repair>(e =>
        {
            e.Property(x => x.Number).HasMaxLength(64).IsRequired();
            e.Property(x => x.Problem).HasMaxLength(4000).IsRequired();
            e.Property(x => x.Cost).HasPrecision(18, 2);
            e.Property(x => x.Currency).HasMaxLength(8);
            e.Property(x => x.Technician).HasMaxLength(256);
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasOne(x => x.Status).WithMany().HasForeignKey(x => x.StatusId);
            e.HasOne(x => x.ServiceCenter).WithMany().HasForeignKey(x => x.ServiceCenterId);
            e.HasMany(x => x.History).WithOne().HasForeignKey(x => x.RepairId).OnDelete(DeleteBehavior.Cascade);
            e.HasIndex(x => new { x.OrganizationId, x.Number }).IsUnique();
            e.HasIndex(x => x.AssetId);
            e.HasIndex(x => x.StatusId);
            e.HasIndex(x => x.OpenedAt);
            e.Property(x => x.Version).IsRowVersion();
        });
        b.Entity<RepairStatusHistory>(e => e.Property(x => x.StatusName).HasMaxLength(256));

        // ---------------- Licensing ----------------
        Lookup<Software>(b, e =>
        {
            e.Property(x => x.Publisher).HasMaxLength(256);
            e.Property(x => x.Version).HasMaxLength(64);
            e.Property(x => x.Category).HasMaxLength(128);
            e.Property(x => x.Website).HasMaxLength(256);
        });
        Lookup<LicenseType>(b);
        b.Entity<License>(e =>
        {
            e.Property(x => x.Name).HasMaxLength(256).IsRequired();
            e.Property(x => x.Cost).HasPrecision(18, 2);
            e.Property(x => x.Currency).HasMaxLength(8);
            e.Property(x => x.ContractNumber).HasMaxLength(128);
            e.HasOne(x => x.Software).WithMany().HasForeignKey(x => x.SoftwareId);
            e.HasOne(x => x.Vendor).WithMany().HasForeignKey(x => x.VendorId);
            e.HasOne(x => x.Supplier).WithMany().HasForeignKey(x => x.SupplierId);
            e.HasOne(x => x.LicenseType).WithMany().HasForeignKey(x => x.LicenseTypeId);
            e.HasOne<Contract>().WithMany().HasForeignKey(x => x.ContractId);
            e.HasOne<Region>().WithMany().HasForeignKey(x => x.RegionId);
            e.HasIndex(x => x.ExpirationDate);
            e.HasIndex(x => x.SoftwareId);
            e.Property(x => x.Version).IsRowVersion();
        });
        b.Entity<LicenseAssignment>(e =>
        {
            e.HasOne(x => x.License).WithMany(x => x.Assignments).HasForeignKey(x => x.LicenseId);
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasIndex(x => x.LicenseId);
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => x.AssetId);
        });

        // ---------------- Access ----------------
        Lookup<AccessSystem>(b, e => { e.Property(x => x.Owner).HasMaxLength(256); e.Property(x => x.Criticality).HasMaxLength(64); });
        Lookup<AccessLevel>(b, e => e.HasOne(x => x.AccessSystem).WithMany().HasForeignKey(x => x.AccessSystemId));
        b.Entity<EmployeeAccess>(e =>
        {
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasOne(x => x.AccessSystem).WithMany().HasForeignKey(x => x.AccessSystemId);
            e.HasOne(x => x.AccessLevel).WithMany().HasForeignKey(x => x.AccessLevelId);
            e.HasOne<Employee>().WithMany().HasForeignKey(x => x.ResponsibleEmployeeId);
            e.Property(x => x.Username).HasMaxLength(256);
            e.Property(x => x.Role).HasMaxLength(256);
            e.Property(x => x.RequestReference).HasMaxLength(128);
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => new { x.AccessSystemId, x.Status });
        });

        // ---------------- Checklists ----------------
        Lookup<ChecklistTemplate>(b, e =>
            e.HasMany(x => x.Items).WithOne(x => x.Template).HasForeignKey(x => x.TemplateId).OnDelete(DeleteBehavior.Cascade));
        b.Entity<ChecklistTemplateItem>(e => e.Property(x => x.Title).HasMaxLength(512).IsRequired());
        b.Entity<EmployeeChecklist>(e =>
        {
            e.Property(x => x.Title).HasMaxLength(512);
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasMany(x => x.Items).WithOne(x => x.Checklist).HasForeignKey(x => x.ChecklistId).OnDelete(DeleteBehavior.Cascade);
            e.HasIndex(x => new { x.EmployeeId, x.Kind });
        });
        b.Entity<EmployeeChecklistItem>(e => e.Property(x => x.Title).HasMaxLength(512).IsRequired());

        // ---------------- Documents ----------------
        Lookup<DocumentTemplate>(b, e =>
            e.HasMany(x => x.Versions).WithOne(x => x.Template).HasForeignKey(x => x.TemplateId));
        b.Entity<DocumentTemplateVersion>(e =>
        {
            e.HasOne(x => x.File).WithMany().HasForeignKey(x => x.FileId);
            e.HasIndex(x => new { x.TemplateId, x.VersionNumber }).IsUnique();
            e.Property(x => x.FileHash).HasMaxLength(128);
        });
        b.Entity<GeneratedDocument>(e =>
        {
            e.Property(x => x.Number).HasMaxLength(64).IsRequired();
            e.Property(x => x.Title).HasMaxLength(512);
            e.Property(x => x.SourceType).HasMaxLength(64);
            e.HasOne(x => x.TemplateVersion).WithMany().HasForeignKey(x => x.TemplateVersionId);
            e.HasOne(x => x.DocxFile).WithMany().HasForeignKey(x => x.DocxFileId);
            e.HasOne(x => x.PdfFile).WithMany().HasForeignKey(x => x.PdfFileId);
            e.HasIndex(x => new { x.SourceType, x.SourceId });
            e.HasIndex(x => x.EmployeeId);
            e.HasIndex(x => x.AssetId);
            e.HasIndex(x => new { x.OrganizationId, x.Number }).IsUnique();
        });
        b.Entity<StoredFile>(e =>
        {
            e.Property(x => x.FileName).HasMaxLength(512).IsRequired();
            e.Property(x => x.ContentType).HasMaxLength(128);
            e.Property(x => x.StoragePath).HasMaxLength(1024).IsRequired();
            e.Property(x => x.Sha256).HasMaxLength(128);
            e.Property(x => x.EntityType).HasMaxLength(64);
            e.HasIndex(x => new { x.EntityType, x.EntityId });
        });

        // ---------------- Security ----------------
        b.Entity<User>(e =>
        {
            e.Property(x => x.UserName).HasMaxLength(128).IsRequired();
            e.Property(x => x.NormalizedUserName).HasMaxLength(128).IsRequired();
            e.Property(x => x.DisplayName).HasMaxLength(256);
            e.Property(x => x.Email).HasMaxLength(256);
            e.Property(x => x.AuthProvider).HasMaxLength(32);
            e.Property(x => x.LastLoginIp).HasMaxLength(64);
            e.HasIndex(x => new { x.OrganizationId, x.NormalizedUserName }).IsUnique().HasFilter("\"IsDeleted\" = false");
            e.HasOne<Employee>().WithMany().HasForeignKey(x => x.EmployeeId);
            e.HasMany(x => x.Roles).WithOne(x => x.User).HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(x => x.Regions).WithOne(x => x.User).HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<Role>(e =>
        {
            e.Property(x => x.Name).HasMaxLength(128).IsRequired();
            e.Property(x => x.Code).HasMaxLength(64).IsRequired();
            e.HasIndex(x => new { x.OrganizationId, x.Code }).IsUnique();
            e.HasMany(x => x.Permissions).WithOne(x => x.Role).HasForeignKey(x => x.RoleId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<Permission>(e =>
        {
            e.HasKey(x => x.Code);
            e.Property(x => x.Code).HasMaxLength(64);
            e.Property(x => x.Group).HasMaxLength(128);
            e.Property(x => x.Description).HasMaxLength(512);
        });
        b.Entity<RolePermission>(e =>
        {
            e.HasKey(x => new { x.RoleId, x.PermissionCode });
            e.HasOne<Permission>().WithMany().HasForeignKey(x => x.PermissionCode).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<UserRole>(e =>
        {
            e.HasKey(x => new { x.UserId, x.RoleId });
            e.HasOne(x => x.Role).WithMany().HasForeignKey(x => x.RoleId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<UserRegion>(e =>
        {
            e.HasKey(x => new { x.UserId, x.RegionId });
            e.HasOne(x => x.Region).WithMany().HasForeignKey(x => x.RegionId).OnDelete(DeleteBehavior.Cascade);
        });
        b.Entity<UserSession>(e =>
        {
            e.HasOne(x => x.User).WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.Property(x => x.IpAddress).HasMaxLength(64);
            e.Property(x => x.UserAgent).HasMaxLength(512);
            e.HasIndex(x => x.UserId);
        });
        b.Entity<ApiToken>(e =>
        {
            e.HasOne(x => x.User).WithMany().HasForeignKey(x => x.UserId).OnDelete(DeleteBehavior.Cascade);
            e.Property(x => x.Name).HasMaxLength(128);
            e.Property(x => x.TokenHash).HasMaxLength(128);
            e.Property(x => x.Prefix).HasMaxLength(16);
            e.HasIndex(x => x.TokenHash).IsUnique();
        });

        // ---------------- System ----------------
        b.Entity<AuditLog>(e =>
        {
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).UseIdentityAlwaysColumn();
            e.Property(x => x.Action).HasMaxLength(128).IsRequired();
            e.Property(x => x.EntityType).HasMaxLength(64);
            e.Property(x => x.EntityName).HasMaxLength(512);
            e.Property(x => x.UserName).HasMaxLength(128);
            e.Property(x => x.IpAddress).HasMaxLength(64);
            e.Property(x => x.UserAgent).HasMaxLength(300);
            e.Property(x => x.CorrelationId).HasMaxLength(64);
            e.HasIndex(x => x.Timestamp);
            e.HasIndex(x => new { x.EntityType, x.EntityId });
            e.HasIndex(x => x.UserId);
            e.HasIndex(x => x.Action);
        });
        b.Entity<Notification>(e =>
        {
            e.Property(x => x.Type).HasMaxLength(64);
            e.Property(x => x.Title).HasMaxLength(512);
            e.Property(x => x.Message).HasMaxLength(2000);
            e.Property(x => x.EntityType).HasMaxLength(64);
            e.Property(x => x.Link).HasMaxLength(512);
            e.Property(x => x.RequiredPermission).HasMaxLength(64);
            e.Property(x => x.DedupKey).HasMaxLength(256);
            e.HasIndex(x => new { x.OrganizationId, x.DedupKey }).IsUnique();
            e.HasIndex(x => x.CreatedAt);
        });
        b.Entity<NotificationRead>(e => e.HasKey(x => new { x.NotificationId, x.UserId }));
        b.Entity<NotificationDelivery>(e => { e.Property(x => x.Channel).HasMaxLength(32); e.Property(x => x.Recipient).HasMaxLength(256); });
        b.Entity<Setting>(e =>
        {
            e.HasKey(x => new { x.OrganizationId, x.Key });
            e.Property(x => x.Key).HasMaxLength(64);
            e.Property(x => x.Value).HasColumnType("jsonb");
        });
        b.Entity<Backup>(e =>
        {
            e.Property(x => x.FileName).HasMaxLength(256);
            e.Property(x => x.FilePath).HasMaxLength(1024);
            e.Property(x => x.CreatedByName).HasMaxLength(128);
            e.Property(x => x.AppVersion).HasMaxLength(32);
        });
        b.Entity<ImportJob>(e =>
        {
            e.Property(x => x.EntityType).HasMaxLength(64);
            e.Property(x => x.FileName).HasMaxLength(512);
        });

        // ---------------- Inventory / stock ----------------
        b.Entity<InventoryCampaign>(e =>
        {
            e.Property(x => x.Number).HasMaxLength(64);
            e.Property(x => x.Name).HasMaxLength(256);
            e.HasMany(x => x.Items).WithOne(x => x.Campaign).HasForeignKey(x => x.CampaignId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne<Region>().WithMany().HasForeignKey(x => x.RegionId);
            e.HasOne<Location>().WithMany().HasForeignKey(x => x.LocationId);
        });
        b.Entity<InventoryCampaignItem>(e =>
        {
            e.HasOne(x => x.Asset).WithMany().HasForeignKey(x => x.AssetId);
            e.HasIndex(x => new { x.CampaignId, x.AssetId }).IsUnique();
        });
        Lookup<StockItem>(b, e =>
        {
            e.Property(x => x.Sku).HasMaxLength(64);
            e.Property(x => x.Category).HasMaxLength(128);
            e.Property(x => x.Unit).HasMaxLength(16);
            e.Property(x => x.MinQuantity).HasPrecision(18, 3);
            e.Property(x => x.UnitPrice).HasPrecision(18, 2);
        });
        b.Entity<StockBalance>(e =>
        {
            e.HasOne(x => x.StockItem).WithMany().HasForeignKey(x => x.StockItemId);
            e.HasOne(x => x.Location).WithMany().HasForeignKey(x => x.LocationId);
            e.HasIndex(x => new { x.StockItemId, x.LocationId }).IsUnique();
            e.Property(x => x.Quantity).HasPrecision(18, 3);
            e.Property(x => x.Version).IsRowVersion();
        });
        b.Entity<StockMovement>(e =>
        {
            e.HasOne(x => x.StockItem).WithMany().HasForeignKey(x => x.StockItemId);
            e.Property(x => x.Quantity).HasPrecision(18, 3);
            e.Property(x => x.DocumentNumber).HasMaxLength(128);
            e.HasIndex(x => x.StockItemId);
        });

        // ---------------- Conventions ----------------
        foreach (var et in b.Model.GetEntityTypes())
        {
            foreach (var p in et.GetProperties())
            {
                if (p.ClrType == typeof(string) && (JsonbNames.Contains(p.Name) || p.Name.EndsWith("Snapshot")))
                    p.SetColumnType("jsonb");
                else if (p.ClrType == typeof(string) && p.GetMaxLength() is null && p.GetColumnType() is null)
                {
                    // Long free text fields stay unbounded; short descriptive fields get a sane limit.
                    if (p.Name is "Name" or "Code") p.SetMaxLength(p.Name == "Code" ? 64 : 256);
                }
            }
            // History must never be lost: no cascading deletes unless configured explicitly above.
            foreach (var fk in et.GetForeignKeys())
                if (fk.DeleteBehavior == DeleteBehavior.Cascade && !IsOwnedChild(fk))
                    fk.DeleteBehavior = DeleteBehavior.Restrict;
                else if (fk.DeleteBehavior == DeleteBehavior.ClientSetNull)
                    fk.DeleteBehavior = DeleteBehavior.Restrict;
        }
    }

    private static readonly HashSet<Type> OwnedChildren = new()
    {
        typeof(ChecklistTemplateItem), typeof(EmployeeChecklistItem), typeof(RolePermission), typeof(UserRole),
        typeof(UserRegion), typeof(UserSession), typeof(ApiToken), typeof(RepairStatusHistory), typeof(InventoryCampaignItem)
    };

    private static bool IsOwnedChild(IMutableForeignKey fk) => OwnedChildren.Contains(fk.DeclaringEntityType.ClrType);

    private static void Lookup<T>(ModelBuilder b, Action<Microsoft.EntityFrameworkCore.Metadata.Builders.EntityTypeBuilder<T>>? extra = null)
        where T : LookupEntity
    {
        b.Entity<T>(e =>
        {
            e.Property(x => x.Name).HasMaxLength(256).IsRequired();
            e.Property(x => x.Code).HasMaxLength(64);
            e.Property(x => x.Description).HasMaxLength(2000);
            e.HasIndex(x => new { x.OrganizationId, x.Name });
            extra?.Invoke(e);
        });
    }
}
