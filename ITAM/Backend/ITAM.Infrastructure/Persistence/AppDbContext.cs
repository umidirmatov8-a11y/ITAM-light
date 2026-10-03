using System.Linq.Expressions;
using System.Reflection;
using ITAM.Application.Common;
using ITAM.Domain.Common;
using ITAM.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;

namespace ITAM.Infrastructure.Persistence;

public class AppDbContext : DbContext, IAppDbContext
{
    private readonly ITenantContext _tenant;
    private readonly ICurrentUser _user;
    private readonly IClock _clock;
    private readonly AuditContext _audit;

    public AppDbContext(DbContextOptions<AppDbContext> options, ITenantContext tenant, ICurrentUser user, IClock clock, AuditContext audit)
        : base(options)
    {
        _tenant = tenant; _user = user; _clock = clock; _audit = audit;
    }

    /// <summary>Used by global query filters (parameterized per context instance).</summary>
    public Guid TenantId => _tenant.OrganizationId;

    public DbSet<Organization> Organizations => Set<Organization>();
    public DbSet<Region> Regions => Set<Region>();
    public DbSet<Location> Locations => Set<Location>();
    public DbSet<Department> Departments => Set<Department>();
    public DbSet<Position> Positions => Set<Position>();
    public DbSet<EmployeeStatus> EmployeeStatuses => Set<EmployeeStatus>();
    public DbSet<Employee> Employees => Set<Employee>();
    public DbSet<EmployeeOrgHistory> EmployeeOrgHistory => Set<EmployeeOrgHistory>();
    public DbSet<AssetCategory> AssetCategories => Set<AssetCategory>();
    public DbSet<AssetType> AssetTypes => Set<AssetType>();
    public DbSet<AssetStatus> AssetStatuses => Set<AssetStatus>();
    public DbSet<Manufacturer> Manufacturers => Set<Manufacturer>();
    public DbSet<Supplier> Suppliers => Set<Supplier>();
    public DbSet<Contract> Contracts => Set<Contract>();
    public DbSet<Asset> Assets => Set<Asset>();
    public DbSet<AssetEvent> AssetEvents => Set<AssetEvent>();
    public DbSet<CustomFieldDefinition> CustomFieldDefinitions => Set<CustomFieldDefinition>();
    public DbSet<NumberSequence> NumberSequences => Set<NumberSequence>();
    public DbSet<OperationBatch> OperationBatches => Set<OperationBatch>();
    public DbSet<Assignment> Assignments => Set<Assignment>();
    public DbSet<AssetReturn> AssetReturns => Set<AssetReturn>();
    public DbSet<AssetTransfer> AssetTransfers => Set<AssetTransfer>();
    public DbSet<AssetStatusChange> AssetStatusChanges => Set<AssetStatusChange>();
    public DbSet<RepairStatus> RepairStatuses => Set<RepairStatus>();
    public DbSet<Repair> Repairs => Set<Repair>();
    public DbSet<RepairStatusHistory> RepairStatusHistory => Set<RepairStatusHistory>();
    public DbSet<Software> Software => Set<Software>();
    public DbSet<LicenseType> LicenseTypes => Set<LicenseType>();
    public DbSet<License> Licenses => Set<License>();
    public DbSet<LicenseAssignment> LicenseAssignments => Set<LicenseAssignment>();
    public DbSet<AccessSystem> AccessSystems => Set<AccessSystem>();
    public DbSet<AccessLevel> AccessLevels => Set<AccessLevel>();
    public DbSet<EmployeeAccess> EmployeeAccesses => Set<EmployeeAccess>();
    public DbSet<ChecklistTemplate> ChecklistTemplates => Set<ChecklistTemplate>();
    public DbSet<ChecklistTemplateItem> ChecklistTemplateItems => Set<ChecklistTemplateItem>();
    public DbSet<EmployeeChecklist> EmployeeChecklists => Set<EmployeeChecklist>();
    public DbSet<EmployeeChecklistItem> EmployeeChecklistItems => Set<EmployeeChecklistItem>();
    public DbSet<DocumentTemplate> DocumentTemplates => Set<DocumentTemplate>();
    public DbSet<DocumentTemplateVersion> DocumentTemplateVersions => Set<DocumentTemplateVersion>();
    public DbSet<GeneratedDocument> GeneratedDocuments => Set<GeneratedDocument>();
    public DbSet<StoredFile> StoredFiles => Set<StoredFile>();
    public DbSet<User> Users => Set<User>();
    public DbSet<Role> Roles => Set<Role>();
    public DbSet<Permission> Permissions => Set<Permission>();
    public DbSet<RolePermission> RolePermissions => Set<RolePermission>();
    public DbSet<UserRole> UserRoles => Set<UserRole>();
    public DbSet<UserRegion> UserRegions => Set<UserRegion>();
    public DbSet<UserSession> UserSessions => Set<UserSession>();
    public DbSet<ApiToken> ApiTokens => Set<ApiToken>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<Notification> Notifications => Set<Notification>();
    public DbSet<NotificationRead> NotificationReads => Set<NotificationRead>();
    public DbSet<NotificationDelivery> NotificationDeliveries => Set<NotificationDelivery>();
    public DbSet<Setting> Settings => Set<Setting>();
    public DbSet<Backup> Backups => Set<Backup>();
    public DbSet<ImportJob> ImportJobs => Set<ImportJob>();
    public DbSet<InventoryCampaign> InventoryCampaigns => Set<InventoryCampaign>();
    public DbSet<InventoryCampaignItem> InventoryCampaignItems => Set<InventoryCampaignItem>();
    public DbSet<StockItem> StockItems => Set<StockItem>();
    public DbSet<StockBalance> StockBalances => Set<StockBalance>();
    public DbSet<StockMovement> StockMovements => Set<StockMovement>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        ModelConfiguration.Configure(modelBuilder);

