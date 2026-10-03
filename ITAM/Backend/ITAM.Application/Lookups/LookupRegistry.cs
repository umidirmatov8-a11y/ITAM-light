using ITAM.Domain.Entities;
using ITAM.Domain.Enums;
using ITAM.Domain.Security;

namespace ITAM.Application.Lookups;

public sealed record LookupDescriptor(
    string Key, Type EntityType, string Title, string ViewPermission, string ManagePermission,
    CustomFieldEntity? CustomFieldEntity = null);

/// <summary>All admin-managed reference data (справочники). Nothing is hard-coded in the UI.</summary>
public static class LookupRegistry
{
    public static readonly IReadOnlyDictionary<string, LookupDescriptor> All = new[]
    {
        new LookupDescriptor("regions", typeof(Region), "Регионы", Permissions.OrgView, Permissions.OrgManage),
        new LookupDescriptor("locations", typeof(Location), "Локации", Permissions.OrgView, Permissions.OrgManage, CustomFieldEntity.Location),
        new LookupDescriptor("departments", typeof(Department), "Подразделения", Permissions.OrgView, Permissions.OrgManage, CustomFieldEntity.Department),
        new LookupDescriptor("positions", typeof(Position), "Должности", Permissions.OrgView, Permissions.OrgManage),
        new LookupDescriptor("employee-statuses", typeof(EmployeeStatus), "Статусы сотрудников", Permissions.EmployeesView, Permissions.DictionariesManage),
        new LookupDescriptor("asset-categories", typeof(AssetCategory), "Категории активов", Permissions.AssetsView, Permissions.DictionariesManage),
        new LookupDescriptor("asset-types", typeof(AssetType), "Типы активов", Permissions.AssetsView, Permissions.DictionariesManage),
        new LookupDescriptor("asset-statuses", typeof(AssetStatus), "Статусы активов", Permissions.AssetsView, Permissions.DictionariesManage),
        new LookupDescriptor("manufacturers", typeof(Manufacturer), "Производители", Permissions.AssetsView, Permissions.DictionariesManage),
        new LookupDescriptor("suppliers", typeof(Supplier), "Поставщики и сервисные центры", Permissions.AssetsView, Permissions.ContractsManage),
        new LookupDescriptor("repair-statuses", typeof(RepairStatus), "Статусы ремонта", Permissions.AssetsView, Permissions.DictionariesManage),
        new LookupDescriptor("software", typeof(Software), "Каталог ПО", Permissions.SoftwareView, Permissions.SoftwareManage, CustomFieldEntity.Software),
        new LookupDescriptor("license-types", typeof(LicenseType), "Типы лицензий", Permissions.LicensesView, Permissions.DictionariesManage),
        new LookupDescriptor("access-systems", typeof(AccessSystem), "Системы доступа", Permissions.AccessView, Permissions.DictionariesManage),
        new LookupDescriptor("access-levels", typeof(AccessLevel), "Уровни доступа", Permissions.AccessView, Permissions.DictionariesManage),
        new LookupDescriptor("stock-items", typeof(StockItem), "Номенклатура склада", Permissions.StockView, Permissions.StockManage),
    }.ToDictionary(d => d.Key, StringComparer.OrdinalIgnoreCase);
}
