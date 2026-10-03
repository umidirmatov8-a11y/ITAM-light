using ITAM.Application.Access;
using ITAM.Application.Admin;
using ITAM.Application.Assets;
using ITAM.Application.Audit;
using ITAM.Application.Auth;
using ITAM.Application.Checklists;
using ITAM.Application.Common;
using ITAM.Application.Contracts;
using ITAM.Application.Dashboard;
using ITAM.Application.DataExchange;
using ITAM.Application.Documents;
using ITAM.Application.Employees;
using ITAM.Application.Inventory;
using ITAM.Application.Licenses;
using ITAM.Application.Lookups;
using ITAM.Application.Notifications;
using ITAM.Application.Operations;
using ITAM.Application.Repairs;
using ITAM.Application.Reports;
using ITAM.Application.Search;
using ITAM.Application.Setup;
using ITAM.Application.Stock;
using Microsoft.Extensions.DependencyInjection;

namespace ITAM.Application;

public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddMemoryCache();
        services.AddSingleton<IClock, SystemClock>();
        services.AddScoped<AuditContext>();
        services.AddScoped<SystemContext>();
        services.AddScoped<IAuditService, AuditService>();
        services.AddScoped<IRegionScope, RegionScope>();
        services.AddScoped<IDepartmentScope, DepartmentScope>();
        services.AddScoped<ISettingsService, SettingsService>();
        services.AddScoped<INumberingService, NumberingService>();
        services.AddScoped<ICustomFieldValidator, CustomFieldValidator>();
        services.AddScoped<ISnapshotService, SnapshotService>();
        services.AddScoped<IFileService, FileService>();

        services.AddScoped<LookupService>();
        services.AddScoped<EmployeeService>();
        services.AddScoped<ChecklistService>();
        services.AddScoped<AssetService>();
        services.AddScoped<AssetTemporalStore>();
        services.AddScoped<AssetOperationService>();
        services.AddScoped<RepairService>();
        services.AddScoped<LicenseService>();
        services.AddScoped<AccessService>();
        services.AddScoped<DocumentTemplateService>();
        services.AddScoped<DocumentService>();
        services.AddScoped<IDocumentGenerator>(sp => sp.GetRequiredService<DocumentService>());
        services.AddScoped<AuditQueryService>();
        services.AddScoped<NotificationService>();
        services.AddScoped<AuthService>();
        services.AddScoped<UserAdminService>();
        services.AddScoped<SettingsAdminService>();
        services.AddScoped<CustomFieldAdminService>();
        services.AddScoped<BackupService>();
        services.AddScoped<ContractService>();
        services.AddScoped<InventoryService>();
        services.AddScoped<StockService>();
        services.AddScoped<DashboardService>();
        services.AddScoped<SearchService>();
        services.AddScoped<ReportService>();
        services.AddScoped<ExportService>();
        services.AddScoped<ImportService>();
        services.AddScoped<SetupService>();
        services.AddScoped<IDemoDataSeeder, DemoDataSeeder>();
        return services;
    }
}