        // Global query filters: tenant isolation + soft delete.
        foreach (var et in modelBuilder.Model.GetEntityTypes())
        {
            var clr = et.ClrType;
            if (et.BaseType is not null) continue;
            var isTenant = typeof(ITenantEntity).IsAssignableFrom(clr);
            var isSoft = typeof(ISoftDelete).IsAssignableFrom(clr);
            if (!isTenant && !isSoft) continue;
            var method = typeof(AppDbContext).GetMethod(nameof(BuildFilter), BindingFlags.NonPublic | BindingFlags.Instance)!
                .MakeGenericMethod(clr);
            var filter = (LambdaExpression)method.Invoke(this, new object[] { isTenant, isSoft })!;
            et.SetQueryFilter(filter);
        }
    }

    private LambdaExpression BuildFilter<T>(bool tenant, bool soft) where T : class
    {
        var param = Expression.Parameter(typeof(T), "e");
        Expression? body = null;
        if (tenant)
            body = Expression.Equal(Expression.Property(param, nameof(ITenantEntity.OrganizationId)),
                Expression.Property(Expression.Constant(this), nameof(TenantId)));
        if (soft)
        {
            var notDeleted = Expression.Not(Expression.Property(param, nameof(ISoftDelete.IsDeleted)));
            body = body is null ? notDeleted : Expression.AndAlso(body, notDeleted);
        }
        return Expression.Lambda<Func<T, bool>>(body!, param);
    }

    public override int SaveChanges(bool acceptAllChangesOnSuccess)
    {
        OnBeforeSave();
        return base.SaveChanges(acceptAllChangesOnSuccess);
    }

    public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
    {
        OnBeforeSave();
        return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
    }

    public Task<int> SaveChangesAsync(CancellationToken ct = default) => SaveChangesAsync(true, ct);

    private void OnBeforeSave()
    {
        var now = _clock.UtcNow;
        var userId = _user.UserId;
        var audits = new List<AuditLog>();

        foreach (var entry in ChangeTracker.Entries().ToList())
        {
            if (entry.Entity is AuditLog && entry.State is EntityState.Modified or EntityState.Deleted)
                throw new InvalidOperationException("Audit log records are immutable");

            if (entry.State == EntityState.Added && entry.Entity is ITenantEntity t && t.OrganizationId == Guid.Empty)
                t.OrganizationId = _tenant.OrganizationId;

            if (entry.Entity is IAuditableEntity a)
            {
                if (entry.State == EntityState.Added)
                {
                    if (a.CreatedAt == default) a.CreatedAt = now;
                    a.CreatedById ??= userId;
                }
                else if (entry.State == EntityState.Modified)
                {
                    a.UpdatedAt = now;
                    a.UpdatedById = userId;
                }
            }

            // Physical deletes of soft-deletable entities become soft deletes.
            if (entry.State == EntityState.Deleted && entry.Entity is ISoftDelete sd)
            {
                entry.State = EntityState.Modified;
                sd.IsDeleted = true;
                sd.DeletedAt = now;
                sd.DeletedById = userId;
            }

            if (!_audit.SuppressAutomatic && entry.Entity is IAuditable
                && entry.State is EntityState.Added or EntityState.Modified or EntityState.Deleted)
            {
                var log = BuildAudit(entry, now);
                if (log is not null) audits.Add(log);
            }
        }

        if (audits.Count > 0) AuditLogs.AddRange(audits);
    }

    private static readonly HashSet<string> IgnoredAuditProps = new()
    {
        "Version", "UpdatedAt", "UpdatedById", "CreatedAt", "CreatedById", "OrganizationId"
    };

    private AuditLog? BuildAudit(EntityEntry entry, DateTime now)
    {
        var type = entry.Entity.GetType();
        var oldValues = new Dictionary<string, object?>();
        var newValues = new Dictionary<string, object?>();
        foreach (var p in entry.Properties)
        {
            var name = p.Metadata.Name;
            if (IgnoredAuditProps.Contains(name)) continue;
            var sensitive = p.Metadata.PropertyInfo?.GetCustomAttribute<SensitiveAttribute>() is not null;
            switch (entry.State)
            {
                case EntityState.Added:
                    if (p.CurrentValue is not null) newValues[name] = sensitive ? "***" : p.CurrentValue;
                    break;
                case EntityState.Modified when p.IsModified && !Equals(p.OriginalValue, p.CurrentValue):
                    oldValues[name] = sensitive ? "***" : p.OriginalValue;
                    newValues[name] = sensitive ? "***" : p.CurrentValue;
                    break;
                case EntityState.Deleted:
                    oldValues[name] = sensitive ? "***" : p.OriginalValue;
                    break;
            }
        }
        if (entry.State == EntityState.Modified && newValues.Count == 0) return null;

        var action = entry.State switch
        {
            EntityState.Added => "create",
            EntityState.Deleted => "delete",
            _ => newValues.ContainsKey("IsDeleted") && Equals(newValues["IsDeleted"], true) ? "delete"
                : newValues.ContainsKey("IsArchived") ? (Equals(newValues["IsArchived"], true) ? "archive" : "restore")
                : "update"
        };

        return new AuditLog
        {
            OrganizationId = _tenant.OrganizationId,
            Timestamp = now,
            UserId = _user.UserId,
            UserName = _user.UserName ?? "system",
            IpAddress = _user.IpAddress,
            UserAgent = _user.UserAgent is { Length: > 300 } ua ? ua[..300] : _user.UserAgent,
            Action = $"{ToKebab(type.Name)}.{action}",
            EntityType = type.Name,
            EntityId = entry.Entity is Entity e ? e.Id : null,
            EntityName = DisplayName(entry.Entity),
            OldValues = oldValues.Count > 0 ? Json.Serialize(oldValues) : null,
            NewValues = newValues.Count > 0 ? Json.Serialize(newValues) : null,
            CorrelationId = _audit.CorrelationId,
        };
    }

    internal static string? DisplayName(object entity)
    {
        foreach (var prop in new[] { "InventoryNumber", "Number", "FullName", "UserName", "Name", "Title", "Key", "Label" })
        {
            var pi = entity.GetType().GetProperty(prop);
            if (pi?.GetValue(entity) is string s && !string.IsNullOrWhiteSpace(s)) return s;
        }
        return null;
    }

    private static string ToKebab(string name)
        => string.Concat(name.Select((c, i) => i > 0 && char.IsUpper(c) ? "-" + char.ToLowerInvariant(c) : char.ToLowerInvariant(c).ToString()));
}
